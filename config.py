"""
Configuration settings for Video Transcription API
"""

import os
from pathlib import Path
from typing import Set, Optional


class Config:
    """Application configuration class"""
    
    def __init__(self):
        self._load_environment()
        self._setup_directories()
        self._validate_config()
    
    def _load_environment(self):
        """Load environment variables from .env file"""
        try:
            from dotenv import load_dotenv
            # Load from parent directory where .env file is located
            env_path = Path(__file__).parent.parent / '.env'
            if env_path.exists():
                load_dotenv(env_path)
                print(f"✅ Loaded .env file from: {env_path}")
            else:
                # Fallback: try current directory
                load_dotenv()
                print("✅ Loaded .env file from current directory")
        except ImportError:
            print("⚠️ python-dotenv not installed, skipping .env file loading")
    
    def _setup_directories(self):
        """Setup directory paths"""
        self.BASE_DIR = Path(__file__).parent
        self.UPLOAD_DIR = self.BASE_DIR / "uploads"
        self.OUTPUT_DIR = self.BASE_DIR / "outputs"
        self.TEMP_DIR = self.BASE_DIR / "temp"
        self.STATIC_DIR = self.BASE_DIR / "static"
        
        # Create directories if they don't exist
        for directory in [self.UPLOAD_DIR, self.OUTPUT_DIR, self.TEMP_DIR, self.STATIC_DIR]:
            directory.mkdir(exist_ok=True)
    
    def _validate_config(self):
        """Validate configuration settings"""
        errors = []
        warnings = []
        
        # Validate Deepgram configuration (warning only for TTS compatibility)
        if self.USE_DEEPGRAM and not self.DEEPGRAM_API_KEY:
            warnings.append("DEEPGRAM_API_KEY is missing - Deepgram transcription and TTS will not be available")
        
        # Validate Groq configuration (warning only)
        if self.ENABLE_NOTES_GENERATION and not self.GROQ_API_KEY:
            warnings.append("GROQ_API_KEY is missing - notes generation will not be available")
        
        # Validate basic settings (these are actual errors)
        if self.MAX_WORKERS < 1:
            errors.append("MAX_WORKERS must be at least 1")
        
        if self.MAX_FILE_SIZE < 1024 * 1024:  # 1MB minimum
            errors.append("MAX_FILE_SIZE must be at least 1MB")
        
        # Print warnings
        if warnings:
            print("⚠️ Configuration warnings:")
            for warning in warnings:
                print(f"   - {warning}")
        
        # Only raise errors for critical issues
        if errors:
            raise ValueError("Configuration errors: " + "; ".join(errors))
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Transcription Configuration - Deepgram (Primary)
    USE_DEEPGRAM: bool = os.getenv("USE_DEEPGRAM", "true").lower() == "true"
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
    DEEPGRAM_MODEL: str = os.getenv("DEEPGRAM_MODEL", "whisper-large")
    
    # Transcription Configuration - Local Whisper (Fallback)
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
    
    # Processing Configuration
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "2"))
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", str(500 * 1024 * 1024)))  # 500MB
    CLEANUP_TEMP_FILES: bool = os.getenv("CLEANUP_TEMP_FILES", "true").lower() == "true"
    
    # File Format Support
    SUPPORTED_VIDEO_FORMATS: Set[str] = {
        '.mp4', '.avi', '.mov', '.mkv', '.flv', 
        '.wmv', '.webm', '.m4v', '.3gp', '.ogv'
    }
    
    SUPPORTED_AUDIO_FORMATS: Set[str] = {
        '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a'
    }
    
    SUPPORTED_IMAGE_FORMATS: Set[str] = {
        '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'
    }
    
    # YouTube-DL Configuration
    YTDL_FORMAT: str = os.getenv("YTDL_FORMAT", "best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best")
    YTDL_AUDIO_FORMAT: str = os.getenv("YTDL_AUDIO_FORMAT", "wav")
    YTDL_AUDIO_QUALITY: str = os.getenv("YTDL_AUDIO_QUALITY", "192")
    
    # CORS Configuration
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") != "*" else ["*"]
    CORS_METHODS: list = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_HEADERS: list = ["*"]
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # AI/LLM Configuration - Groq
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    ENABLE_NOTES_GENERATION: bool = os.getenv("ENABLE_NOTES_GENERATION", "true").lower() == "true"
    
    # Cloud Storage - Cloudflare R2
    R2_ACCOUNT_ID: str = os.getenv("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY_ID: str = os.getenv("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET_NAME: str = os.getenv("R2_BUCKET_NAME", "mindquick-notes")
    R2_PUBLIC_URL: str = os.getenv("R2_PUBLIC_URL", "")
    ENABLE_R2_STORAGE: bool = os.getenv("ENABLE_R2_STORAGE", "true").lower() == "true"
    
    @property
    def R2_ENDPOINT_URL(self) -> str:
        """Generate R2 endpoint URL from account ID"""
        return f"https://{self.R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if self.R2_ACCOUNT_ID else ""
    
    # Firebase Configuration (if used)
    FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "")
    FIREBASE_PRIVATE_KEY: str = os.getenv("FIREBASE_PRIVATE_KEY", "")
    FIREBASE_CLIENT_EMAIL: str = os.getenv("FIREBASE_CLIENT_EMAIL", "")
    
    # Paddle Configuration (if used for payments)
    PADDLE_VENDOR_ID: str = os.getenv("PADDLE_VENDOR_ID", "")
    PADDLE_API_KEY: str = os.getenv("PADDLE_API_KEY", "")
    PADDLE_PUBLIC_KEY: str = os.getenv("PADDLE_PUBLIC_KEY", "")
    PADDLE_ENVIRONMENT: str = os.getenv("PADDLE_ENVIRONMENT", "sandbox")
    
    def get_gpu_info(self) -> dict:
        """Get GPU information if available"""
        try:
            import torch
            if torch.cuda.is_available():
                return {
                    "available": True,
                    "device_name": torch.cuda.get_device_name(0),
                    "device_count": torch.cuda.device_count(),
                    "memory_total": torch.cuda.get_device_properties(0).total_memory,
                }
            else:
                return {"available": False, "reason": "CUDA not available"}
        except ImportError:
            return {"available": False, "reason": "PyTorch not installed"}
    
    def get_system_info(self) -> dict:
        """Get system resource information"""
        try:
            import psutil
            memory = psutil.virtual_memory()
            return {
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "cpu_count": psutil.cpu_count(),
                "cpu_percent": psutil.cpu_percent(interval=1),
            }
        except ImportError:
            return {"error": "psutil not installed"}
    
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT.lower() == "production"
    
    def get_transcription_service(self) -> str:
        """Get the active transcription service"""
        if self.USE_DEEPGRAM and self.DEEPGRAM_API_KEY:
            return "deepgram"
        else:
            return "local_whisper"


# Create global config instance
config = Config()

# Apply environment-specific overrides
if config.is_production():
    config.DEBUG = False
    config.LOG_LEVEL = "WARNING"
    if config.CORS_ORIGINS == ["*"]:
        config.CORS_ORIGINS = ["https://yourdomain.com"]  # Update with your domain

# Legacy compatibility - expose config values at module level
HOST = config.HOST
PORT = config.PORT
DEBUG = config.DEBUG

# Directory paths
BASE_DIR = config.BASE_DIR
UPLOAD_DIR = config.UPLOAD_DIR
OUTPUT_DIR = config.OUTPUT_DIR
TEMP_DIR = config.TEMP_DIR
STATIC_DIR = config.STATIC_DIR

# Transcription settings
USE_DEEPGRAM = config.USE_DEEPGRAM
DEEPGRAM_API_KEY = config.DEEPGRAM_API_KEY
DEEPGRAM_MODEL = config.DEEPGRAM_MODEL
WHISPER_MODEL = config.WHISPER_MODEL
WHISPER_DEVICE = config.WHISPER_DEVICE

# Processing settings
MAX_WORKERS = config.MAX_WORKERS
MAX_FILE_SIZE = config.MAX_FILE_SIZE
CLEANUP_TEMP_FILES = config.CLEANUP_TEMP_FILES

# File formats
SUPPORTED_VIDEO_FORMATS = config.SUPPORTED_VIDEO_FORMATS
SUPPORTED_AUDIO_FORMATS = config.SUPPORTED_AUDIO_FORMATS
SUPPORTED_IMAGE_FORMATS = config.SUPPORTED_IMAGE_FORMATS

# YouTube-DL
YTDL_FORMAT = config.YTDL_FORMAT
YTDL_AUDIO_FORMAT = config.YTDL_AUDIO_FORMAT
YTDL_AUDIO_QUALITY = config.YTDL_AUDIO_QUALITY

# CORS
CORS_ORIGINS = config.CORS_ORIGINS
CORS_METHODS = config.CORS_METHODS
CORS_HEADERS = config.CORS_HEADERS

# Logging
LOG_LEVEL = config.LOG_LEVEL
LOG_FORMAT = config.LOG_FORMAT

# AI/LLM
GROQ_API_KEY = config.GROQ_API_KEY
GROQ_MODEL = config.GROQ_MODEL
ENABLE_NOTES_GENERATION = config.ENABLE_NOTES_GENERATION

# Cloud Storage
R2_ACCOUNT_ID = config.R2_ACCOUNT_ID
R2_ACCESS_KEY_ID = config.R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY = config.R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME = config.R2_BUCKET_NAME
R2_ENDPOINT_URL = config.R2_ENDPOINT_URL
R2_PUBLIC_URL = config.R2_PUBLIC_URL
ENABLE_R2_STORAGE = config.ENABLE_R2_STORAGE

# Firebase
FIREBASE_PROJECT_ID = config.FIREBASE_PROJECT_ID
FIREBASE_PRIVATE_KEY = config.FIREBASE_PRIVATE_KEY
FIREBASE_CLIENT_EMAIL = config.FIREBASE_CLIENT_EMAIL

# Paddle
PADDLE_VENDOR_ID = config.PADDLE_VENDOR_ID
PADDLE_API_KEY = config.PADDLE_API_KEY
PADDLE_PUBLIC_KEY = config.PADDLE_PUBLIC_KEY
PADDLE_ENVIRONMENT = config.PADDLE_ENVIRONMENT

# Print configuration summary on import
if not config.is_production():
    print(f"🔧 Configuration loaded:")
    print(f"   Environment: {config.ENVIRONMENT}")
    print(f"   Transcription: {config.get_transcription_service()}")
    print(f"   Notes Generation: {'✅' if config.ENABLE_NOTES_GENERATION else '❌'}")
    print(f"   R2 Storage: {'✅' if config.ENABLE_R2_STORAGE else '❌'}")
    
    gpu_info = config.get_gpu_info()
    if gpu_info["available"]:
        print(f"   GPU: ✅ {gpu_info['device_name']}")
    else:
        print(f"   GPU: ❌ {gpu_info['reason']}")