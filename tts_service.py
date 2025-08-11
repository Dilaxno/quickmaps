"""
Text-to-Speech Service with multiple backend support
Provides TTS functionality for generated notes using various TTS engines
"""

import os
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Setup logging
logger = logging.getLogger(__name__)

class TTSService:
    """Text-to-Speech service with multiple backend support"""
    
    def __init__(self):
        self.pipeline = None
        self.backend = None
        self.model_name = "gTTS"
        self.voice = "en-us"  # Default to American English for gTTS
        self.is_initialized = False
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.available_backends = []
        
    def _check_available_backends(self):
        """Check which TTS backends are available"""
        self.available_backends = []
        
        # Check for gTTS (preferred - Google's reliable online TTS)
        try:
            import gtts
            self.available_backends.append("gtts")
            logger.info("✅ gTTS backend available")
        except ImportError as e:
            logger.debug(f"gTTS not available - missing dependency: {e}")
        except Exception as e:
            logger.debug(f"gTTS check failed: {e}")
        
        # Check for pyttsx3 (offline, cross-platform)
        try:
            import pyttsx3
            self.available_backends.append("pyttsx3")
            logger.info("✅ pyttsx3 backend available")
        except ImportError:
            logger.debug("pyttsx3 not available")
        
        logger.info(f"Available TTS backends: {self.available_backends}")
        return self.available_backends

    def initialize(self):
        """Initialize the TTS service with the best available backend"""
        try:
            # Check available backends
            self._check_available_backends()
            
            if not self.available_backends:
                raise Exception("No TTS backends available. Please install gtts, pyttsx3, or other compatible TTS libraries.")
            
            # Try to initialize backends in order of preference (gTTS first)
            if "gtts" in self.available_backends:
                self._initialize_gtts()
            elif "pyttsx3" in self.available_backends:
                self._initialize_pyttsx3()
            else:
                raise Exception("No compatible TTS backend found")
            
            self.is_initialized = True
            logger.info(f"✅ TTS service initialized successfully with {self.backend} backend")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize TTS service: {e}")
            self.is_initialized = False
            raise

    def _initialize_pyttsx3(self):
        """Initialize pyttsx3 backend"""
        import pyttsx3
        self.pipeline = pyttsx3.init()
        self.backend = "pyttsx3"
        
        # Configure voice settings
        voices = self.pipeline.getProperty('voices')
        if voices:
            # Try to use a female voice if available
            for voice in voices:
                if 'female' in voice.name.lower() or 'zira' in voice.name.lower():
                    self.pipeline.setProperty('voice', voice.id)
                    break
        
        # Set speech rate and volume
        self.pipeline.setProperty('rate', 180)  # Speed of speech
        self.pipeline.setProperty('volume', 0.9)  # Volume level (0.0 to 1.0)
        
        logger.info("pyttsx3 TTS engine initialized")

    def _initialize_gtts(self):
        """Initialize gTTS backend"""
        # gTTS doesn't need initialization, just import check
        import gtts
        self.backend = "gtts"
        # Set default to American English
        self.voice = "en-us"
        logger.info("gTTS backend initialized with American English voice")


    
    def is_available(self) -> bool:
        """Check if TTS service is available"""
        if self.backend in ["gtts"]:
            # gTTS doesn't need special pipeline checks
            return self.is_initialized
        else:
            return self.is_initialized and self.pipeline is not None
    
    async def _generate_speech_async(self, text: str, output_path: str) -> Dict[str, Any]:
        """Generate speech from text (asynchronous)"""
        try:
            if not self.is_available():
                raise Exception("TTS service not initialized")
            
            # Clean text for better TTS output
            text = self._clean_text_for_tts(text)
            
            # Limit text length to prevent memory issues
            max_length = 5000  # Adjust based on backend capabilities
            if len(text) > max_length:
                text = text[:max_length] + "..."
                logger.warning(f"Text truncated to {max_length} characters for TTS")
            
            logger.info(f"Generating speech for {len(text)} characters using {self.backend} backend")
            
            if self.backend == "gtts":
                return self._generate_with_gtts(text, output_path)
            elif self.backend == "pyttsx3":
                return self._generate_with_pyttsx3(text, output_path)
            else:
                raise Exception(f"Unknown backend: {self.backend}")
            
        except Exception as e:
            logger.error(f"❌ TTS generation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _generate_speech_sync(self, text: str, output_path: str) -> Dict[str, Any]:
        """Generate speech from text (synchronous for non-async backends)"""
        try:
            if not self.is_available():
                raise Exception("TTS service not initialized")
            
            # Clean text for better TTS output
            text = self._clean_text_for_tts(text)
            
            # Limit text length to prevent memory issues
            max_length = 5000  # Adjust based on backend capabilities
            if len(text) > max_length:
                text = text[:max_length] + "..."
                logger.warning(f"Text truncated to {max_length} characters for TTS")
            
            logger.info(f"Generating speech for {len(text)} characters using {self.backend} backend")
            
            if self.backend == "pyttsx3":
                return self._generate_with_pyttsx3(text, output_path)
            elif self.backend == "gtts":
                return self._generate_with_gtts(text, output_path)
            else:
                raise Exception(f"Sync generation not supported for backend: {self.backend}")
            
        except Exception as e:
            logger.error(f"❌ TTS generation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _generate_with_pyttsx3(self, text: str, output_path: str) -> Dict[str, Any]:
        """Generate speech using pyttsx3"""
        try:
            # pyttsx3 saves to file directly
            self.pipeline.save_to_file(text, output_path)
            self.pipeline.runAndWait()
            
            # Get file size
            file_size = os.path.getsize(output_path)
            
            # Estimate duration (rough calculation)
            words = len(text.split())
            estimated_duration = words / 3  # Assume ~3 words per second
            
            return {
                "success": True,
                "audio_path": output_path,
                "duration": estimated_duration,
                "sample_rate": 22050,  # pyttsx3 default
                "file_size": file_size,
                "text_length": len(text),
                "backend": "pyttsx3"
            }
            
        except Exception as e:
            raise Exception(f"pyttsx3 generation failed: {e}")

    def _generate_with_gtts(self, text: str, output_path: str) -> Dict[str, Any]:
        """Generate speech using gTTS"""
        try:
            from gtts import gTTS
            
            # Create gTTS object
            tts = gTTS(text=text, lang='en', slow=False)
            
            # Save to file
            tts.save(output_path)
            
            # Get file size
            file_size = os.path.getsize(output_path)
            
            # Estimate duration (rough calculation)
            words = len(text.split())
            estimated_duration = words / 2.5  # gTTS is typically faster
            
            return {
                "success": True,
                "audio_path": output_path,
                "duration": estimated_duration,
                "sample_rate": 24000,  # gTTS typical
                "file_size": file_size,
                "text_length": len(text),
                "backend": "gtts"
            }
            
        except Exception as e:
            raise Exception(f"gTTS generation failed: {e}")


    
    async def generate_speech(self, text: str, output_dir: str = None) -> Dict[str, Any]:
        """Generate speech from text (async)"""
        try:
            # Create output directory if not provided
            if output_dir is None:
                output_dir = tempfile.gettempdir()
            
            # Ensure output directory exists
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename
            audio_id = str(uuid.uuid4())
            output_path = os.path.join(output_dir, f"tts_{audio_id}.wav")
            
            # Run TTS generation in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._generate_speech_sync,
                text,
                output_path
            )
            
            if result["success"]:
                result["audio_id"] = audio_id
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Async TTS generation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def generate_speech_for_notes(self, notes_content: str, job_id: str, output_dir: str) -> Dict[str, Any]:
        """Generate speech specifically for notes content"""
        try:
            # Clean up notes content for better TTS
            cleaned_text = self._clean_text_for_tts(notes_content)
            
            # Generate filename based on job_id
            output_path = os.path.join(output_dir, f"{job_id}_notes_audio.wav")
            
            # Run TTS generation
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._generate_speech_sync,
                cleaned_text,
                output_path
            )
            
            if result["success"]:
                result["job_id"] = job_id
                result["cleaned_text_length"] = len(cleaned_text)
                result["original_text_length"] = len(notes_content)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Notes TTS generation failed for job {job_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "job_id": job_id
            }
    
    def _clean_text_for_tts(self, text: str) -> str:
        """Clean text content for better TTS output with voice delays"""
        import re
        
        # First, identify and mark titles/headers for special treatment
        lines = text.split('\n')
        processed_lines = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # Check if this line looks like a title/header
            is_title = False
            
            # Pattern 1: Markdown headers (# ## ### etc.)
            if re.match(r'^#{1,6}\s+', line):
                is_title = True
                line = re.sub(r'^#{1,6}\s+', '', line)  # Remove markdown
                
            # Pattern 2: Section titles (Section X:, X., etc.)
            elif re.match(r'^(Section\s+\d+:|[IVX]+\.|[A-Z]\.|[0-9]+\.)\s*', line):
                is_title = True
                
            # Pattern 3: Lines ending with colon (likely titles)
            elif line.endswith(':') and len(line.split()) <= 8:
                is_title = True
                
            # Pattern 4: Short lines that are all caps or title case
            elif (len(line.split()) <= 6 and 
                  (line.isupper() or line.istitle()) and 
                  not line.endswith('.') and 
                  not line.endswith('!')):
                is_title = True
            
            # Add appropriate delays for titles
            if is_title:
                # Add longer pause after titles with comma and period
                if not line.endswith('.') and not line.endswith(','):
                    line = line + ',.'  # Comma for short pause, period for longer pause
                processed_lines.append(line)
            else:
                processed_lines.append(line)
        
        # Rejoin the processed lines
        text = '\n'.join(processed_lines)
        
        # Remove remaining markdown formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Italic
        text = re.sub(r'`([^`]+)`', r'\1', text)  # Inline code
        text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)  # Code blocks
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Links
        
        # Clean up bullet points and lists with pauses
        text = re.sub(r'^\s*[\*\-\+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        
        # Remove duplicate section titles
        text = self._remove_duplicate_titles(text)
        
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        
        # Add strategic pauses for better speech flow
        # Double newlines become longer pauses
        text = text.replace('\n\n', '... ')  # Three dots for longer pause
        
        # Single newlines become shorter pauses
        text = text.replace('\n', ', ')  # Comma for shorter pause
        
        # Add pauses after sentences that don't end with punctuation
        text = re.sub(r'([a-zA-Z0-9])\s+([A-Z])', r'\1. \2', text)
        
        # Clean up excessive punctuation but preserve intentional pauses
        text = re.sub(r'\.{4,}', '...', text)  # Max 3 dots
        text = re.sub(r',,+', ',', text)  # Remove multiple commas
        text = re.sub(r'\s+', ' ', text)  # Normalize spaces
        text = re.sub(r'\s+([,.!?])', r'\1', text)  # Remove space before punctuation
        
        # Ensure proper spacing after punctuation
        text = re.sub(r'([,.!?])([A-Za-z])', r'\1 \2', text)
        
        return text.strip()
    
    def _remove_duplicate_titles(self, text: str) -> str:
        """Remove duplicate section titles that appear consecutively"""
        import re
        
        # Split text into sentences for processing
        sentences = re.split(r'[.!?]+', text)
        cleaned_sentences = []
        
        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence:
                continue
            
            # Check if this sentence looks like a section title
            # Pattern: "Section X: Title" or "X. Title" or just "Title:"
            section_patterns = [
                r'^Section\s+\d+:\s*(.+)',  # "Section 2: Title"
                r'^\d+\.\s*(.+)',           # "2. Title"
                r'^(.+):\s*$',              # "Title:"
                r'^(.+)\s*-\s*$',           # "Title -"
            ]
            
            current_title = None
            for pattern in section_patterns:
                match = re.match(pattern, sentence, re.IGNORECASE)
                if match:
                    current_title = match.group(1).strip()
                    break
            
            # If we found a title, check if the next sentence starts with the same title
            if current_title and i + 1 < len(sentences):
                next_sentence = sentences[i + 1].strip()
                
                # Check if next sentence starts with the same title
                title_variations = [
                    current_title,
                    current_title.rstrip(':'),
                    current_title.rstrip('-'),
                    current_title.rstrip('.'),
                ]
                
                duplicate_found = False
                for variation in title_variations:
                    if variation and next_sentence.lower().startswith(variation.lower()):
                        # Found duplicate - skip adding the title sentence
                        duplicate_found = True
                        logger.debug(f"Removed duplicate title: '{sentence}' (next sentence starts with same title)")
                        break
                
                if duplicate_found:
                    continue
            
            cleaned_sentences.append(sentence)
        
        # Rejoin sentences
        result = '. '.join(cleaned_sentences)
        
        # Additional cleanup for common duplicate patterns
        # Remove patterns like "Title: Title, content..." or "Title - Title: content"
        result = re.sub(r'([^.!?:\-]+):\s*\1,?\s*', r'\1: ', result, flags=re.IGNORECASE)
        result = re.sub(r'([^.!?:\-]+)\s*-\s*\1:\s*', r'\1: ', result, flags=re.IGNORECASE)
        
        # Remove patterns like "Section X Title Title content"
        result = re.sub(r'\b(\w+(?:\s+\w+){0,4})\s+\1\b', r'\1', result, flags=re.IGNORECASE)
        
        # Remove patterns where title appears twice with different punctuation
        # e.g., "Title - Title:" -> "Title:"
        result = re.sub(r'([^.!?]+?)\s*[-:]\s*\1\s*:', r'\1:', result, flags=re.IGNORECASE)
        
        return result
    
    def get_supported_formats(self) -> list:
        """Get list of supported audio formats"""
        if self.backend == "gtts":
            return ["mp3", "wav"]  # gTTS primarily generates MP3
        return ["wav", "mp3", "flac"]
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the TTS service"""
        info = {
            "backend": self.backend,
            "available_backends": self.available_backends,
            "is_available": self.is_available(),
            "supported_formats": self.get_supported_formats(),
            "max_text_length": 5000,
            "sample_rate": 24000
        }
        
        if self.backend == "gtts":
            info.update({
                "model_name": "Google Text-to-Speech",
                "voice": self.voice,
                "description": "Google's cloud-based text-to-speech service",
                "license": "Google"
            })
        elif self.backend == "pyttsx3":
            info.update({
                "model_name": "pyttsx3 (System TTS)",
                "description": "Cross-platform offline text-to-speech"
            })
        elif self.backend == "gtts":
            info.update({
                "model_name": "Google Text-to-Speech",
                "description": "Google's online text-to-speech service"
            })
        
        return info
    
    def set_voice(self, voice: str) -> bool:
        """Set voice/language for TTS (gTTS backend only)"""
        if self.backend == "gtts":
            self.voice = voice
            logger.info(f"Language set to: {voice}")
            return True
        else:
            logger.warning(f"Voice setting not supported for {self.backend} backend")
            return False
    
    def get_available_voices(self) -> list:
        """Get list of available voices/languages"""
        if self.backend == "gtts":
            # Popular gTTS languages
            return [
                "en",      # English
                "en-us",   # English (US)
                "en-uk",   # English (UK)
                "en-au",   # English (Australia)
                "es",      # Spanish
                "fr",      # French
                "de",      # German
                "it",      # Italian
                "pt",      # Portuguese
                "ru",      # Russian
                "ja",      # Japanese
                "ko",      # Korean
                "zh",      # Chinese
            ]
        return []

# Global TTS service instance
tts_service = TTSService()

# Initialize on import (optional - can be done lazily)
try:
    # Check available backends without initializing
    available_backends = tts_service._check_available_backends()
    if available_backends:
        logger.info(f"TTS service ready with backends: {available_backends}")
    else:
        logger.warning("No TTS backends available. Install gtts (recommended) or pyttsx3.")
    
    # Don't auto-initialize to avoid startup delays
    # tts_service.initialize()
except Exception as e:
    logger.warning(f"Error checking TTS backends: {e}")