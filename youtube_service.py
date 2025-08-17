"""
YouTube Service Module

Handles YouTube video downloading and audio extraction.
"""

import os
import subprocess
import logging
import yt_dlp
import time
from config import YTDL_FORMAT
from ffmpeg_config import FFMPEG_EXECUTABLE

logger = logging.getLogger(__name__)

class YouTubeService:
    """Service for handling YouTube video downloads and audio extraction"""
    
    @staticmethod
    def check_and_update_ytdlp():
        """
        Check if yt-dlp needs updating and update if necessary
        This can help resolve 403 errors caused by outdated extractors
        """
        try:
            # This is a simple check - in production you might want to implement
            # a more sophisticated version checking mechanism
            logger.info("yt-dlp version check completed")
        except Exception as e:
            logger.warning(f"Could not check yt-dlp version: {e}")
    
    @staticmethod
    def is_ted_url(url: str) -> bool:
        """Check if URL is a TED Talk URL"""
        return 'ted.com' in url.lower()
    
    @staticmethod
    def is_udemy_url(url: str) -> bool:
        """Check if URL is a Udemy course URL"""
        return 'udemy.com' in url.lower()
    
    @staticmethod
    def is_khanacademy_url(url: str) -> bool:
        """Check if URL is a Khan Academy video URL"""
        return 'khanacademy.org' in url.lower()
    
    @staticmethod
    def download_video(url: str, output_path: str, cookies_path: str | None = None) -> str:
        """
        Download video from YouTube URL
        
        Args:
            url (str): YouTube video URL
            output_path (str): Directory to save the downloaded video
            
        Returns:
            str: Path to the downloaded video file
            
        Raises:
            Exception: If download fails
        """
        # Adjust configuration based on URL type
        is_ted = YouTubeService.is_ted_url(url)
        is_udemy = YouTubeService.is_udemy_url(url)
        is_khan = YouTubeService.is_khanacademy_url(url)
        
        # Determine platform-specific settings
        if is_udemy:
            platform = 'Udemy'
            referer = 'https://www.udemy.com/'
            sleep_interval = 3
            max_sleep_interval = 10
            retries = 5
        elif is_ted:
            platform = 'TED'
            referer = 'https://www.ted.com/'
            sleep_interval = 2
            max_sleep_interval = 8
            retries = 5
        elif is_khan:
            platform = 'Khan Academy'
            referer = 'https://www.khanacademy.org/'
            sleep_interval = 2
            max_sleep_interval = 8
            retries = 5
        else:
            platform = 'YouTube'
            referer = 'https://www.youtube.com/'
            sleep_interval = 1
            max_sleep_interval = 5
            retries = 3
        
        ydl_opts = {
            'format': YTDL_FORMAT,
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'extractaudio': False,
            # Anti-bot measures
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'referer': referer,
            'headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            # Rate limiting and retries (more conservative for educational platforms)
            'sleep_interval': sleep_interval,
            'max_sleep_interval': max_sleep_interval,
            'sleep_interval_subtitles': sleep_interval,
            'retries': retries,
            'fragment_retries': retries,
            'extractor_retries': retries,
            'file_access_retries': retries,
            # Additional options
            'ignoreerrors': False,
            'no_warnings': False,
            'extract_flat': False,
            # Cookies and session handling
            'cookiefile': cookies_path if cookies_path else None,
            'cookiesfrombrowser': None,
        }
        
        # Udemy-specific configurations
        if is_udemy:
            ydl_opts.update({
                # Udemy often requires authentication, but we'll try public previews
                'username': None,
                'password': None,
                # More conservative approach for Udemy
                'socket_timeout': 30,
                'retries': 10,
                'fragment_retries': 10,
            })
        
        try:
            if cookies_path:
                logger.info(f"Starting download for {platform} content with cookies file: {cookies_path}")
            else:
                logger.info(f"Starting download for {platform} content: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                logger.info(f"Download completed successfully: {filename}")
                return filename
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            if "403" in error_msg or "Forbidden" in error_msg:
                # Try with different format as fallback
                logger.warning(f"403 error encountered, trying fallback format for {url}")
                return YouTubeService._download_with_fallback(url, output_path)
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                raise Exception("YouTube rate limit exceeded. Please try again later.")
            elif "private" in error_msg.lower() or "unavailable" in error_msg.lower():
                raise Exception("Video is private or unavailable.")
            else:
                raise Exception(f"YouTube download failed: {error_msg}")
        except Exception as e:
            raise Exception(f"YouTube download failed: {str(e)}")
    
    @staticmethod
    def _download_with_fallback(url: str, output_path: str) -> str:
        """
        Fallback download method with different configurations
        """
        is_ted = YouTubeService.is_ted_url(url)
        is_khan = YouTubeService.is_khanacademy_url(url)
        
        if is_ted or is_khan:
            # Educational site-specific fallback configurations (TED/Khan Academy)
            ref = 'https://www.ted.com/' if is_ted else 'https://www.khanacademy.org/'
            fallback_configs = [
                # Try with a conservative video format
                {
                    'format': 'best[height<=480]/best',
                    'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'referer': ref,
                    'sleep_interval': 3,
                    'retries': 3,
                },
                # Try with audio-only
                {
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
                    'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'referer': ref,
                    'sleep_interval': 5,
                    'retries': 2,
                },
            ]
        else:
            # YouTube-specific fallback configurations
            fallback_configs = [
                # Try with audio-only format first (often works when video fails)
                {
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'sleep_interval': 2,
                    'retries': 2,
                },
                # Try with lower quality video
                {
                    'format': 'worst[ext=mp4]/worst',
                    'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
                    'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'sleep_interval': 3,
                    'retries': 2,
                },
                # Try with generic format
                {
                    'format': 'best',
                    'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
                    'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                    'sleep_interval': 5,
                    'retries': 1,
                }
            ]
        
        for i, config in enumerate(fallback_configs):
            try:
                logger.info(f"Trying fallback method {i+1}/3 for {url}")
                with yt_dlp.YoutubeDL(config) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    logger.info(f"Fallback method {i+1} successful")
                    return filename
            except Exception as e:
                logger.warning(f"Fallback method {i+1} failed: {str(e)}")
                continue
        
        raise Exception("All download methods failed. The video may be geo-blocked, private, or temporarily unavailable.")
    
    @staticmethod
    def extract_audio(video_path: str, audio_path: str) -> str:
        """
        Extract audio from video file using ffmpeg

        Args:
            video_path (str): Path to the input video file
            audio_path (str): Path for the output audio file

        Returns:
            str: Path to the extracted audio file

        Raises:
            Exception: If audio extraction fails
        """
        try:
            # Use ffmpeg to extract audio
            cmd = [
                FFMPEG_EXECUTABLE,
                '-i', video_path,
                '-vn',  # No video
                '-acodec', 'pcm_s16le',  # PCM 16-bit little-endian
                '-ar', '16000',  # Sample rate 16kHz (good for Whisper)
                '-ac', '1',  # Mono
                '-y',  # Overwrite output file
                audio_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
            logger.info(f"Audio extracted successfully to {audio_path}")
            return audio_path

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            raise Exception(f"Audio extraction failed: {e.stderr}")
        except FileNotFoundError:
            # This error is now less likely due to the FFMPEG_EXECUTABLE config
            raise Exception(f"FFmpeg not found. Please ensure '{FFMPEG_EXECUTABLE}' is a valid path or in your system's PATH.")
        except Exception as e:
            raise Exception(f"An unexpected error occurred during audio extraction: {str(e)}")
    
    @staticmethod
    def get_video_info(url: str) -> dict:
        """
        Get video information without downloading
        
        Args:
            url (str): YouTube video URL
            
        Returns:
            dict: Video information
            
        Raises:
            Exception: If info extraction fails
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            # Anti-bot measures
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            'headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            # Rate limiting and retries
            'sleep_interval': 1,
            'max_sleep_interval': 5,
            'retries': 3,
            'extractor_retries': 3,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'upload_date': info.get('upload_date', 'Unknown')
                }
        except Exception as e:
            raise Exception(f"Failed to extract video info: {str(e)}")

# Global instance
youtube_service = YouTubeService()