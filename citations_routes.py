import os
import re
from typing import Optional, List, Dict, Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/citations", tags=["citations"]) 

# --- Pydantic models ---
class SuggestRequest(BaseModel):
    text: Optional[str] = None
    topic: Optional[str] = None
    level: Optional[str] = "intro"  # intro | intermediate | advanced

class SuggestResponse(BaseModel):
    topic: str
    level: str
    keywords: List[str]
    reference_types: List[str]
    recommended_queries: List[str]
    scholarly_api_hint: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    focus: Optional[str] = "general"  # general | paper | textbook | standards | docs
    num: Optional[int] = 5
    lang: Optional[str] = None

class SearchResult(BaseModel):
    title: str
    link: str
    snippet: Optional[str] = None
    displayLink: Optional[str] = None

class SearchResponse(BaseModel):
    query: str
    focus: str
    results: List[SearchResult]
    provider: str
    note: Optional[str] = None


# --- Helpers ---
_EDU_SITES = [
    "site:mit.edu", "site:stanford.edu", "site:harvard.edu", "site:berkeley.edu",
    "site:cmu.edu", "site:cs.princeton.edu", "site:edu"
]
_PAPER_SITES = [
    "site:arxiv.org", "site:openreview.net", "site:acm.org", "site:dl.acm.org",
    "site:ieeexplore.ieee.org", "site:neurips.cc", "site:paperswithcode.com",
    "site:aclweb.org"
]
_STANDARDS_SITES = [
    "site:ietf.org", "site:w3.org", "site:iso.org"
]
_DOCS_SITES = [
    "site:docs.python.org", "site:pytorch.org", "site:tensorflow.org", "site:developer.mozilla.org"
]

_DOMAIN_HINTS: Dict[str, List[str]] = {
    "machine learning": ["neural", "model", "training", "dataset", "inference", "features"],
    "nlp": ["token", "transformer", "bert", "language", "sequence"],
    "computer vision": ["image", "vision", "cnn", "object", "detection"],
    "web": ["http", "cors", "api", "browser", "cookie"],
    "databases": ["sql", "index", "transaction", "consistency", "schema"],
}


def _infer_topic(text: str, explicit: Optional[str]) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    txt = (text or "").lower()
    best = ("general", 0)
    for domain, hints in _DOMAIN_HINTS.items():
        score = sum(1 for h in hints if h in txt)
        if score > best[1]:
            best = (domain, score)
    return best[0]


def _gen_keywords(topic: str, level: str, text: str) -> List[str]:
    base = set()
    # extract candidate words
    words = re.findall(r"[A-Za-z]{4,}", text.lower()) if text else []
    common = {"with","this","that","from","into","over","under","also","than","then","they","them","your","have","used","using","use","will","shall","should","could","would","may","might","been","being","such","very","more","most","much","many","like","just","make","made","into","some","only","well","good","best","case","when","where","what","which","about","into","onto","upon","within","without","between","among"}
    for w in words:
        if w not in common and len(base) < 12:
            base.add(w)
    # topical boosters
    booster = {
        "intro": ["introduction", "overview", "basics", "foundations"],
        "intermediate": ["practical", "guide", "patterns", "case study"],
        "advanced": ["survey", "state of the art", "benchmark", "theory"],
    }
    for k in booster.get(level, []):
        base.add(k)
    # topic-specific boosters
    topic_boost = {
        "machine learning": ["supervised", "unsupervised", "optimization", "generalization"],
        "nlp": ["transformers", "tokenization", "attention", "embedding"],
        "computer vision": ["convolution", "segmentation", "detection", "recognition"],
        "web": ["http", "cors", "jwt", "rest", "caching"],
        "databases": ["transaction", "isolation", "indexing", "normalization"],
    }
    for k in topic_boost.get(topic, []):
        base.add(k)
    return list(base)[:15]


def _reference_types(level: str) -> List[str]:
    types = [
        "textbook chapter",
        "survey/review paper",
        "conference/journal paper",
        "tutorial or lecture notes (university)",
        "official documentation",
        "standards / RFC (if applicable)",
    ]
    if level == "intro":
        types.insert(0, "beginner tutorial")
    return types


def _recommended_queries(topic: str, keywords: List[str]) -> List[str]:
    stem = (topic if topic and topic != "general" else "topic").strip()
    packs = [
        f"{stem} textbook chapter",
        f"{stem} survey paper",
        f"{stem} tutorial site:edu",
        f"{stem} review article",
        f"{stem} best practices",
        f"{stem} lecture notes site:edu",
    ]
    if keywords:
        packs.append(f"{stem} {' '.join(keywords[:3])}")
    return packs


@router.get("/ping")
async def ping():
    return {"status": "ok"}


@router.post("/suggest", response_model=SuggestResponse)
async def suggest_sources(req: SuggestRequest):
    raise HTTPException(status_code=410, detail="Citations feature has been removed")


def _focus_to_filter(focus: str) -> Optional[str]:
    f = (focus or "general").lower()
    if f == "paper":
        return " OR ".join(_PAPER_SITES)
    if f == "textbook":
        return " OR ".join(_EDU_SITES)
    if f == "standards":
        return " OR ".join(_STANDARDS_SITES)
    if f == "docs":
        return " OR ".join(_DOCS_SITES)
    if f == "trusted":
        # Combine reputable domains (edu, papers, standards, docs)
        combined = _EDU_SITES + _PAPER_SITES + _STANDARDS_SITES + _DOCS_SITES
        return " OR ".join(combined)
    return None


async def _google_cse_search(query: str, num: int = 5, lang: Optional[str] = None) -> Dict[str, Any]:
    api_key = os.getenv("GOOGLE_CSE_API_KEY")
    cx = os.getenv("GOOGLE_CSE_CX")
    if not api_key or not cx:
        raise RuntimeError("Google CSE is not configured (GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX)")

    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": max(1, min(int(num or 5), 10)),
    }
    if lang:
        params["lr"] = f"lang_{lang}"

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get("https://www.googleapis.com/customsearch/v1", params=params)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Google CSE error: {resp.status_code} {resp.text[:200]}")
        return resp.json()


@router.post("/search", response_model=SearchResponse)
async def search_sources(req: SearchRequest):
    raise HTTPException(status_code=410, detail="Citations feature has been removed")


class QuickRequest(BaseModel):
    text: str
    level: Optional[str] = "intro"
    focus: Optional[str] = "general"
    num: Optional[int] = 5

class QuickResponse(BaseModel):
    suggestions: SuggestResponse
    search: SearchResponse


@router.post("/quick", response_model=QuickResponse)
async def quick_citations(req: QuickRequest):
    raise HTTPException(status_code=410, detail="Citations feature has been removed")
