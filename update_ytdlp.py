#!/usr/bin/env python3
"""
Script to update yt-dlp to the latest version
This can help resolve 403 Forbidden errors caused by outdated extractors
"""

import subprocess
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_ytdlp():
    """Update yt-dlp to the latest version"""
    try:
        logger.info("Updating yt-dlp to the latest version...")
        
        # Update yt-dlp using pip
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'
        ], capture_output=True, text=True, check=True)
        
        logger.info("yt-dlp updated successfully!")
        logger.info(f"Output: {result.stdout}")
        
        # Check the new version
        version_result = subprocess.run([
            sys.executable, '-c', 'import yt_dlp; print(f"yt-dlp version: {yt_dlp.version.__version__}")'
        ], capture_output=True, text=True)
        
        if version_result.returncode == 0:
            logger.info(version_result.stdout.strip())
        
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to update yt-dlp: {e}")
        logger.error(f"Error output: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error updating yt-dlp: {e}")
        return False

if __name__ == "__main__":
    success = update_ytdlp()
    sys.exit(0 if success else 1)