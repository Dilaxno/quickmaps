from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
import subprocess
import os
import json
import logging
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
from utils.transcription import transcribe_video
from utils.summarizer import summarize_transcript
from utils.firebase_auth import require_auth, optional_auth, get_current_user
from utils.ip_detection import get_vpn_detector
from utils.device_fingerprint import get_device_manager
from utils.credit_manager import get_credit_manager
from utils.r2_storage import get_r2_storage
from utils.mjml_email_service import mjml_email_service

# Firebase Firestore import (kept for potential future use)
try:
    from firebase_admin import firestore
    firestore_available = True
except ImportError:
    firestore_available = False
    print("Firebase Admin SDK not available.")

# Vimeo API import
try:
    import vimeo
except ImportError:
    vimeo = None
    print("PyVimeo not installed. Vimeo API features will be limited.")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add GZip compression for large responses
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://127.0.0.1:5173", 
        "https://quickmaps.pro",
        "https://www.quickmaps.pro",
        "https://api.quickmaps.pro"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=[
        "*",
        "Authorization",
        "Content-Type",
        "X-Requested-With",
        "Accept",
        "Origin",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers"
    ],
    expose_headers=["*"],
    max_age=86400,  # Cache preflight requests for 24 hours
)

class YouTubeURL(BaseModel):
    url: str

class VimeoURL(BaseModel):
    url: str

class UserSettingsUpdate(BaseModel):
    notifications: dict = None
    privacy: dict = None
    preferences: dict = None

class CreditGrantRequest(BaseModel):
    credits: int
    reason: str = "Manual grant"

class CreditAllocationRequest(BaseModel):
    user_id: str
    credits: int
    transaction_id: str = None
    reason: str = "Test allocation"

class WelcomeEmailRequest(BaseModel):
    email: str
    name: str = "User"

class DeepExplanationRequest(BaseModel):
    concept: str
    context: str = ""
    detail_level: str = "comprehensive"

class LlamaTestRequest(BaseModel):
    prompt: str
    max_tokens: int = 1000
    temperature: float = 0.7

class NoteSaveRequest(BaseModel):
    notes_data: dict
    title: str = "Untitled Notes"
    encrypt: bool = True

class NoteUpdateRequest(BaseModel):
    title: str = None
    notes_data: dict = None
    encrypt: bool = True

# Helper functions for Vimeo
def extract_vimeo_id(url):
    """Extract Vimeo video ID from URL"""
    import re
    patterns = [
        r'vimeo\.com/(\d+)',
        r'vimeo\.com/video/(\d+)',
        r'player\.vimeo\.com/video/(\d+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def download_vimeo_with_api(video_id, output_path, access_token):
    """Alternative method to download Vimeo video using API"""
    if not vimeo:
        raise Exception("PyVimeo not installed")
    
    try:
        client = vimeo.VimeoClient(
            token=access_token,
            key=None,  # Not needed for personal access tokens
            secret=None  # Not needed for personal access tokens
        )
        
        # Get video information
        response = client.get(f'/videos/{video_id}')
        if response.status_code != 200:
            error_msg = f"Failed to get video info. Status: {response.status_code}"
            if hasattr(response, 'json'):
                try:
                    error_data = response.json()
                    error_msg += f", Error: {error_data}"
                except:
                    error_msg += f", Response: {response.text}"
            raise Exception(error_msg)
        
        video_data = response.json()
        logger.info(f"Video data structure: {list(video_data.keys()) if isinstance(video_data, dict) else type(video_data)}")
        
        # Check if video has downloadable files
        if video_data.get('download'):
            downloads = video_data.get('download', [])
            logger.info(f"Found downloads: {len(downloads) if isinstance(downloads, list) else type(downloads)}")
            
            if downloads and isinstance(downloads, list):
                # Get the best quality download
                valid_downloads = [d for d in downloads if isinstance(d, dict) and d.get('link')]
                if valid_downloads:
                    best_download = max(valid_downloads, key=lambda x: (x.get('width', 0) or 0) * (x.get('height', 0) or 0))
                    download_url = best_download.get('link')
                    
                    if download_url:
                        # Download the file
                        import requests
                        response = requests.get(download_url, stream=True)
                        response.raise_for_status()
                        
                        with open(output_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        
                        return output_path
        
        # Try to get streaming URLs from files
        files = video_data.get('files', [])
        logger.info(f"Found files: {len(files) if isinstance(files, list) else type(files)}")
        
        if files and isinstance(files, list):
            # Get the best quality file
            valid_files = [f for f in files if isinstance(f, dict) and f.get('link')]
            if valid_files:
                best_file = max(valid_files, key=lambda x: (x.get('width', 0) or 0) * (x.get('height', 0) or 0))
                file_url = best_file.get('link')
                
                if file_url:
                    import requests
                    response = requests.get(file_url, stream=True)
                    response.raise_for_status()
                    
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    return output_path
        
        # If no direct download is available, provide helpful error message
        video_title = video_data.get('name', 'Unknown')
        privacy_setting = video_data.get('privacy', {}).get('view', 'unknown')
        
        raise Exception(f"Video '{video_title}' (privacy: {privacy_setting}) does not provide direct download links through the API. This is common for public Vimeo videos that don't allow downloads.")
        
    except Exception as e:
        logger.error(f"Vimeo API download failed: {str(e)}")
        raise

def process_video(filepath: str) -> dict:
    """
    Process a video file to generate comprehensive educational notes
    
    Args:
        filepath: Path to the video file
        
    Returns:
        dict: Educational notes data
    """
    try:
        logger.info(f"Processing video: {filepath}")
        
        # Check if file exists
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Video file not found: {filepath}")
        
        transcript = transcribe_video(filepath)
        logger.info("Transcription completed")
        
        educational_notes = summarize_transcript(transcript)
        logger.info("Educational notes generation completed")
        
        return educational_notes
    except Exception as e:
        logger.error(f"Error in process_video: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Quickcap API is running", "status": "healthy"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "Backend is running properly"}

@app.get("/cors-test")
async def cors_test(request: Request):
    """Test CORS configuration"""
    return {
        "status": "success",
        "message": "CORS is working correctly",
        "origin": request.headers.get("origin"),
        "user_agent": request.headers.get("user-agent"),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/ip/check")
async def check_ip_info(request: Request):
    """Check current IP address and VPN/Proxy status (for testing)"""
    detector = get_vpn_detector()
    client_ip = detector.get_client_ip(request)
    result = detector.check_ip(client_ip)
    
    return {
        "client_ip": client_ip,
        "detection_result": result,
        "headers": dict(request.headers),
        "vpn_blocking_enabled": os.getenv("VPN_BLOCKING_ENABLED", "true").lower() == "true",
        "strict_mode": os.getenv("VPN_STRICT_MODE", "false").lower() == "true"
    }

@app.post("/ip/test")
async def test_ip_detection(test_ip: str = Form(...)):
    """Test VPN/Proxy detection for a specific IP address"""
    detector = get_vpn_detector()
    result = detector.check_ip(test_ip)
    should_block, _ = detector.is_blocked_ip(test_ip)
    
    return {
        "test_ip": test_ip,
        "detection_result": result,
        "would_be_blocked": should_block,
        "vpn_blocking_enabled": os.getenv("VPN_BLOCKING_ENABLED", "true").lower() == "true",
        "strict_mode": os.getenv("VPN_STRICT_MODE", "false").lower() == "true"
    }

# Device Fingerprinting Endpoints

class DeviceRegistrationRequest(BaseModel):
    user_id: str
    device_id: str
    fingerprint: dict
    risk_assessment: dict
    registration_timestamp: str

class DeviceValidationRequest(BaseModel):
    device_id: str
    fingerprint: dict
    risk_assessment: dict

@app.post("/device/register")
async def register_device(request: Request, device_data: DeviceRegistrationRequest, current_user: dict = Depends(require_auth)):
    """Register a new device fingerprint for a user"""
    manager = get_device_manager()
    detector = get_vpn_detector()
    
    # Get client info
    client_ip = detector.get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    
    # Verify user matches the authenticated user
    if device_data.user_id != current_user.get("uid"):
        raise HTTPException(status_code=403, detail="User ID mismatch")
    
    # Register device
    result = manager.register_device(
        device_data=device_data.dict(),
        user_id=current_user.get("uid"),
        ip_address=client_ip,
        user_agent=user_agent
    )
    
    if not result.get("success"):
        if "already registered" in result.get("error", "").lower():
            raise HTTPException(status_code=409, detail=result.get("error"))
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))
    
    logger.info(f"Device registered: {device_data.device_id} for user {current_user.get('uid')}")
    return result

@app.post("/device/validate")
async def validate_device(request: Request, device_data: DeviceValidationRequest, current_user: dict = Depends(require_auth)):
    """Validate a device fingerprint for an existing user"""
    manager = get_device_manager()
    detector = get_vpn_detector()
    
    # Get client info
    client_ip = detector.get_client_ip(request)
    
    # Validate device
    result = manager.validate_device(
        device_data=device_data.dict(),
        user_id=current_user.get("uid"),
        ip_address=client_ip
    )
    
    if not result.get("valid"):
        if result.get("reason") == "device_user_mismatch":
            raise HTTPException(status_code=403, detail=result.get("message"))
        elif result.get("reason") == "device_not_registered":
            raise HTTPException(status_code=404, detail=result.get("message"))
        elif result.get("reason") == "device_inactive":
            raise HTTPException(status_code=410, detail=result.get("message"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message", "Device validation failed"))
    
    logger.info(f"Device validated: {device_data.device_id} for user {current_user.get('uid')}")
    return result

@app.get("/device/check/{device_id}")
async def check_device_status(device_id: str):
    """Check if a device is registered (public endpoint for signup validation)"""
    manager = get_device_manager()
    result = manager.check_device_status(device_id)
    
    if not result.get("exists"):
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Return limited info for privacy
    return {
        "exists": True,
        "device_id": device_id,
        "user_id": result.get("user_id"),  # This is needed for duplicate detection
        "registration_date": result.get("registration_date"),
        "is_active": result.get("is_active")
    }

@app.get("/device/my-devices")
async def get_my_devices(request: Request, current_user: dict = Depends(require_auth)):
    """Get all devices registered to the current user"""
    manager = get_device_manager()
    devices = manager.get_user_devices(current_user.get("uid"))
    
    return {
        "user_id": current_user.get("uid"),
        "devices": devices,
        "device_count": len(devices)
    }

@app.delete("/device/{device_id}")
async def deactivate_device(device_id: str, request: Request, current_user: dict = Depends(require_auth)):
    """Deactivate a device (remove it from the user's account)"""
    manager = get_device_manager()
    
    result = manager.deactivate_device(device_id, current_user.get("uid"))
    
    if not result.get("success"):
        if "not found" in result.get("error", "").lower():
            raise HTTPException(status_code=404, detail="Device not found")
        elif "different user" in result.get("error", "").lower():
            raise HTTPException(status_code=403, detail="Device belongs to different user")
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))
    
    logger.info(f"Device deactivated: {device_id} by user {current_user.get('uid')}")
    return result

@app.get("/device/statistics")
async def get_device_statistics(request: Request, current_user: dict = Depends(require_auth)):
    """Get device fingerprinting statistics (admin only - you can add admin check later)"""
    manager = get_device_manager()
    stats = manager.get_statistics()
    
    return {
        "statistics": stats,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/auth/me")
async def get_current_user_info(request: Request, current_user: dict = Depends(require_auth)):
    """Get current authenticated user information"""
    credit_manager = get_credit_manager()
    credits = await credit_manager.get_user_credits(current_user.get("uid"))
    
    return {
        "uid": current_user.get("uid"),
        "email": current_user.get("email"),
        "name": current_user.get("name"),
        "credits": credits,
        "authenticated": True
    }

# Credit Management Endpoints

@app.post("/credits/grant")
async def grant_credits(credit_request: CreditGrantRequest, request: Request, current_user: dict = Depends(require_auth)):
    """Grant credits to the current user (for testing/admin purposes)"""
    try:
        credit_manager = get_credit_manager()
        user_id = current_user.get("uid")
        
        result = await credit_manager.add_credits(
            user_id=user_id,
            credits=credit_request.credits,
            reason=credit_request.reason,
            transaction_id=f"manual_grant_{datetime.now().timestamp()}"
        )
        
        logger.info(f"Credits granted to user {user_id}: {credit_request.credits} credits")
        return result
        
    except Exception as e:
        logger.error(f"Error granting credits: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to grant credits: {str(e)}")

@app.post("/credits/confirm/{operation_id}")
async def confirm_credit_deduction(operation_id: str, request: Request, current_user: dict = Depends(require_auth)):
    """Confirm credit deduction after successful educational notes display in frontend"""
    credit_manager = get_credit_manager()
    user_id = current_user.get("uid")
    
    try:
        result = await credit_manager.confirm_credit_deduction(user_id, operation_id)
        
        if result.get("success"):
            logger.info(f"Credit deduction confirmed for user {user_id}, operation {operation_id}")
            return {"success": True, "message": "Credit deduction confirmed"}
        else:
            logger.warning(f"Failed to confirm credit deduction for user {user_id}, operation {operation_id}: {result.get('error')}")
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to confirm credit deduction"))
            
    except Exception as e:
        logger.error(f"Error confirming credit deduction: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to confirm credit deduction: {str(e)}")

@app.post("/credits/release/{operation_id}")
async def release_reserved_credits(operation_id: str, request: Request, current_user: dict = Depends(require_auth)):
    """Release reserved credits if frontend fails to display educational notes"""
    credit_manager = get_credit_manager()
    user_id = current_user.get("uid")
    
    try:
        result = await credit_manager.release_reserved_credits(user_id, operation_id)
        
        if result.get("success"):
            logger.info(f"Reserved credits released for user {user_id}, operation {operation_id}")
            return {"success": True, "message": "Reserved credits released"}
        else:
            logger.warning(f"Failed to release reserved credits for user {user_id}, operation {operation_id}: {result.get('error')}")
            # Don't raise an error here as this might be called multiple times
            return {"success": False, "message": result.get("error", "Failed to release reserved credits")}
            
    except Exception as e:
        logger.error(f"Error releasing reserved credits: {str(e)}")
        return {"success": False, "message": f"Failed to release reserved credits: {str(e)}"}

@app.post("/credits/cleanup")
async def cleanup_expired_reservations(request: Request, current_user: dict = Depends(require_auth)):
    """Clean up expired credit reservations (admin endpoint)"""
    try:
        credit_manager = get_credit_manager()
        result = await credit_manager.cleanup_expired_reservations()
        
        logger.info(f"Cleaned up {result.get('cleaned_count', 0)} expired reservations")
        return {
            "success": True,
            "message": f"Cleaned up {result.get('cleaned_count', 0)} expired reservations",
            "cleaned_count": result.get('cleaned_count', 0)
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up expired reservations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup expired reservations: {str(e)}")

# Video Processing Endpoints

@app.post("/upload/")
async def upload_video(request: Request, file: UploadFile = File(...), current_user: dict = Depends(require_auth)):
    """Upload and process a video file to generate educational notes"""
    
    # Check VPN/Proxy blocking
    detector = get_vpn_detector()
    client_ip = detector.get_client_ip(request)
    is_blocked, block_reason = detector.is_blocked_ip(client_ip)
    
    if is_blocked:
        logger.warning(f"Blocked upload attempt from {client_ip}: {block_reason}")
        raise HTTPException(
            status_code=403, 
            detail=f"Access denied: {block_reason}. Please disable VPN/proxy and try again."
        )
    
    # Check and reserve credits
    credit_manager = get_credit_manager()
    user_id = current_user.get("uid")
    
    # Reserve 1 credit for processing
    operation_id = f"upload_{user_id}_{datetime.now().timestamp()}"
    credit_result = await credit_manager.reserve_credits(user_id, 1, operation_id)
    
    if not credit_result.get("success"):
        raise HTTPException(status_code=402, detail="Insufficient credits")
    
    try:
        # Save uploaded file
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        
        file_path = os.path.join(upload_dir, f"{user_id}_{datetime.now().timestamp()}_{file.filename}")
        
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        logger.info(f"File uploaded: {file_path}")
        
        # Process the video
        processing_result = process_video(file_path)
        logger.info(f"Video processing completed successfully for user {user_id}")
        
        # Educational notes are now ready for the user
        logger.info(f"Educational notes generated successfully for user {user_id}")
        
        # Clean up the uploaded file to save disk space
        try:
            os.remove(file_path)
            logger.info(f"Cleaned up uploaded file: {file_path}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to clean up file {file_path}: {cleanup_error}")
        
        # Add operation_id to result so frontend can confirm the transaction
        processing_result['operation_id'] = operation_id
        
        return processing_result
        
    except Exception as e:
        # Release reserved credits on error
        await credit_manager.release_reserved_credits(user_id, operation_id)
        logger.error(f"Error processing uploaded video for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")

@app.post("/youtube/")
async def process_youtube(request: Request, youtube: YouTubeURL, current_user: dict = Depends(require_auth)):
    """Process a YouTube video to generate educational notes"""
    
    # Check VPN/Proxy blocking
    detector = get_vpn_detector()
    client_ip = detector.get_client_ip(request)
    is_blocked, block_reason = detector.is_blocked_ip(client_ip)
    
    if is_blocked:
        logger.warning(f"Blocked YouTube processing attempt from {client_ip}: {block_reason}")
        raise HTTPException(
            status_code=403, 
            detail=f"Access denied: {block_reason}. Please disable VPN/proxy and try again."
        )
    
    # Check and reserve credits
    credit_manager = get_credit_manager()
    user_id = current_user.get("uid")
    
    # Reserve 1 credit for processing
    operation_id = f"youtube_{user_id}_{datetime.now().timestamp()}"
    credit_result = await credit_manager.reserve_credits(user_id, 1, operation_id)
    
    if not credit_result.get("success"):
        raise HTTPException(status_code=402, detail="Insufficient credits")
    
    try:
        # Create downloads directory
        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_template = os.path.join(download_dir, f"youtube_{user_id}_{timestamp}_%(title)s.%(ext)s")
        
        # Download with yt-dlp
        cmd = [
            "yt-dlp",
            "--format", "bestaudio/best",
            "--output", output_template,
            "--no-playlist",
            "--force-overwrites",
            "--retries", "10",
            "--socket-timeout", "60",
            "--ignore-errors",
            "--impersonate", "chrome",
            youtube.url
        ]
        
        logger.info(f"Downloading YouTube video: {youtube.url}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"YouTube download completed: {result.stdout}")
        
        # Find the downloaded file
        downloaded_files = []
        for file in os.listdir(download_dir):
            if file.startswith(f"youtube_{user_id}_{timestamp}"):
                downloaded_files.append(os.path.join(download_dir, file))
        
        if not downloaded_files:
            raise Exception("Failed to download video")
        
        actual_path = downloaded_files[0]
        logger.info(f"Downloaded file: {actual_path}")
        
        # Process the video
        processing_result = process_video(actual_path)
        logger.info(f"YouTube video processing completed successfully for user {user_id}")
        
        # Educational notes are now ready for the user
        logger.info(f"Educational notes generated successfully for user {user_id}")
        
        # Clean up the downloaded file to save disk space
        try:
            os.remove(actual_path)
            logger.info(f"Cleaned up downloaded file: {actual_path}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to clean up file {actual_path}: {cleanup_error}")
        
        # Add operation_id to result so frontend can confirm the transaction
        processing_result['operation_id'] = operation_id
        
        return processing_result
        
    except subprocess.CalledProcessError as e:
        # Release reserved credits on error
        await credit_manager.release_reserved_credits(user_id, operation_id)
        logger.error(f"yt-dlp error for user {user_id}: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"Failed to download video: {e.stderr}")
    except Exception as e:
        # Release reserved credits on error
        await credit_manager.release_reserved_credits(user_id, operation_id)
        logger.error(f"Error processing YouTube video for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")

@app.post("/vimeo/")
async def process_vimeo(request: Request, vimeo_request: VimeoURL, current_user: dict = Depends(require_auth)):
    """Process a Vimeo video to generate educational notes"""
    
    # Check VPN/Proxy blocking
    detector = get_vpn_detector()
    client_ip = detector.get_client_ip(request)
    is_blocked, block_reason = detector.is_blocked_ip(client_ip)
    
    if is_blocked:
        logger.warning(f"Blocked Vimeo processing attempt from {client_ip}: {block_reason}")
        raise HTTPException(
            status_code=403, 
            detail=f"Access denied: {block_reason}. Please disable VPN/proxy and try again."
        )
    
    # Check and reserve credits
    credit_manager = get_credit_manager()
    user_id = current_user.get("uid")
    
    # Reserve 1 credit for processing
    operation_id = f"vimeo_{user_id}_{datetime.now().timestamp()}"
    credit_result = await credit_manager.reserve_credits(user_id, 1, operation_id)
    
    if not credit_result.get("success"):
        raise HTTPException(status_code=402, detail="Insufficient credits")
    
    try:
        # Create downloads directory
        download_dir = "downloads"
        os.makedirs(download_dir, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(download_dir, f"vimeo_{user_id}_{timestamp}.%(ext)s")
        
        logger.info(f"Downloading Vimeo video: {vimeo_request.url}")
        
        # Try yt-dlp first (most reliable)
        cmd = [
            "yt-dlp",
            "--format", "bestaudio/best",
            "--output", output_path,
            "--no-playlist",
            "--force-overwrites",
            "--retries", "10",
            "--socket-timeout", "60",
            "--ignore-errors",
            "--impersonate", "chrome",
            vimeo_request.url
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Vimeo download completed: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.warning(f"yt-dlp failed: {e.stderr}")
            
            # Try Vimeo API as fallback
            video_id = extract_vimeo_id(vimeo_request.url)
            if video_id and vimeo:
                access_token = os.getenv("VIMEO_ACCESS_TOKEN")
                if access_token and access_token != "your_vimeo_access_token_here":
                    try:
                        logger.info("Trying Vimeo API download...")
                        actual_path = download_vimeo_with_api(video_id, output_path.replace(".%(ext)s", ".mp4"), access_token)
                    except Exception as api_error:
                        logger.error(f"Vimeo API download failed: {api_error}")
                        raise Exception(f"Both yt-dlp and Vimeo API failed. yt-dlp error: {e.stderr}")
                else:
                    raise Exception(f"yt-dlp failed and no Vimeo API token configured: {e.stderr}")
            else:
                raise Exception(f"yt-dlp failed and cannot extract video ID or PyVimeo not available: {e.stderr}")
        
        # Find the downloaded file
        downloaded_files = []
        for file in os.listdir(download_dir):
            if file.startswith(f"vimeo_{user_id}_{timestamp}"):
                downloaded_files.append(os.path.join(download_dir, file))
        
        if not downloaded_files:
            raise Exception("Failed to download video")
        
        actual_path = downloaded_files[0]
        logger.info(f"Downloaded file: {actual_path}")
        
        # Process the video
        processing_result = process_video(actual_path)
        logger.info(f"Vimeo video processing completed successfully for user {user_id}")
        
        # Educational notes are now ready for the user
        logger.info(f"Educational notes generated successfully for user {user_id}")
        
        # Clean up the downloaded file to save disk space
        try:
            os.remove(actual_path)
            logger.info(f"Cleaned up downloaded file: {actual_path}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to clean up file {actual_path}: {cleanup_error}")
        
        # Add operation_id to result so frontend can confirm the transaction
        processing_result['operation_id'] = operation_id
        
        return processing_result
        
    except Exception as e:
        # Release reserved credits on error
        await credit_manager.release_reserved_credits(user_id, operation_id)
        logger.error(f"Error processing Vimeo video for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")

# User Settings Endpoints

@app.get("/user/settings")
async def get_user_settings(request: Request, current_user: dict = Depends(require_auth)):
    """Get user settings and preferences"""
    try:
        # For now, return default settings. In production, you'd store these in a database
        default_settings = {
            "notifications": {
                "email": True,
                "push": False,
                "notesComplete": True,
                "lowCredits": True,
                "securityAlerts": True
            },
            "privacy": {
                "profileVisible": False,
                "shareAnalytics": True,
                "autoSave": True
            },
            "preferences": {
                "theme": "dark",
                "language": "en",
                "autoPlay": False,
                "compressionLevel": "medium"
            }
        }
        
        return {
            "success": True,
            "settings": default_settings
        }
        
    except Exception as e:
        logger.error(f"Error getting user settings for user {current_user.get('uid')}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user settings: {str(e)}")

@app.put("/user/settings")
async def update_user_settings(
    settings_update: UserSettingsUpdate,
    request: Request, 
    current_user: dict = Depends(require_auth)
):
    """Update user settings and preferences"""
    try:
        # In production, you'd save these to a database
        # For now, just return success
        
        logger.info(f"Settings updated for user {current_user.get('uid')}")
        
        return {
            "success": True,
            "message": "Settings updated successfully"
        }
        
    except Exception as e:
        logger.error(f"Error updating user settings for user {current_user.get('uid')}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update user settings: {str(e)}")

@app.get("/user/statistics")
async def get_user_statistics(request: Request, current_user: dict = Depends(require_auth)):
    """Get user statistics and usage data"""
    try:
        credit_manager = get_credit_manager()
        user_id = current_user.get("uid")
        
        # Get current credits
        current_credits = await credit_manager.get_user_credits(user_id)
        
        # Get credit history (last 30 days)
        credit_history = await credit_manager.get_credit_history(user_id, days=30)
        
        # Calculate some basic stats
        total_spent = sum([abs(entry.get('amount', 0)) for entry in credit_history if entry.get('amount', 0) < 0])
        total_earned = sum([entry.get('amount', 0) for entry in credit_history if entry.get('amount', 0) > 0])
        
        # Get last login (for now, use current time)
        last_login = datetime.now().isoformat()
        
        stats = {
            "currentCredits": current_credits,
            "totalSpent": total_spent,
            "totalEarned": total_earned,
            "lastLogin": last_login,
            "totalNotes": len([entry for entry in credit_history if entry.get('amount', 0) < 0]),  # Approximate
            "storageUsed": 0,  # Not applicable for educational notes
            "averageNotesSize": 0  # Not applicable
        }
        
        return {
            "success": True,
            "statistics": stats,
            "creditHistory": credit_history[-10:]  # Last 10 transactions
        }
        
    except Exception as e:
        logger.error(f"Error getting user statistics for user {current_user.get('uid')}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user statistics: {str(e)}")

# Webhook Endpoints

@app.post("/webhooks/paddle")
async def handle_paddle_webhook(request: Request):
    """Handle Paddle webhook for payment processing"""
    try:
        from utils.paddle_webhook import handle_paddle_webhook as process_webhook
        
        # Get the raw body and headers
        body = await request.body()
        headers = dict(request.headers)
        
        # Process the webhook
        result = await process_webhook(body, headers)
        
        if result.get("success"):
            logger.info(f"Paddle webhook processed successfully: {result.get('event_type')}")
            return {"status": "success"}
        else:
            logger.error(f"Paddle webhook processing failed: {result.get('error')}")
            raise HTTPException(status_code=400, detail=result.get("error"))
            
    except Exception as e:
        logger.error(f"Error processing Paddle webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")

# Test Endpoints (for development)

@app.post("/test/allocate-credits")
async def test_allocate_credits(request: CreditAllocationRequest, current_user: dict = Depends(get_current_user)):
    """Test endpoint for allocating credits (development only)"""
    try:
        credit_manager = get_credit_manager()
        
        result = await credit_manager.add_credits(
            user_id=request.user_id,
            credits=request.credits,
            reason=request.reason,
            transaction_id=request.transaction_id or f"test_{datetime.now().timestamp()}"
        )
        
        logger.info(f"Test credits allocated: {request.credits} to user {request.user_id}")
        return result
        
    except Exception as e:
        logger.error(f"Error in test credit allocation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to allocate credits: {str(e)}")

@app.get("/webhooks/paddle/test")
async def test_paddle_webhook():
    """Test endpoint to verify Paddle webhook configuration"""
    return {
        "status": "success",
        "message": "Paddle webhook endpoint is accessible",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/test/simple-credit-allocation")
async def test_simple_credit_allocation(request: CreditAllocationRequest):
    """Simple test endpoint for credit allocation without auth"""
    try:
        credit_manager = get_credit_manager()
        
        # Add credits directly
        result = await credit_manager.add_credits(
            user_id=request.user_id,
            credits=request.credits,
            reason=request.reason,
            transaction_id=request.transaction_id or f"simple_test_{datetime.now().timestamp()}"
        )
        
        # Get updated balance
        current_credits = await credit_manager.get_user_credits(request.user_id)
        
        logger.info(f"Simple test credits allocated: {request.credits} to user {request.user_id}, new balance: {current_credits}")
        
        return {
            "success": True,
            "message": f"Allocated {request.credits} credits to user {request.user_id}",
            "new_balance": current_credits,
            "transaction_details": result
        }
        
    except Exception as e:
        logger.error(f"Error in simple credit allocation test: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to allocate credits: {str(e)}")

@app.post("/test/llama")
async def test_llama_groq(request: LlamaTestRequest):
    """Test endpoint for Llama model via Groq"""
    try:
        from utils.groq_client import sync_chat_completion
        
        logger.info(f"Testing Llama with prompt: {request.prompt[:100]}...")
        
        response = sync_chat_completion(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": request.prompt}],
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        if response:
            logger.info("✅ Llama test successful")
            return {
                "success": True,
                "response": response,
                "model": "llama-3.1-8b-instant",
                "timestamp": datetime.now().isoformat()
            }
        else:
            logger.error("❌ Llama test failed - no response")
            return {
                "success": False,
                "error": "No response from Llama model",
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"❌ Llama test failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Llama test failed: {str(e)}")

@app.get("/test/llama/status")
async def get_llama_status():
    """Get status of Llama model availability"""
    try:
        from utils.groq_client import sync_chat_completion
        
        # Test with a simple prompt
        test_response = sync_chat_completion(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Hello, respond with 'OK' if you're working."}],
            temperature=0.1,
            max_tokens=10
        )
        
        if test_response and "ok" in test_response.lower():
            return {
                "status": "healthy",
                "model": "llama-3.1-8b-instant",
                "available": True,
                "test_response": test_response,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "status": "unhealthy",
                "model": "llama-3.1-8b-instant", 
                "available": False,
                "test_response": test_response,
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Llama status check failed: {str(e)}")
        return {
            "status": "error",
            "model": "llama-3.1-8b-instant",
            "available": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Email Service Endpoints

@app.post("/send-welcome-email")
async def send_welcome_email(request: Request, email_request: WelcomeEmailRequest, current_user: dict = Depends(require_auth)):
    """Send welcome email to user"""
    try:
        result = await mjml_email_service.send_welcome_email(
            to_email=email_request.email,
            user_name=email_request.name
        )
        
        if result.get("success"):
            logger.info(f"Welcome email sent to {email_request.email}")
            return {"success": True, "message": "Welcome email sent successfully"}
        else:
            logger.error(f"Failed to send welcome email to {email_request.email}: {result.get('error')}")
            raise HTTPException(status_code=500, detail=f"Failed to send email: {result.get('error')}")
            
    except Exception as e:
        logger.error(f"Error sending welcome email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@app.post("/send-welcome-email-public")
async def send_welcome_email_public(request: Request, email_request: WelcomeEmailRequest):
    """Send welcome email (public endpoint for testing)"""
    try:
        result = await mjml_email_service.send_welcome_email(
            to_email=email_request.email,
            user_name=email_request.name
        )
        
        if result.get("success"):
            logger.info(f"Welcome email sent to {email_request.email} (public)")
            return {"success": True, "message": "Welcome email sent successfully"}
        else:
            logger.error(f"Failed to send welcome email to {email_request.email}: {result.get('error')}")
            raise HTTPException(status_code=500, detail=f"Failed to send email: {result.get('error')}")
            
    except Exception as e:
        logger.error(f"Error sending welcome email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@app.get("/email-service-status")
async def get_email_service_status(current_user: dict = Depends(require_auth)):
    """Get email service status"""
    try:
        status = await mjml_email_service.get_service_status()
        return {
            "success": True,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting email service status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get email service status: {str(e)}")

# Deep Explanation Endpoint

@app.post("/explain/deep")
async def get_deep_explanation(request: Request, explanation_request: DeepExplanationRequest, current_user: dict = Depends(require_auth)):
    """Get deep explanation of a concept using Llama model"""
    try:
        from utils.groq_client import sync_chat_completion
        
        # Create a comprehensive prompt for deep explanation
        prompt = f"""You are an expert educator and researcher. Provide a comprehensive, detailed explanation of the following concept:

CONCEPT: {explanation_request.concept}

CONTEXT: {explanation_request.context}

DETAIL LEVEL: {explanation_request.detail_level}

Please provide a thorough explanation that includes:
1. Clear definition and core principles
2. Historical background and development
3. Key components and how they work
4. Real-world applications and examples
5. Common misconceptions and clarifications
6. Related concepts and connections
7. Current research and future directions
8. Practical implications and significance

Make the explanation educational, engaging, and appropriate for the specified detail level."""

        response = sync_chat_completion(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4000
        )
        
        if response:
            logger.info(f"Deep explanation generated for concept: {explanation_request.concept}")
            return {
                "success": True,
                "concept": explanation_request.concept,
                "explanation": response,
                "detail_level": explanation_request.detail_level,
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to generate explanation")
            
    except Exception as e:
        logger.error(f"Error generating deep explanation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate explanation: {str(e)}")

# Notes Management Endpoints
@app.get("/notes")
async def get_user_notes(request: Request, current_user: dict = Depends(require_auth)):
    """Get all notes for the current user"""
    try:
        r2_storage = get_r2_storage()
        user_id = current_user['uid']
        
        # Get notes from R2 storage
        notes_list = await r2_storage.list_user_notes(user_id, limit=100)
        
        return {
            "success": True,
            "notes": notes_list,
            "total": len(notes_list)
        }
        
    except Exception as e:
        logger.error(f"Error fetching user notes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch notes: {str(e)}")

@app.post("/notes/save")
async def save_notes(request: Request, note_request: NoteSaveRequest, current_user: dict = Depends(require_auth)):
    """Save new educational notes"""
    try:
        r2_storage = get_r2_storage()
        user_id = current_user['uid']
        
        # Save notes to R2 storage
        result = await r2_storage.save_notes(
            user_id=user_id,
            notes_data=note_request.notes_data,
            title=note_request.title,
            encrypt=note_request.encrypt
        )
        
        logger.info(f"Notes saved successfully for user {user_id} with ID {result['note_id']}")
        
        return {
            "success": True,
            "note_id": result["note_id"],
            "title": result["metadata"]["title"],
            "message": "Notes saved successfully"
        }
        
    except Exception as e:
        logger.error(f"Error saving notes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save notes: {str(e)}")

@app.get("/notes/{note_id}")
async def get_note(note_id: str, request: Request, current_user: dict = Depends(require_auth)):
    """Get a specific note by ID"""
    try:
        r2_storage = get_r2_storage()
        user_id = current_user['uid']
        
        # Get the note from R2 storage
        note_data = await r2_storage.get_notes(user_id, note_id)
        
        if not note_data:
            raise HTTPException(status_code=404, detail="Note not found")
        
        return {
            "success": True,
            "note_id": note_id,
            "title": note_data["metadata"]["title"],
            "notes_data": note_data["notes_data"],
            "created_at": note_data["metadata"]["created_at"],
            "updated_at": note_data["metadata"].get("updated_at"),
            "source_type": note_data["metadata"].get("source_type", "educational_notes")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching note {note_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch note: {str(e)}")

@app.put("/notes/{note_id}")
async def update_note(note_id: str, request: Request, note_update: NoteUpdateRequest, current_user: dict = Depends(require_auth)):
    """Update a note (title or content)"""
    try:
        r2_storage = get_r2_storage()
        user_id = current_user['uid']
        
        # Update the note in R2 storage
        result = await r2_storage.update_notes(
            user_id=user_id,
            note_id=note_id,
            title=note_update.title,
            notes_data=note_update.notes_data
        )
        
        if not result:
            raise HTTPException(status_code=404, detail="Note not found")
        
        logger.info(f"Note {note_id} updated successfully for user {user_id}")
        
        return {
            "success": True,
            "note_id": note_id,
            "message": "Note updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating note {note_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update note: {str(e)}")

@app.delete("/notes/{note_id}")
async def delete_note(note_id: str, request: Request, current_user: dict = Depends(require_auth)):
    """Delete a note"""
    try:
        r2_storage = get_r2_storage()
        user_id = current_user['uid']
        
        # Delete the note from R2 storage
        success = await r2_storage.delete_notes(user_id, note_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Note not found")
        
        logger.info(f"Note {note_id} deleted successfully for user {user_id}")
        
        return {
            "success": True,
            "message": "Note deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting note {note_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete note: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)