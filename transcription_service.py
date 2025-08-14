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



    def _transcribe_with_deepgram(self, audio_path: str) -> Dict[str, Any]:
        """Call Deepgram prerecorded transcription with whisper-large"""
        try:
            from deepgram import DeepgramClient, PrerecordedOptions, FileSource
        except Exception as e:
            raise Exception(
                "deepgram-sdk is not installed. Please add 'deepgram-sdk' to requirements and pip install it."
            ) from e

        try:
            client = DeepgramClient(DEEPGRAM_API_KEY) if DEEPGRAM_API_KEY else DeepgramClient()

            with open(audio_path, 'rb') as f:
                source: FileSource = {"buffer": f.read()}

            options = PrerecordedOptions(
                model=DEEPGRAM_MODEL or "whisper-large",
                smart_format=True,
                punctuate=True,
                paragraphs=True,
                utterances=False,
                diarize=False,
            )

            resp = client.listen.rest.v("1").transcribe_file(source, options)
            # Deepgram JSON has results in resp['results']['channels'][0]['alternatives'][0]
            alt = resp.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0]
            text = alt.get('transcript', '')
            language = alt.get('language', 'en')

            # Build segments from words if available
            segments = []
            words = alt.get('words') or []
            if words:
                # group words into segments by small gaps
                current = {"start": words[0].get('start', 0), "end": words[0].get('end', 0), "text": words[0].get('word', '')}
                for w in words[1:]:
                    gap = w.get('start', 0) - current["end"]
                    if gap > 0.6:  # new segment if pause is bigger than 600ms
                        segments.append(current)
                        current = {"start": w.get('start', 0), "end": w.get('end', 0), "text": w.get('word', '')}
                    else:
                        current["end"] = w.get('end', current["end"])
                        current["text"] += (" " + w.get('word', ''))
                if current:
                    segments.append(current)

            return {"text": text, "segments": segments, "language": language}
        except Exception as e:
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