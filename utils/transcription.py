import whisper
import torch

# Use "small" model for better GPU acceleration and accuracy balance
# Available models: tiny, base, small, medium, large
# "small" provides good accuracy while being GPU-optimized
model = whisper.load_model("small")

def transcribe_video(filepath):
    """
    Transcribe video using Whisper small model with GPU acceleration
    
    Args:
        filepath (str): Path to the video/audio file
        
    Returns:
        list: List of transcript segments with timestamps
    """
    # Check if CUDA is available for GPU acceleration
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # Transcribe with optimized settings for GPU
    result = model.transcribe(
        filepath, 
        verbose=True,
        # Enable GPU acceleration if available
        fp16=torch.cuda.is_available(),  # Use half precision on GPU for speed
        # Additional optimization options
        temperature=0.0,  # Use deterministic decoding for consistency
        best_of=1,       # Use single beam for speed
        beam_size=1      # Single beam search for faster processing
    )
    
    return result["segments"]  # Includes timestamps
