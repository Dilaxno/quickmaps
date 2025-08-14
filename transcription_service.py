"""
Transcription Service Module

Deepgram-only transcription (model: whisper-large by default).
"""

import json
import logging
from typing import Dict, Any

from config import (
    USE_DEEPGRAM,
    DEEPGRAM_API_KEY,
    DEEPGRAM_MODEL,
)

logger = logging.getLogger(__name__)

class TranscriptionService:
    """Service for handling audio transcription using Deepgram only"""

    def __init__(self):
        self.use_deepgram = USE_DEEPGRAM and bool(DEEPGRAM_API_KEY)
        if not self.use_deepgram:
            logger.warning("Deepgram not configured. Set USE_DEEPGRAM=true and provide DEEPGRAM_API_KEY.")
    
    def _build_segments_from_words(self, words):
        """Build segments from word-level timestamps"""
        segments = []
        if not words:
            return segments
            
        try:
            # Handle both object and dictionary word formats
            def get_word_attr(word, attr, default=0):
                if hasattr(word, attr):
                    return getattr(word, attr, default)
                elif isinstance(word, dict):
                    return word.get(attr, default)
                return default
            
            first_word = words[0]
            current = {
                "start": get_word_attr(first_word, 'start', 0),
                "end": get_word_attr(first_word, 'end', 0),
                "text": get_word_attr(first_word, 'word', '')
            }
            
            for w in words[1:]:
                w_start = get_word_attr(w, 'start', 0)
                w_end = get_word_attr(w, 'end', 0)
                w_word = get_word_attr(w, 'word', '')
                
                gap = w_start - current["end"]
                if gap > 0.6:  # new segment if pause is bigger than 600ms
                    segments.append(current)
                    current = {"start": w_start, "end": w_end, "text": w_word}
                else:
                    current["end"] = w_end
                    current["text"] += (" " + w_word)
            
            if current:
                segments.append(current)
                
        except Exception as e:
            logger.warning(f"⚠️ Error building segments from words: {e}")
            
        return segments



    def _transcribe_with_deepgram(self, audio_path: str) -> Dict[str, Any]:
        """Call Deepgram prerecorded transcription with whisper-large"""
        try:
            from deepgram import DeepgramClient, PrerecordedOptions, FileSource
        except Exception as e:
            raise Exception(
                "deepgram-sdk is not installed. Please add 'deepgram-sdk' to requirements and pip install it."
            ) from e

        try:
            logger.info(f"🎤 Starting Deepgram transcription with model: {DEEPGRAM_MODEL or 'whisper-large'}")
            client = DeepgramClient(DEEPGRAM_API_KEY) if DEEPGRAM_API_KEY else DeepgramClient()

            with open(audio_path, 'rb') as f:
                buffer_data = f.read()
                logger.info(f"📁 Audio file size: {len(buffer_data)} bytes")
                source: FileSource = {"buffer": buffer_data}

            options = PrerecordedOptions(
                model=DEEPGRAM_MODEL or "whisper-large",
                smart_format=True,
                punctuate=True,
                paragraphs=True,
                utterances=False,
                diarize=False,
            )
            
            logger.info("🔄 Sending request to Deepgram...")

            resp = client.listen.rest.v("1").transcribe_file(source, options)
            logger.info(f"📥 Received response from Deepgram. Type: {type(resp)}")
            
            # Handle both dictionary and object responses
            text = ''
            language = 'en'
            segments = []
            
            try:
                # Try object-style access first (newer SDK)
                if hasattr(resp, 'results') and resp.results:
                    channel = resp.results.channels[0] if resp.results.channels else None
                    if channel and channel.alternatives:
                        alt = channel.alternatives[0]
                        text = getattr(alt, 'transcript', '')
                        language = getattr(alt, 'detected_language', 'en') or 'en'
                        
                        # Build segments from words if available
                        words = getattr(alt, 'words', []) or []
                        segments = self._build_segments_from_words(words)
                        
                elif hasattr(resp, 'to_dict'):
                    # Try converting to dict if available
                    resp_dict = resp.to_dict()
                    alt = resp_dict.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0]
                    text = alt.get('transcript', '')
                    language = alt.get('detected_language', 'en') or 'en'
                    
                    words = alt.get('words', [])
                    segments = self._build_segments_from_words(words)
                    
                else:
                    # Fallback: try dictionary access (older SDK)
                    alt = resp.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0]
                    text = alt.get('transcript', '')
                    language = alt.get('detected_language', 'en') or 'en'
                    
                    words = alt.get('words', [])
                    segments = self._build_segments_from_words(words)
                    
            except Exception as parse_error:
                logger.warning(f"⚠️ Error parsing Deepgram response: {parse_error}")
                # Try to extract basic text at least
                try:
                    if hasattr(resp, 'results'):
                        text = str(resp.results.channels[0].alternatives[0].transcript)
                    else:
                        text = "Transcription completed but text extraction failed"
                except:
                    text = "Transcription failed to parse"

            logger.info(f"✅ Deepgram transcription completed. Text length: {len(text)} chars, Segments: {len(segments)}")
            return {"text": text, "segments": segments, "language": language}
            
        except Exception as e:
            logger.error(f"❌ Deepgram transcription failed: {str(e)}")
            logger.error(f"Response type: {type(resp) if 'resp' in locals() else 'No response'}")
            if 'resp' in locals():
                logger.error(f"Response attributes: {dir(resp)}")
            raise Exception(f"Deepgram transcription failed: {e}")

    def transcribe_audio(self, audio_path: str) -> Dict[str, Any]:
        """Transcribe audio using Deepgram"""
        if not self.use_deepgram:
            raise Exception("Deepgram is not configured. Set USE_DEEPGRAM=true and provide DEEPGRAM_API_KEY in .env")
        return self._transcribe_with_deepgram(audio_path)

    def is_available(self) -> bool:
        """Check if the transcription service is available"""
        return bool(self.use_deepgram)

# Global instance
transcription_service = TranscriptionService()