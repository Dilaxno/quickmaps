"""
Configuration settings for Video Transcription API
"""

import os
from pathlib import Path

# Load environment variables from .env file
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
    # python-dotenv not installed, skip loading .env file
    print("⚠️ python-dotenv not installed, skipping .env file loading")
    pass

# Server Configuration
HOST = "0.0.0.0"
PORT = 8000
DEBUG = False

# Directory Configuration
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
TEMP_DIR = BASE_DIR / "temp"
STATIC_DIR = BASE_DIR / "static"

# Whisper Configuration
WHISPER_MODEL = "base"  # Options: tiny, base, small, medium, large
WHISPER_DEVICE = "cpu"  # Options: cpu, cuda (if GPU available)

# Processing Configuration
MAX_WORKERS = 2  # Number of concurrent transcription jobs
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB in bytes
CLEANUP_TEMP_FILES = True

# Supported file formats
SUPPORTED_VIDEO_FORMATS = {
    '.mp4', '.avi', '.mov', '.mkv', '.flv', 
    '.wmv', '.webm', '.m4v', '.3gp', '.ogv'
}

SUPPORTED_IMAGE_FORMATS = {
    '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'
}

# YouTube-DL Configuration
YTDL_FORMAT = 'best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best'  # Preferred format for downloads
YTDL_AUDIO_FORMAT = 'wav'  # Audio format for extraction
YTDL_AUDIO_QUALITY = '192'  # Audio quality

# CORS Configuration
CORS_ORIGINS = ["*"]  # Allow all origins, restrict in production
CORS_METHODS = ["*"]
CORS_HEADERS = ["*"]

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Groq API Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
ENABLE_NOTES_GENERATION = os.getenv("ENABLE_NOTES_GENERATION", "true").lower() == "true"

# Cloudflare R2 Configuration
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "mindquick-notes")
R2_ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_ACCOUNT_ID else ""
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")  # Custom domain for public access
ENABLE_R2_STORAGE = os.getenv("ENABLE_R2_STORAGE", "true").lower() == "true"

# Environment-specific overrides
if os.getenv("ENVIRONMENT") == "production":
    DEBUG = False
    CORS_ORIGINS = ["https://yourdomain.com"]  # Restrict in production
    LOG_LEVEL = "WARNING"

# GPU Configuration (if available)
try:
    import torch
    if torch.cuda.is_available():
        WHISPER_DEVICE = "cuda"
        print(f"🚀 GPU acceleration available: {torch.cuda.get_device_name(0)}")
    else:
        print("💻 Using CPU for transcription")
except ImportError:
    print("💻 Using CPU for transcription (PyTorch not available)")

# Model size recommendations based on available memory
def get_recommended_model():
    """Get recommended Whisper model based on system resources"""
    try:
        import psutil
        available_memory = psutil.virtual_memory().available / (1024**3)  # GB
        
        if available_memory < 2:
            return "tiny"
        elif available_memory < 4:
            return "base"
        elif available_memory < 8:
            return "small"
        else:
            return "medium"
    except ImportError:
        return "base"  # Default fallback

# Auto-adjust model if not explicitly set
if WHISPER_MODEL == "auto":
    WHISPER_MODEL = get_recommended_model()
    print(f"🧠 Auto-selected Whisper model: {WHISPER_MODEL}")

# Validation
def validate_config():
    """Validate configuration settings"""
    errors = []
    
    if WHISPER_MODEL not in ["tiny", "base", "small", "medium", "large"]:
        errors.append(f"Invalid WHISPER_MODEL: {WHISPER_MODEL}")
    
    if MAX_WORKERS < 1:
        errors.append("MAX_WORKERS must be at least 1")
    
    if MAX_FILE_SIZE < 1024 * 1024:  # 1MB minimum
        errors.append("MAX_FILE_SIZE must be at least 1MB")
    
    if errors:
        raise ValueError("Configuration errors: " + "; ".join(errors))

# Run validation
validate_config()