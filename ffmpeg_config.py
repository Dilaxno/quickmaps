import os
import logging

logger = logging.getLogger(__name__)

FFMPEG_EXECUTABLE = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE_EXECUTABLE = os.getenv("FFPROBE_PATH", "ffprobe")

if FFMPEG_EXECUTABLE != "ffmpeg":
    logger.info(f"Using custom FFmpeg path: {FFMPEG_EXECUTABLE}")

if FFPROBE_EXECUTABLE != "ffprobe":
    logger.info(f"Using custom ffprobe path: {FFPROBE_EXECUTABLE}")
