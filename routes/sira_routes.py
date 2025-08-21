from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import tempfile
import shutil
import os
import logging

from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, OUTPUT_DIR
from transcription_service import transcription_service
from tts_service import tts_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize Groq client for Sira assistant
try:
    sira_groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except Exception as e:
    logger.error(f"Failed to initialize Groq client for Sira: {e}")
    sira_groq_client = None


def _cors_headers_for_request(request: Request) -> dict:
    try:
        origin = request.headers.get("origin")
        # Allow any origin here; main app middleware enforces stricter policy
        if origin:
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Vary": "Origin",
            }
    except Exception:
        pass
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Credentials": "true",
    }


class SiraAskRequest(BaseModel):
    note: str
    query: str


@router.post("/api/sira/ask")
async def sira_ask_endpoint(req: SiraAskRequest, request: Request):
    try:
        if not sira_groq_client or not GROQ_API_KEY:
            raise HTTPException(status_code=503, detail="Groq is not configured")
        note = (req.note or "").strip()
        query = (req.query or "").strip()
        if not note or not query:
            raise HTTPException(status_code=400, detail="Both note and query are required")
        # Truncate to keep prompt size safe
        if len(note) > 8000:
            note = note[:8000]
        if len(query) > 2000:
            query = query[:2000]
        prompt = f"{note}\n\n{query}"
        response = sira_groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are Sira, a concise and helpful AI learning assistant. Answer with reference to the provided note content when applicable. Be accurate and succinct."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=700,
            top_p=0.9,
        )
        answer = (response.choices[0].message.content or "").strip()
        # Generate TTS audio using Deepgram Aura 1 via tts_service
        audio_info = None
        try:
            if not tts_service.is_available():
                tts_service.initialize()
            audio_info = await tts_service.generate_speech(answer, str(OUTPUT_DIR))
        except Exception as te:
            logging.warning(f"Sira TTS generation failed: {te}")
            audio_info = None
        audio_url = None
        if isinstance(audio_info, dict) and audio_info.get("success") and audio_info.get("audio_id"):
            audio_url = f"/api/tts/audio/{audio_info.get('audio_id')}"
        return {"success": True, "answer": answer, "audio_url": audio_url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sira ask error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "detail": "Failed to get answer"}, headers=_cors_headers_for_request(request))


@router.post("/api/sira/ask-audio")
async def sira_ask_audio_endpoint(
    request: Request,
    note: str = Form(...),
    audio: UploadFile = File(...),
):
    try:
        if not audio or not audio.filename:
            return JSONResponse(status_code=400, content={"detail": "Audio is required"}, headers=_cors_headers_for_request(request))
        if not (note or "").strip():
            return JSONResponse(status_code=400, content={"detail": "Note is required"}, headers=_cors_headers_for_request(request))
        # Save uploaded audio to a temp file
        suffix = Path(audio.filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            shutil.copyfileobj(audio.file, tmp)
        transcript_text = None
        try:
            # Use existing transcription service (Deepgram nova-2)
            tx_result = transcription_service.transcribe_audio(tmp_path)
            transcript_text = (tx_result or {}).get("text") or ""
        except Exception as te:
            logger.error(f"Deepgram transcription failed: {te}")
            transcript_text = ""
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        if not sira_groq_client or not GROQ_API_KEY:
            return JSONResponse(status_code=503, content={"detail": "Groq is not configured"}, headers=_cors_headers_for_request(request))
        # Build prompt: note content + spoken question (or fallback)
        user_query = transcript_text.strip() or "Please analyze the note."
        composed = f"{(note or '').strip()}\n\n{user_query}"
        try:
            response = sira_groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are Sira, a concise and helpful AI learning assistant. Answer with reference to the provided note content when applicable. Be accurate and succinct."},
                    {"role": "user", "content": composed},
                ],
                temperature=0.2,
                max_tokens=700,
                top_p=0.9,
            )
            answer = (response.choices[0].message.content or "").strip()
        except Exception as ge:
            logger.error(f"Groq call failed: {ge}")
            answer = ""
        # Generate TTS audio using Deepgram Aura 1 via tts_service
        audio_info = None
        try:
            if not tts_service.is_available():
                tts_service.initialize()
            audio_info = await tts_service.generate_speech(answer, str(OUTPUT_DIR))
        except Exception as te:
            logger.warning(f"Sira TTS (audio question) generation failed: {te}")
            audio_info = None
        audio_url = None
        if isinstance(audio_info, dict) and audio_info.get("success") and audio_info.get("audio_id"):
            audio_url = f"/api/tts/audio/{audio_info.get('audio_id')}"
        return JSONResponse(status_code=200, content={
            "success": True,
            "transcript": transcript_text,
            "answer": answer,
            "audio_url": audio_url,
        }, headers=_cors_headers_for_request(request))
    except Exception as e:
        logger.error(f"Sira ask-audio error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "detail": "Failed to process audio"}, headers=_cors_headers_for_request(request))
