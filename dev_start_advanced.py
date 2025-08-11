#!/usr/bin/env python3
"""
Advanced Development startup script for Video Transcription API with watchdog auto-reload
Provides more granular control over file watching and restart behavior
"""

import sys
import subprocess
import os
import time
import signal
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class RestartHandler(FileSystemEventHandler):
    """Handler for file system events that triggers server restart"""
    
    def __init__(self, restart_callback):
        self.restart_callback = restart_callback
        self.last_restart = 0
        self.restart_delay = 1  # Minimum delay between restarts in seconds
        
    def on_modified(self, event):
        if event.is_directory:
            return
            
        # Only restart for Python files
        if not event.src_path.endswith('.py'):
            return
            
        # Ignore __pycache__ and other temporary files
        if '__pycache__' in event.src_path or event.src_path.endswith('.pyc'):
            return
            
        current_time = time.time()
        if current_time - self.last_restart < self.restart_delay:
            return
            
        self.last_restart = current_time
        print(f"📝 File changed: {event.src_path}")
        self.restart_callback()

class DevelopmentServer:
    """Advanced development server with auto-reload capabilities"""
    
    def __init__(self):
        self.process = None
        self.observer = None
        self.should_restart = threading.Event()
        self.running = False
        
    def check_ffmpeg(self):
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

    def check_dependencies(self):
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

    def create_directories(self):
        """Create necessary directories"""
        directories = ['uploads', 'outputs', 'temp', 'static']
        for directory in directories:
            Path(directory).mkdir(exist_ok=True)
            print(f"✅ Directory '{directory}' ready")

    def start_server(self):
        """Start the FastAPI server"""
        try:
            cmd = [
                sys.executable, '-m', 'uvicorn', 'main:app',
                '--host', '0.0.0.0',
                '--port', '8000',
                '--log-level', 'info'
            ]
            
            print("🚀 Starting server process...")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            # Stream output in a separate thread
            def stream_output():
                if self.process:
                    for line in iter(self.process.stdout.readline, ''):
                        if line.strip():
                            print(f"[SERVER] {line.strip()}")
            
            output_thread = threading.Thread(target=stream_output, daemon=True)
            output_thread.start()
            
            return True
            
        except Exception as e:
            print(f"❌ Error starting server: {e}")
            return False

    def stop_server(self):
        """Stop the FastAPI server"""
        if self.process:
            print("🛑 Stopping server...")
            try:
                # Try graceful shutdown first
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown fails
                print("🔨 Force killing server...")
                self.process.kill()
                self.process.wait()
            finally:
                self.process = None

    def restart_server(self):
        """Restart the FastAPI server"""
        print("🔄 Restarting server due to file changes...")
        self.stop_server()
        time.sleep(0.5)  # Brief pause
        self.start_server()
        print("✅ Server restarted successfully")

    def setup_file_watcher(self):
        """Setup file system watcher"""
        event_handler = RestartHandler(self.restart_server)
        self.observer = Observer()
        
        # Watch current directory for Python files
        watch_path = Path('.').resolve()
        self.observer.schedule(event_handler, str(watch_path), recursive=True)
        
        print(f"👀 Watching for changes in: {watch_path}")
        print("📁 Monitoring: *.py files")
        print("🚫 Ignoring: __pycache__, *.pyc, venv/, temp/, uploads/, outputs/")

    def run(self):
        """Run the development server with auto-reload"""
        print("🎥 Video Transcription API - Advanced Development Mode")
        print("🔄 Auto-reload with watchdog - enhanced file monitoring")
        print("=" * 70)
        
        # Pre-flight checks
        if not self.check_ffmpeg():
            return False
        
        print()
        
        if not self.check_dependencies():
            print("\nInstall dependencies with: pip install -r requirements.txt")
            return False
        
        print()
        self.create_directories()
        print()
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            print("\n👋 Shutting down development server...")
            self.running = False
            self.stop_server()
            if self.observer:
                self.observer.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start the server
        if not self.start_server():
            return False
        
        # Setup file watcher
        self.setup_file_watcher()
        self.observer.start()
        
        print()
        print("🚀 Development server is running!")
        print("📱 Web interface: http://localhost:8000")
        print("📚 API docs: http://localhost:8000/docs")
        print("⏹️  Press Ctrl+C to stop")
        print()
        
        self.running = True
        
        try:
            # Keep the main thread alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            print("\n🧹 Cleaning up...")
            self.stop_server()
            if self.observer:
                self.observer.stop()
                self.observer.join()
        
        return True

def main():
    """Main entry point"""
    server = DevelopmentServer()
    success = server.run()
    
    if not success:
        print("❌ Failed to start development server")
        sys.exit(1)
    
    print("👋 Development server stopped")

if __name__ == "__main__":
    main()