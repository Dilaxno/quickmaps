#!/usr/bin/env python3
"""
Development startup script for Video Transcription API with auto-reload
"""

import sys
import subprocess
import os
from pathlib import Path

def check_ffmpeg():
    """Check if FFmpeg is installed"""
    try:
        subprocess.run(['ffmpeg', '-version'], 
                      capture_output=True, check=True)
        print("✅ FFmpeg is installed")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ FFmpeg not found!")
        print("Please install FFmpeg:")
        print("  Windows: Download from https://ffmpeg.org/download.html")
        print("  macOS: brew install ffmpeg")
        print("  Linux: sudo apt install ffmpeg")
        return False

def check_dependencies():
    """Check if required Python packages are installed"""
    required_packages = [
        'fastapi', 'uvicorn', 'yt-dlp', 'whisper', 'torch', 'watchdog'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package} is installed")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package} is missing")
    
    if missing_packages:
        print(f"\nPlease install missing packages:")
        print(f"pip install {' '.join(missing_packages)}")
        return False
    
    return True

def create_directories():
    """Create necessary directories"""
    directories = ['uploads', 'outputs', 'temp', 'static']
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Directory '{directory}' ready")

def main():
    print("🎥 Video Transcription API - Development Mode")
    print("🔄 Auto-reload enabled - server will restart on file changes")
    print("=" * 60)
    
    # Check FFmpeg
    if not check_ffmpeg():
        sys.exit(1)
    
    print()
    
    # Check Python dependencies
    if not check_dependencies():
        print("\nInstall dependencies with: pip install -r requirements.txt")
        sys.exit(1)
    
    print()
    
    # Create directories
    create_directories()
    
    print()
    print("🚀 Starting development server with auto-reload...")
    print("📱 Web interface: http://localhost:8000")
    print("📚 API docs: http://localhost:8000/docs")
    print("🔄 Watching for changes in: *.py files")
    print("⏹️  Press Ctrl+C to stop")
    print()
    
    # Start the application with auto-reload
    try:
        import uvicorn
        uvicorn.run(
            "main:app",
            host="0.0.0.0", 
            port=8000,
            reload=True,
            reload_dirs=["./"],
            reload_includes=["*.py"],
            reload_excludes=["venv/*", "__pycache__/*", "*.pyc", "temp/*", "uploads/*", "outputs/*"]
        )
    except KeyboardInterrupt:
        print("\n👋 Development server stopped by user")
    except Exception as e:
        print(f"❌ Error starting development server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()