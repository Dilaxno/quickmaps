"""
Transcription Service Module

Handles audio transcription using Whisper model.
"""

import logging
import torch
import whisper
from config import WHISPER_MODEL

# Determine the device for Whisper model
WHISPER_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

logger = logging.getLogger(__name__)

class TranscriptionService:
    """Service for handling audio transcription using Whisper"""
    
    def __init__(self):
        self.model = None
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the Whisper model"""
        try:
            logger.info(f"Loading Whisper model: {WHISPER_MODEL} on device: {WHISPER_DEVICE}")
            self.model = whisper.load_model(WHISPER_MODEL, device=WHISPER_DEVICE)
            logger.info("Whisper model loaded successfully!")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise
    
    def transcribe_audio(self, audio_path: str) -> dict:
        """
        Transcribe audio file using Whisper
        
        Args:
            audio_path (str): Path to the audio file
            
        Returns:
            dict: Transcription result containing text, segments, and language
            
        Raises:
            Exception: If transcription fails
        """
        try:
            if not self.model:
                raise Exception("Whisper model not initialized")
                
            result = self.model.transcribe(audio_path)
            return {
                "text": result["text"],
                "segments": result["segments"],
                "language": result["language"]
            }
        except Exception as e:
            raise Exception(f"Transcription failed: {str(e)}")
    
    def is_available(self) -> bool:
        """Check if the transcription service is available"""
        return self.model is not None

# Global instance
transcription_service = TranscriptionService()