#!/usr/bin/env python3
"""
Setup script for Edge-TTS integration
This script helps install and configure the required dependencies for Edge-TTS
"""

import subprocess
import sys
import logging
import os
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_command(command, description):
    """Run a command and handle errors"""
    try:
        logger.info(f"🔧 {description}")
        logger.info(f"Running: {command}")
        
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        
        if result.stdout:
            logger.info(f"Output: {result.stdout.strip()}")
        
        logger.info(f"✅ {description} completed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ {description} failed")
        logger.error(f"Error: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"❌ {description} failed with exception: {e}")
        return False

def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    logger.info(f"Python version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        logger.error("❌ Python 3.8 or higher is required")
        return False
    
    logger.info("✅ Python version is compatible")
    return True

def install_dependencies():
    """Install required dependencies for Edge-TTS"""
    dependencies = [
        ("edge-tts>=6.1.0", "Microsoft Edge Text-to-Speech"),
        ("soundfile>=0.12.1", "Audio file I/O"),
        ("asyncio", "Async I/O support (built-in)"),
    ]
    
    logger.info("📦 Installing Edge-TTS dependencies...")
    
    success_count = 0
    for package, description in dependencies:
        if run_command(f"pip install {package}", f"Installing {description}"):
            success_count += 1
        else:
            logger.warning(f"⚠️ Failed to install {package}")
    
    logger.info(f"📊 Installation summary: {success_count}/{len(dependencies)} packages installed successfully")
    return success_count == len(dependencies)

def test_imports():
    """Test if all required modules can be imported"""
    test_modules = [
        ("edge_tts", "Edge-TTS"),
        ("soundfile", "SoundFile"),
        ("asyncio", "AsyncIO"),
    ]
    
    logger.info("🧪 Testing module imports...")
    
    success_count = 0
    for module, description in test_modules:
        try:
            __import__(module)
            logger.info(f"✅ {description} import successful")
            success_count += 1
        except ImportError as e:
            logger.error(f"❌ {description} import failed: {e}")
        except Exception as e:
            logger.error(f"❌ {description} import failed with exception: {e}")
    
    logger.info(f"📊 Import test summary: {success_count}/{len(test_modules)} modules imported successfully")
    return success_count == len(test_modules)

def test_edge_tts_service():
    """Test if Edge-TTS service can be created"""
    try:
        logger.info("🎤 Testing Edge-TTS service creation...")
        
        import edge_tts
        import asyncio
        
        # Test creating a communicate object
        logger.info("📥 Testing Edge-TTS communicate object...")
        communicate = edge_tts.Communicate("Test", "en-US-AriaNeural")
        
        logger.info("✅ Edge-TTS service created successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Edge-TTS service test failed: {e}")
        return False

async def test_voice_list():
    """Test if Edge-TTS voice list can be retrieved"""
    try:
        logger.info("👤 Testing Edge-TTS voice list...")
        
        import edge_tts
        
        logger.info("📥 Retrieving available voices...")
        voices = await edge_tts.list_voices()
        
        logger.info(f"✅ Voice list retrieved successfully ({len(voices)} voices available)")
        
        # Show a few example voices
        english_voices = [v for v in voices if v['Locale'].startswith('en-')][:5]
        for voice in english_voices:
            logger.info(f"   - {voice['ShortName']}: {voice['DisplayName']}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Voice list test failed: {e}")
        return False

async def run_full_test():
    """Run a complete end-to-end test"""
    try:
        logger.info("🚀 Running full Edge-TTS test...")
        
        import edge_tts
        import tempfile
        import os
        
        # Generate speech
        test_text = "Hello, this is a test of the Microsoft Edge text-to-speech system."
        voice = "en-US-AriaNeural"
        
        logger.info(f"Generating speech with voice: {voice}")
        communicate = edge_tts.Communicate(test_text, voice)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            await communicate.save(tmp_file.name)
            file_size = os.path.getsize(tmp_file.name)
            
            logger.info(f"✅ Full test successful!")
            logger.info(f"   - Generated audio file: {tmp_file.name}")
            logger.info(f"   - File size: {file_size} bytes")
            logger.info(f"   - Voice: {voice}")
            
            # Try to get duration if soundfile is available
            try:
                import soundfile as sf
                audio_data, sample_rate = sf.read(tmp_file.name)
                duration = len(audio_data) / sample_rate
                logger.info(f"   - Sample rate: {sample_rate} Hz")
                logger.info(f"   - Duration: {duration:.2f} seconds")
            except ImportError:
                logger.info("   - Duration: Could not calculate (soundfile not available)")
            
            # Clean up
            os.unlink(tmp_file.name)
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Full test failed: {e}")
        return False

async def main():
    """Main setup function"""
    logger.info("🎯 Edge-TTS Setup Script")
    logger.info("=" * 50)
    
    # Check Python version
    if not check_python_version():
        return False
    
    # Install dependencies
    if not install_dependencies():
        logger.error("❌ Dependency installation failed")
        return False
    
    # Test imports
    if not test_imports():
        logger.error("❌ Import tests failed")
        return False
    
    # Test Edge-TTS service
    if not test_edge_tts_service():
        logger.error("❌ Edge-TTS service test failed")
        return False
    
    # Test voice list
    if not await test_voice_list():
        logger.error("❌ Voice list test failed")
        return False
    
    # Run full test
    if not await run_full_test():
        logger.error("❌ Full integration test failed")
        return False
    
    logger.info("🎉 Edge-TTS setup completed successfully!")
    logger.info("✅ All tests passed - Edge-TTS is ready to use")
    
    return True

if __name__ == "__main__":
    import asyncio
    success = asyncio.run(main())
    sys.exit(0 if success else 1)