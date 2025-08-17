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
        
        # Check for Deepgram Aura1 TTS (preferred - high quality neural TTS)
        try:
            from config import DEEPGRAM_API_KEY
            logger.debug(f"Checking Deepgram API key: {'***' if DEEPGRAM_API_KEY else 'None'}")
            if DEEPGRAM_API_KEY:
                from deepgram import DeepgramClient
                self.available_backends.append("deepgram_aura1")
                logger.info("✅ Deepgram Aura1 TTS backend available")
            else:
                logger.info("⚠️ Deepgram TTS not available - no API key configured")
        except ImportError as e:
            logger.info(f"⚠️ Deepgram TTS not available - missing dependency: {e}")
        except Exception as e:
            logger.info(f"⚠️ Deepgram TTS check failed: {e}")
        
        # Check for gTTS (fallback - Google's reliable online TTS)
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
            
            # Try to initialize backends in order of preference (Deepgram Aura1 first)
            if "deepgram_aura1" in self.available_backends:
                self._initialize_deepgram_aura1()
            elif "gtts" in self.available_backends:
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

    def _initialize_deepgram_aura1(self):
        """Initialize Deepgram Aura1 TTS backend"""
        from deepgram import DeepgramClient
        from config import DEEPGRAM_API_KEY
        
        self.pipeline = DeepgramClient(DEEPGRAM_API_KEY)
        self.backend = "deepgram_aura1"
        self.voice = "aura-asteria-en"  # Default to Asteria voice (female, American English)
        logger.info("Deepgram Aura1 TTS backend initialized with Asteria voice")

    def _initialize_gtts(self):
        """Initialize gTTS backend"""
        # gTTS doesn't need initialization, just import check
        import gtts
        self.backend = "gtts"
        # Set default to American English
        self.voice = "en-us"
        logger.info("gTTS backend initialized with American English voice")

    def set_voice(self, voice_name: str) -> bool:
        """Set the voice for TTS generation"""
        try:
            if self.backend == "deepgram_aura1":
                # Available Deepgram Aura voices
                available_voices = [
                    "aura-asteria-en",   # female, American English (default)
                    "aura-luna-en",      # female, American English
                    "aura-stella-en",    # female, American English
                    "aura-athena-en",    # female, British English
                    "aura-hera-en",      # female, American English
                    "aura-orion-en",     # male, American English
                    "aura-arcas-en",     # male, American English
                    "aura-perseus-en",   # male, American English
                    "aura-angus-en",     # male, Irish English
                    "aura-orpheus-en",   # male, American English
                    "aura-helios-en",    # male, British English
                    "aura-zeus-en"       # male, American English
                ]
                
                if voice_name in available_voices:
                    self.voice = voice_name
                    logger.info(f"✅ Deepgram voice set to: {voice_name}")
                    return True
                else:
                    logger.warning(f"⚠️ Voice '{voice_name}' not available for Deepgram. Available: {available_voices}")
                    return False
                    
            elif self.backend == "gtts":
                # gTTS language codes
                if voice_name in ["en-us", "en-uk", "en-au", "en-ca", "en-in"]:
                    self.voice = voice_name
                    logger.info(f"✅ gTTS voice set to: {voice_name}")
                    return True
                else:
                    logger.warning(f"⚠️ Voice '{voice_name}' not supported for gTTS")
                    return False
                    
            elif self.backend == "pyttsx3":
                # pyttsx3 uses system voices
                voices = self.pipeline.getProperty('voices')
                for voice in voices:
                    if voice_name.lower() in voice.name.lower():
                        self.pipeline.setProperty('voice', voice.id)
                        self.voice = voice_name
                        logger.info(f"✅ pyttsx3 voice set to: {voice_name}")
                        return True
                logger.warning(f"⚠️ Voice '{voice_name}' not found in pyttsx3")
                return False
                
            else:
                logger.warning(f"⚠️ Voice setting not supported for backend: {self.backend}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to set voice '{voice_name}': {e}")
            return False

    def get_available_voices(self) -> list:
        """Get list of available voices for current backend"""
        try:
            if self.backend == "deepgram_aura1":
                return [
                    {"id": "aura-asteria-en", "name": "Asteria", "gender": "female", "accent": "American English"},
                    {"id": "aura-luna-en", "name": "Luna", "gender": "female", "accent": "American English"},
                    {"id": "aura-stella-en", "name": "Stella", "gender": "female", "accent": "American English"},
                    {"id": "aura-athena-en", "name": "Athena", "gender": "female", "accent": "British English"},
                    {"id": "aura-hera-en", "name": "Hera", "gender": "female", "accent": "American English"},
                    {"id": "aura-orion-en", "name": "Orion", "gender": "male", "accent": "American English"},
                    {"id": "aura-arcas-en", "name": "Arcas", "gender": "male", "accent": "American English"},
                    {"id": "aura-perseus-en", "name": "Perseus", "gender": "male", "accent": "American English"},
                    {"id": "aura-angus-en", "name": "Angus", "gender": "male", "accent": "Irish English"},
                    {"id": "aura-orpheus-en", "name": "Orpheus", "gender": "male", "accent": "American English"},
                    {"id": "aura-helios-en", "name": "Helios", "gender": "male", "accent": "British English"},
                    {"id": "aura-zeus-en", "name": "Zeus", "gender": "male", "accent": "American English"}
                ]
            elif self.backend == "gtts":
                return [
                    {"id": "en-us", "name": "American English", "gender": "neutral", "accent": "American"},
                    {"id": "en-uk", "name": "British English", "gender": "neutral", "accent": "British"},
                    {"id": "en-au", "name": "Australian English", "gender": "neutral", "accent": "Australian"},
                    {"id": "en-ca", "name": "Canadian English", "gender": "neutral", "accent": "Canadian"},
                    {"id": "en-in", "name": "Indian English", "gender": "neutral", "accent": "Indian"}
                ]
            elif self.backend == "pyttsx3":
                voices = self.pipeline.getProperty('voices')
                return [{"id": voice.id, "name": voice.name, "gender": "unknown", "accent": "system"} for voice in voices]
            else:
                return []
        except Exception as e:
            logger.error(f"❌ Failed to get available voices: {e}")
            return []

    
    def is_available(self) -> bool:
        """Check if TTS service is available"""
        if self.backend in ["gtts"]:
            # gTTS doesn't need special pipeline checks
            return self.is_initialized
        elif self.backend == "deepgram_aura1":
            # Deepgram needs client and API key
            return self.is_initialized and self.pipeline is not None
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
            if self.backend == "deepgram_aura1":
                max_length = 10000  # Deepgram can handle longer texts with chunking
            else:
                max_length = 5000   # Other backends
                
            if len(text) > max_length:
                text = text[:max_length] + "..."
                logger.warning(f"Text truncated to {max_length} characters for TTS")
            
            logger.info(f"Generating speech for {len(text)} characters using {self.backend} backend")
            
            if self.backend == "deepgram_aura1":
                return self._generate_with_deepgram_aura1(text, output_path)
            elif self.backend == "gtts":
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
            if self.backend == "deepgram_aura1":
                max_length = 10000  # Deepgram can handle longer texts with chunking
            else:
                max_length = 5000   # Other backends
                
            if len(text) > max_length:
                text = text[:max_length] + "..."
                logger.warning(f"Text truncated to {max_length} characters for TTS")
            
            logger.info(f"Generating speech for {len(text)} characters using {self.backend} backend")
            
            if self.backend == "deepgram_aura1":
                return self._generate_with_deepgram_aura1(text, output_path)
            elif self.backend == "pyttsx3":
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
                "backend": "pyttsx3",
                "mime_type": "audio/wav",
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
                "backend": "gtts",
                "mime_type": "audio/mpeg",
            }
            
        except Exception as e:
            raise Exception(f"gTTS generation failed: {e}")

    def _generate_with_deepgram_aura1(self, text: str, output_path: str) -> Dict[str, Any]:
        """Generate speech using Deepgram Aura1 TTS with text chunking for long texts"""
        try:
            import httpx
            import wave
            import io
            from config import DEEPGRAM_API_KEY
            
            logger.info(f"🎤 Generating TTS with Deepgram Aura1 voice: {self.voice}")
            logger.info(f"📝 Text length: {len(text)} characters")
            
            # Deepgram TTS has a 2000 character limit per request
            max_chunk_size = 1900  # Leave some buffer
            
            if len(text) <= max_chunk_size:
                # Single request for short text
                return self._generate_single_deepgram_chunk(text, output_path)
            else:
                # Split text into chunks and concatenate audio
                return self._generate_chunked_deepgram_audio(text, output_path, max_chunk_size)
                
        except Exception as e:
            logger.error(f"❌ Deepgram Aura1 TTS generation failed: {e}")
            raise Exception(f"Deepgram Aura1 TTS generation failed: {e}")

    def _generate_single_deepgram_chunk(self, text: str, output_path: str) -> Dict[str, Any]:
        """Generate speech for a single chunk of text"""
        import httpx
        from config import DEEPGRAM_API_KEY
        
        # Deepgram TTS API endpoint
        url = "https://api.deepgram.com/v1/speak"
        
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Query parameters (model, encoding, sample_rate go here)
        params = {
            "model": self.voice,         # Use configured voice
            "encoding": "linear16",      # WAV format
            "sample_rate": 24000        # High quality sample rate
        }
        
        # JSON payload (only text goes here)
        payload = {
            "text": text
        }
        
        logger.info(f"🔍 Sending single chunk to Deepgram TTS ({len(text)} chars)")
        
        # Use timeout for the request
        timeout = httpx.Timeout(60.0)  # 1 minute timeout
        
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, params=params, json=payload)
            
            if response.status_code != 200:
                error_text = response.text[:500]
                raise Exception(f"Deepgram TTS API error {response.status_code}: {error_text}")
            
            # Save the audio data to file
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            # Get file size
            file_size = os.path.getsize(output_path)
            
            # Estimate duration (rough calculation)
            words = len(text.split())
            estimated_duration = words / 2.8  # Aura voices are natural speed
            
            logger.info(f"✅ Deepgram Aura1 TTS completed. File size: {file_size} bytes")
            
            return {
                "success": True,
                "audio_path": output_path,
                "duration": estimated_duration,
                "sample_rate": 24000,
                "file_size": file_size,
                "text_length": len(text),
                "backend": "deepgram_aura1",
                "voice": self.voice,
                "chunks": 1,
                "mime_type": "audio/wav",
            }

    def _generate_chunked_deepgram_audio(self, text: str, output_path: str, max_chunk_size: int) -> Dict[str, Any]:
        """Generate speech for long text by chunking and concatenating audio"""
        import httpx
        import wave
        import tempfile
        from config import DEEPGRAM_API_KEY
        
        # Split text into chunks intelligently (at sentence boundaries when possible)
        chunks = self._split_text_into_chunks(text, max_chunk_size)
        logger.info(f"📦 Split text into {len(chunks)} chunks")
        
        # Generate audio for each chunk
        temp_files = []
        total_duration = 0
        
        try:
            for i, chunk in enumerate(chunks):
                logger.info(f"🎤 Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
                
                # Create temporary file for this chunk
                temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
                os.close(temp_fd)
                temp_files.append(temp_path)
                
                # Generate audio for this chunk
                chunk_result = self._generate_single_deepgram_chunk(chunk, temp_path)
                if not chunk_result["success"]:
                    raise Exception(f"Failed to generate audio for chunk {i+1}")
                
                total_duration += chunk_result["duration"]
            
            # Concatenate all audio files
            logger.info(f"🔗 Concatenating {len(temp_files)} audio chunks")
            self._concatenate_wav_files(temp_files, output_path)
            
            # Get final file size
            file_size = os.path.getsize(output_path)
            
            logger.info(f"✅ Deepgram Aura1 chunked TTS completed. File size: {file_size} bytes, Duration: {total_duration:.1f}s")
            
            return {
                "success": True,
                "audio_path": output_path,
                "duration": total_duration,
                "sample_rate": 24000,
                "file_size": file_size,
                "text_length": len(text),
                "backend": "deepgram_aura1",
                "voice": self.voice,
                "chunks": len(chunks),
                "mime_type": "audio/wav",
            }
            
        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file {temp_file}: {e}")

    def _split_text_into_chunks(self, text: str, max_size: int) -> list:
        """Split text into chunks at sentence boundaries when possible"""
        import re
        
        if len(text) <= max_size:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Split by sentences first
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        for sentence in sentences:
            # If adding this sentence would exceed the limit
            if len(current_chunk) + len(sentence) + 1 > max_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    # Single sentence is too long, split by words
                    if len(sentence) > max_size:
                        word_chunks = self._split_long_sentence(sentence, max_size)
                        chunks.extend(word_chunks[:-1])
                        current_chunk = word_chunks[-1]
                    else:
                        current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

    def _split_long_sentence(self, sentence: str, max_size: int) -> list:
        """Split a long sentence by words"""
        words = sentence.split()
        chunks = []
        current_chunk = ""
        
        for word in words:
            if len(current_chunk) + len(word) + 1 > max_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = word
                else:
                    # Single word is too long, just truncate
                    chunks.append(word[:max_size])
                    current_chunk = ""
            else:
                if current_chunk:
                    current_chunk += " " + word
                else:
                    current_chunk = word
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

    def _concatenate_wav_files(self, input_files: list, output_file: str):
        """Concatenate multiple WAV files into one"""
        import wave
        
        if not input_files:
            raise Exception("No input files to concatenate")
        
        # Open the first file to get parameters
        with wave.open(input_files[0], 'rb') as first_wav:
            params = first_wav.getparams()
            frames = first_wav.readframes(first_wav.getnframes())
        
        # Open output file for writing
        with wave.open(output_file, 'wb') as output_wav:
            output_wav.setparams(params)
            output_wav.writeframes(frames)
            
            # Append remaining files
            for input_file in input_files[1:]:
                with wave.open(input_file, 'rb') as wav_file:
                    # Verify parameters match
                    if wav_file.getparams()[:4] != params[:4]:
                        logger.warning(f"WAV parameters mismatch in {input_file}, attempting to concatenate anyway")
                    
                    frames = wav_file.readframes(wav_file.getnframes())
                    output_wav.writeframes(frames)

    
    async def generate_speech(self, text: str, output_dir: str = None) -> Dict[str, Any]:
        """Generate speech from text (async)"""
        try:
            # Create output directory if not provided
            if output_dir is None:
                output_dir = tempfile.gettempdir()
            
            # Ensure output directory exists
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename based on backend/container
            audio_id = str(uuid.uuid4())
            ext = 'mp3' if self.backend == 'gtts' else 'wav'
            output_path = os.path.join(output_dir, f"tts_{audio_id}.{ext}")
            
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
            
            # Generate filename based on job_id and backend
            ext = 'mp3' if self.backend == 'gtts' else 'wav'
            output_path = os.path.join(output_dir, f"{job_id}_notes_audio.{ext}")
            
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
        """Clean text content for natural TTS output without artificial pauses"""
        import re
        
        # Remove markdown formatting but keep the text natural
        lines = text.split('\n')
        processed_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Remove markdown headers but keep the text as-is
            line = re.sub(r'^#{1,6}\s+', '', line)  # Remove markdown headers
            
            # Remove list markers but keep the content
            line = re.sub(r'^\s*[\*\-\+]\s+', '', line)  # Remove bullet points
            line = re.sub(r'^\s*\d+\.\s+', '', line)  # Remove numbered lists
            
            # Keep the line as natural text
            processed_lines.append(line)
        
        # Rejoin the processed lines with natural spacing
        text = '\n'.join(processed_lines)
        
        # Remove remaining markdown formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Italic
        text = re.sub(r'`([^`]+)`', r'\1', text)  # Inline code
        text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)  # Code blocks
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Links
        
        # Remove duplicate section titles
        text = self._remove_duplicate_titles(text)
        
        # Clean up whitespace naturally
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Multiple blank lines to double
        text = re.sub(r'\n\n', '. ', text)  # Double newlines become natural sentence breaks
        text = re.sub(r'\n', ' ', text)  # Single newlines become spaces
        
        # Only add periods where sentences clearly end without punctuation
        # But be very conservative to avoid breaking up titles
        text = re.sub(r'([a-z])\s+([A-Z][a-z]{2,})', r'\1. \2', text)  # Only if next word is clearly a new sentence
        
        # Clean up spacing
        text = re.sub(r'\s+', ' ', text)  # Normalize spaces
        text = re.sub(r'\s+([.!?])', r'\1', text)  # Remove space before punctuation
        
        # Ensure proper spacing after punctuation
        text = re.sub(r'([.!?])([A-Za-z])', r'\1 \2', text)
        
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
        elif self.backend == "deepgram_aura1":
            info.update({
                "model_name": "Deepgram Aura1",
                "voice": self.voice,
                "description": "Deepgram's high-quality neural text-to-speech with Aura voices",
                "license": "Deepgram",
                "quality": "High (24kHz)"
            })
        elif self.backend == "pyttsx3":
            info.update({
                "model_name": "pyttsx3 (System TTS)",
                "description": "Cross-platform offline text-to-speech"
            })
        
        return info
    


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