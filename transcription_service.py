"""
Transcription Service Module

Deepgram-only transcription (model: whisper-large by default).
"""

import json
import logging
import time
import os
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
        # Configure generous timeouts, especially for whisper-large
        try:
            self.deepgram_timeout = int(os.getenv("DEEPGRAM_TIMEOUT_SECONDS", "900"))  # total read/write timeout
        except Exception:
            self.deepgram_timeout = 900
        try:
            self.deepgram_connect_timeout = int(os.getenv("DEEPGRAM_CONNECT_TIMEOUT_SECONDS", "180"))
        except Exception:
            self.deepgram_connect_timeout = 60

        # Chunking configuration for long audio
        try:
            self.chunk_threshold_seconds = int(os.getenv("DEEPGRAM_CHUNK_THRESHOLD_SECONDS", "2400"))  # 40 min
        except Exception:
            self.chunk_threshold_seconds = 2400
        try:
            self.chunk_seconds = int(os.getenv("DEEPGRAM_CHUNK_SECONDS", "600"))  # 10 min per chunk
        except Exception:
            self.chunk_seconds = 600
        try:
            self.chunk_size_bytes_threshold = int(os.getenv("DEEPGRAM_CHUNK_SIZE_BYTES_THRESHOLD", str(150 * 1024 * 1024)))
        except Exception:
            self.chunk_size_bytes_threshold = 150 * 1024 * 1024
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

    def _transcribe_with_deepgram_http(self, audio_path: str) -> Dict[str, Any]:
        """Fallback method using direct HTTP requests to Deepgram API"""
        import httpx
        from pathlib import Path
        
        try:
            logger.info("🔄 Using HTTP fallback for Deepgram transcription...")
            
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            
            # Detect content type based on file extension
            file_ext = Path(audio_path).suffix.lower()
            content_type_map = {
                '.wav': 'audio/wav',
                '.mp3': 'audio/mpeg',
                '.m4a': 'audio/mp4',
                '.flac': 'audio/flac',
                '.ogg': 'audio/ogg',
                '.aac': 'audio/aac'
            }
            content_type = content_type_map.get(file_ext, 'audio/wav')
            
            headers = {
                'Authorization': f'Token {DEEPGRAM_API_KEY}',
                'Content-Type': content_type
            }
            
            params = {
                'model': DEEPGRAM_MODEL or 'whisper-large',
                'smart_format': 'true',
                'punctuate': 'true',
                'paragraphs': 'true',
                'utterances': 'false',
                'diarize': 'false'
            }
            
            logger.info(f"📡 Making HTTP request to Deepgram API (Content-Type: {content_type}) with timeouts: connect={self.deepgram_connect_timeout}s, read/write/pool={self.deepgram_timeout}s")
            
            # Use longer, configurable timeouts for HTTP request
            timeout = httpx.Timeout(
                connect=self.deepgram_connect_timeout,
                read=self.deepgram_timeout,
                write=self.deepgram_timeout,
                pool=self.deepgram_timeout,
            )
            
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    'https://api.deepgram.com/v1/listen',
                    headers=headers,
                    params=params,
                    content=audio_data
                )
                
                logger.info(f"📥 HTTP response status: {response.status_code}")
                
                if response.status_code != 200:
                    error_text = response.text[:500]  # Limit error text length
                    raise Exception(f"HTTP {response.status_code}: {error_text}")
                
                result = response.json()
                logger.info("✅ Successfully parsed JSON response")
                
                # Parse the JSON response
                alt = result.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0]
                text = alt.get('transcript', '')
                language = alt.get('detected_language', 'en') or 'en'
                
                words = alt.get('words', [])
                segments = self._build_segments_from_words(words)
                
                logger.info(f"✅ HTTP transcription completed. Text length: {len(text)} chars, Segments: {len(segments)}")
                return {"text": text, "segments": segments, "language": language}
                
        except Exception as e:
            logger.error(f"❌ HTTP fallback failed: {e}")
            raise

    def _transcribe_with_deepgram(self, audio_path: str) -> Dict[str, Any]:
        """Call Deepgram prerecorded transcription with whisper-large using SDK v4.x"""
        try:
            from deepgram import DeepgramClient, PrerecordedOptions, FileSource
        except Exception as e:
            raise Exception(
                "deepgram-sdk is not installed. Please add 'deepgram-sdk' to requirements and pip install it."
            ) from e

        try:
            logger.info(f"🎤 Starting Deepgram transcription with model: {DEEPGRAM_MODEL or 'whisper-large'}")
            
            # Create client - SDK v4.x uses different initialization
            client = DeepgramClient(DEEPGRAM_API_KEY)
            
            with open(audio_path, 'rb') as f:
                buffer_data = f.read()
                logger.info(f"📁 Audio file size: {len(buffer_data)} bytes")
                
                # Check file size and warn if very large
                file_size_mb = len(buffer_data) / (1024 * 1024)
                if file_size_mb > 100:
                    logger.warning(f"⚠️ Large audio file ({file_size_mb:.1f}MB) - transcription may take longer")

            # SDK v4.x options
            options = PrerecordedOptions(
                model=DEEPGRAM_MODEL or "whisper-large",
                smart_format=True,
                punctuate=True,
                paragraphs=True,
                utterances=False,
                diarize=False,
            )
            
            logger.info("🔄 Sending request to Deepgram...")

            # SDK v4.x API call
            payload = {"buffer": buffer_data}
            
            # Try transcription with retry logic
            max_retries = 5
            retry_count = 0
            response = None
            
            while retry_count < max_retries:
                try:
                    response = client.listen.prerecorded.v("1").transcribe_file(payload, options)
                    logger.info(f"📥 Received response from Deepgram. Type: {type(response)}")
                    break
                except Exception as retry_error:
                    retry_count += 1
                    if "timeout" in str(retry_error).lower() and retry_count < max_retries:
                        # Exponential backoff capped at 30s
                        delay = min(2 ** retry_count, 30)
                        logger.warning(f"⚠️ Timeout on attempt {retry_count}/{max_retries}, retrying in {delay}s...")
                        time.sleep(delay)
                        continue
                    else:
                        raise retry_error
            
            if response is None:
                raise Exception("Failed to get response from Deepgram after retries")
            
            # Parse response - SDK v4.x returns different structure
            text = ''
            language = 'en'
            segments = []
            
            try:
                # SDK v4.x response parsing
                if hasattr(response, 'results'):
                    results = response.results
                    if hasattr(results, 'channels') and results.channels:
                        channel = results.channels[0]
                        if hasattr(channel, 'alternatives') and channel.alternatives:
                            alt = channel.alternatives[0]
                            text = getattr(alt, 'transcript', '')
                            
                            # Get language
                            if hasattr(alt, 'detected_language'):
                                language = alt.detected_language or 'en'
                            elif hasattr(results, 'metadata') and hasattr(results.metadata, 'detected_language'):
                                language = results.metadata.detected_language or 'en'
                            
                            # Build segments from words if available
                            words = getattr(alt, 'words', []) or []
                            segments = self._build_segments_from_words(words)
                
                # Fallback: try to convert to dict if object access fails
                elif hasattr(response, 'to_dict'):
                    resp_dict = response.to_dict()
                    alt = resp_dict.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0]
                    text = alt.get('transcript', '')
                    language = alt.get('detected_language', 'en') or 'en'
                    words = alt.get('words', [])
                    segments = self._build_segments_from_words(words)
                
                # Last resort: try dictionary access
                else:
                    logger.warning("⚠️ Using fallback dictionary access for response")
                    alt = response['results']['channels'][0]['alternatives'][0]
                    text = alt.get('transcript', '')
                    language = alt.get('detected_language', 'en') or 'en'
                    words = alt.get('words', [])
                    segments = self._build_segments_from_words(words)
                    
            except Exception as parse_error:
                logger.warning(f"⚠️ Error parsing Deepgram response: {parse_error}")
                logger.warning(f"Response type: {type(response)}")
                logger.warning(f"Response dir: {dir(response)}")
                
                # Try to extract basic text at least
                try:
                    if hasattr(response, 'results'):
                        text = str(response.results.channels[0].alternatives[0].transcript)
                    else:
                        text = "Transcription completed but text extraction failed"
                except:
                    text = "Transcription failed to parse"

            logger.info(f"✅ Deepgram transcription completed. Text length: {len(text)} chars, Segments: {len(segments)}")
            return {"text": text, "segments": segments, "language": language}
            
        except Exception as e:
            logger.error(f"❌ Deepgram SDK transcription failed: {str(e)}")
            logger.error(f"Response type: {type(response) if 'response' in locals() else 'No response'}")
            
            # Check if it's a timeout error and try HTTP fallback
            if "timeout" in str(e).lower():
                logger.info("🔄 Attempting HTTP fallback due to timeout...")
                try:
                    return self._transcribe_with_deepgram_http(audio_path)
                except Exception as fallback_error:
                    logger.error(f"❌ HTTP fallback also failed: {fallback_error}")
                    raise Exception(f"Both SDK and HTTP methods failed. SDK: {e}, HTTP: {fallback_error}")
            
            raise Exception(f"Deepgram transcription failed: {e}")

    # Helper: get audio duration in seconds using pydub or ffprobe
    def _get_audio_duration_seconds(self, audio_path: str):
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception:
            pass
        try:
            import subprocess
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nokey=1:noprint_wrappers=1",
                audio_path,
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            dur = float(out.decode("utf-8", errors="ignore").strip())
            return dur if dur > 0 else None
        except Exception as e:
            logger.warning(f"Could not determine duration: {e}")
            return None

    # Helper: split audio into WAV chunks for robust decoding
    def _split_audio_to_chunks(self, audio_path: str, chunk_seconds: int):
        import tempfile, subprocess, shutil
        from pathlib import Path
        tmpdir = tempfile.mkdtemp(prefix="dg_chunks_")
        pattern = str(Path(tmpdir) / "chunk_%04d.wav")
        try:
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", audio_path,
                "-f", "segment", "-segment_time", str(chunk_seconds),
                "-ac", "1", "-ar", "16000",
                pattern,
            ]
            subprocess.check_call(cmd)
            files = sorted([str(p) for p in Path(tmpdir).glob("chunk_*.wav")])
            if not files:
                raise Exception("No chunks created by ffmpeg.")
            return files, tmpdir
        except Exception as e:
            logger.error(f"Chunking failed: {e}")
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise

    # Helper: single-file transcription with SDK + HTTP fallback
    def _transcribe_single(self, audio_path: str) -> Dict[str, Any]:
        try:
            return self._transcribe_with_deepgram(audio_path)
        except Exception as e:
            if "timeout" in str(e).lower() or "PrerecordedResponse" in str(e):
                logger.warning(f"⚠️ SDK method failed ({e}), trying HTTP fallback...")
                return self._transcribe_with_deepgram_http(audio_path)
            raise

    # Chunked transcription orchestrator
    def _transcribe_audio_chunked(self, audio_path: str, chunk_seconds: int) -> Dict[str, Any]:
        import shutil
        from pathlib import Path
        chunk_paths, tmpdir = self._split_audio_to_chunks(audio_path, chunk_seconds)
        try:
            combined_text = []
            combined_segments = []
            language = "en"
            total = len(chunk_paths)
            for idx, chunk_path in enumerate(chunk_paths):
                logger.info(f"🎧 Transcribing chunk {idx+1}/{total}: {chunk_path}")
                offset = idx * float(chunk_seconds)
                result = self._transcribe_single(chunk_path)
                combined_text.append(result.get("text", "") or "")
                lang = result.get("language") or language
                language = lang or language
                segs = result.get("segments") or []
                for s in segs:
                    try:
                        start = float(s.get("start", 0)) + offset
                        end = float(s.get("end", 0)) + offset
                        text = s.get("text", "")
                    except Exception:
                        start = float(getattr(s, "start", 0) or 0) + offset
                        end = float(getattr(s, "end", 0) or 0) + offset
                        text = getattr(s, "text", "") or ""
                    combined_segments.append({"start": start, "end": end, "text": text})
            return {"text": "\n\n".join(t for t in combined_text if t).strip(), "segments": combined_segments, "language": language}
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def transcribe_audio(self, audio_path: str) -> Dict[str, Any]:
        """Transcribe audio using Deepgram with chunking for long audio"""
        if not self.use_deepgram:
            raise Exception("Deepgram is not configured. Set USE_DEEPGRAM=true and provide DEEPGRAM_API_KEY in .env")
        
        # Decide whether to chunk based on duration or size
        try:
            duration = self._get_audio_duration_seconds(audio_path)
        except Exception:
            duration = None
        try:
            size_bytes = os.path.getsize(audio_path)
        except Exception:
            size_bytes = 0

        should_chunk = False
        if duration is not None and duration >= float(getattr(self, "chunk_threshold_seconds", 2400)):
            should_chunk = True
            logger.info(f"⏱️ Long audio detected ({duration/60:.1f} min) >= threshold, using chunked transcription.")
        elif duration is None and size_bytes >= int(getattr(self, "chunk_size_bytes_threshold", 150*1024*1024)):
            should_chunk = True
            logger.info(f"💾 Large file size detected ({size_bytes/1024/1024:.1f} MB) and unknown duration; using chunked transcription.")

        if should_chunk:
            try:
                return self._transcribe_audio_chunked(audio_path, int(getattr(self, "chunk_seconds", 600)))
            except Exception as e:
                logger.error(f"❌ Chunked transcription failed: {e}; falling back to single-file transcription.")
                return self._transcribe_single(audio_path)

        # Default single-file path
        return self._transcribe_single(audio_path)

    def is_available(self) -> bool:
        """Check if the transcription service is available"""
        return bool(self.use_deepgram)

# Global instance
transcription_service = TranscriptionService()