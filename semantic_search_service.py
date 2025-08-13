"""
Semantic Search Service

Provides semantic search capabilities for bookmarks using embeddings and vector similarity.
Falls back to TF-IDF based search if embedding models are not available.
"""

import os
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import re
from collections import Counter
import math

logger = logging.getLogger(__name__)

class SemanticSearchService:
    def __init__(self):
        self.embedding_model = None
        self.use_embeddings = False
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
            'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those'
        }
        
        # Try to initialize embedding model
        self._initialize_embedding_model()
    
    def _initialize_embedding_model(self):
        """Initialize embedding model if available"""
        try:
            # Try to use sentence-transformers if available
            from sentence_transformers import SentenceTransformer
            
            # Use a lightweight model that works well for semantic search
            model_name = os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
            self.embedding_model = SentenceTransformer(model_name)
            self.use_embeddings = True
            logger.info(f"✅ Initialized embedding model: {model_name}")
            
        except ImportError:
            logger.warning("⚠️ sentence-transformers not available, using TF-IDF fallback")
            self.use_embeddings = False
        except Exception as e:
            logger.error(f"❌ Failed to initialize embedding model: {e}")
            self.use_embeddings = False
    
    def search_bookmarks(self, query: str, bookmarks: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
        """
        Perform semantic search on bookmarks
        
        Args:
            query: Search query
            bookmarks: List of bookmark dictionaries
            limit: Maximum number of results to return
            
        Returns:
            List of bookmarks with similarity scores
        """
        if not query.strip() or not bookmarks:
            return []
        
        if self.use_embeddings:
            return self._embedding_search(query, bookmarks, limit)
        else:
            return self._tfidf_search(query, bookmarks, limit)
    
    def _embedding_search(self, query: str, bookmarks: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Perform embedding-based semantic search"""
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode([query])[0]
            
            results = []
            
            # Generate embeddings for each bookmark and calculate similarity
            for bookmark in bookmarks:
                content = f"{bookmark.get('title', '')} {bookmark.get('content', '')}"
                if not content.strip():
                    continue
                
                # Generate content embedding
                content_embedding = self.embedding_model.encode([content])[0]
                
                # Calculate cosine similarity
                similarity = self._cosine_similarity(query_embedding, content_embedding)
                
                if similarity > 0.1:  # Minimum threshold
                    result = bookmark.copy()
                    result['similarity_score'] = float(similarity)
                    result['matched_terms'] = self._extract_matched_terms(query, content)
                    results.append(result)
            
            # Sort by similarity score (descending)
            results.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"❌ Embedding search failed: {e}")
            # Fallback to TF-IDF search
            return self._tfidf_search(query, bookmarks, limit)
    
    def _tfidf_search(self, query: str, bookmarks: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Perform TF-IDF based semantic search"""
        query_terms = self._tokenize(query.lower())
        if not query_terms:
            return []
        
        results = []
        
        # Calculate document frequencies for IDF
        doc_frequencies = {}
        all_docs = []
        
        for bookmark in bookmarks:
            content = f"{bookmark.get('title', '')} {bookmark.get('content', '')}".lower()
            terms = self._tokenize(content)
            all_docs.append(terms)
            
            for term in set(terms):
                doc_frequencies[term] = doc_frequencies.get(term, 0) + 1
        
        total_docs = len(bookmarks)
        
        # Calculate similarity for each bookmark
        for i, bookmark in enumerate(bookmarks):
            content = f"{bookmark.get('title', '')} {bookmark.get('content', '')}".lower()
            content_terms = all_docs[i]
            
            if not content_terms:
                continue
            
            # Calculate similarity score
            score = self._calculate_tfidf_similarity(
                query_terms, content_terms, content, doc_frequencies, total_docs
            )
            
            if score > 0.1:  # Minimum threshold
                result = bookmark.copy()
                result['similarity_score'] = float(score)
                result['matched_terms'] = self._find_matched_terms(query_terms, content_terms)
                results.append(result)
        
        # Sort by similarity score (descending)
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        return results[:limit]
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into meaningful terms"""
        # Remove punctuation and split
        text = re.sub(r'[^\w\s]', ' ', text)
        terms = text.split()
        
        # Filter terms
        filtered_terms = []
        for term in terms:
            term = term.lower().strip()
            if len(term) > 2 and term not in self.stop_words:
                filtered_terms.append(term)
        
        return filtered_terms
    
    def _calculate_tfidf_similarity(self, query_terms: List[str], content_terms: List[str], 
                                  full_content: str, doc_frequencies: Dict[str, int], 
                                  total_docs: int) -> float:
        """Calculate TF-IDF based similarity score"""
        if not query_terms or not content_terms:
            return 0.0
        
        score = 0.0
        content_term_counts = Counter(content_terms)
        content_length = len(content_terms)
        
        # Exact phrase matching (higher weight)
        query_phrase = ' '.join(query_terms)
        if query_phrase in full_content:
            score += 2.0
        
        # TF-IDF scoring for individual terms
        for query_term in query_terms:
            if query_term in content_term_counts:
                # Term frequency
                tf = content_term_counts[query_term] / content_length
                
                # Inverse document frequency
                df = doc_frequencies.get(query_term, 1)
                idf = math.log(total_docs / df)
                
                # TF-IDF score
                tfidf = tf * idf
                score += tfidf
            
            # Partial matching for longer terms
            if len(query_term) > 4:
                for content_term in content_term_counts:
                    if query_term in content_term or content_term in query_term:
                        score += 0.3
        
        # Normalize score
        return min(score / len(query_terms), 5.0)
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def _extract_matched_terms(self, query: str, content: str) -> List[str]:
        """Extract matched terms between query and content"""
        query_terms = set(self._tokenize(query.lower()))
        content_terms = set(self._tokenize(content.lower()))
        
        return list(query_terms.intersection(content_terms))
    
    def _find_matched_terms(self, query_terms: List[str], content_terms: List[str]) -> List[str]:
        """Find matched terms between query and content term lists"""
        query_set = set(query_terms)
        content_set = set(content_terms)
        
        return list(query_set.intersection(content_set))
    
    def get_search_suggestions(self, bookmarks: List[Dict[str, Any]], limit: int = 5) -> List[str]:
        """Generate search suggestions based on bookmark content"""
        if not bookmarks:
            return []
        
        # Extract common terms and phrases
        all_terms = []
        for bookmark in bookmarks:
            content = f"{bookmark.get('title', '')} {bookmark.get('content', '')}"
            terms = self._tokenize(content.lower())
            all_terms.extend(terms)
        
        # Get most common terms
        term_counts = Counter(all_terms)
        common_terms = [term for term, count in term_counts.most_common(20) if count > 1]
        
        # Generate suggestions
        suggestions = []
        
        # Add some generic helpful queries
        generic_suggestions = [
            "How to improve productivity?",
            "Meeting notes and action items",
            "Project planning and ideas",
            "Important deadlines and dates",
            "Financial advice and tips"
        ]
        
        suggestions.extend(generic_suggestions[:3])
        
        # Add term-based suggestions
        if common_terms:
            for i in range(0, min(len(common_terms), 4), 2):
                if i + 1 < len(common_terms):
                    suggestion = f"{common_terms[i]} and {common_terms[i+1]}"
                    suggestions.append(suggestion)
        
        return suggestions[:limit]

# Global instance
semantic_search_service = SemanticSearchService()