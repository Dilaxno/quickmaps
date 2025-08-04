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
from utils.transcription import transcribe_video
from utils.summarizer import summarize_transcript as summarize_transcript
from utils.mindmap import generate_mindmap
from utils.firebase_auth import require_auth, optional_auth, get_current_user
from utils.ip_detection import get_vpn_detector
from utils.device_fingerprint import get_device_manager
from utils.credit_manager import get_credit_manager
from utils.r2_storage import get_r2_storage
from utils.mjml_email_service import mjml_email_service

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

class MindMapSave(BaseModel):
    mindmap_data: dict
    title: str = "Untitled Mind Map"
    encrypt: bool = True

class MindMapResponse(BaseModel):
    mindmap_id: str
    title: str
    created_at: str
    mindmap_data: dict = None

class UserSettingsUpdate(BaseModel):
    notifications: dict = None
    privacy: dict = None
    preferences: dict = None

class VimeoURL(BaseModel):
    url: str

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
        
        # Try to get download links
        download_response = client.get(f'/videos/{video_id}', params={'fields': 'download'})
        if download_response.status_code == 200:
            download_data = download_response.json()
            downloads = download_data.get('download', [])
            
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
        
        # If direct download fails, try to get streaming URLs
        files = video_data.get('files', [])
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
        
        raise Exception("No downloadable files found")
        
    except Exception as e:
        logger.error(f"Vimeo API download failed: {str(e)}")
        raise

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
        "name": current_user.get("name") or current_user.get("display_name"),
        "displayName": current_user.get("name") or current_user.get("display_name"),
        "picture": current_user.get("picture") or current_user.get("photo_url"),
        "photoURL": current_user.get("picture") or current_user.get("photo_url"),
        "email_verified": current_user.get("email_verified", False),
        "credits": credits
    }

@app.post("/auth/verify")
async def verify_token(request: Request, current_user: Optional[dict] = Depends(get_current_user)):
    """Verify if the provided token is valid"""
    if current_user:
        return {"valid": True, "user": current_user}
    else:
        return {"valid": False, "user": None}

# Credit Management Endpoints

@app.get("/credits/balance")
async def get_credit_balance(request: Request, current_user: dict = Depends(require_auth)):
    """Get current credit balance for the authenticated user"""
    credit_manager = get_credit_manager()
    credits = await credit_manager.get_user_credits(current_user.get("uid"))
    
    return {
        "user_id": current_user.get("uid"),
        "credits": credits,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/credits/check/{required_credits}")
async def check_sufficient_credits(required_credits: int, request: Request, current_user: dict = Depends(require_auth)):
    """Check if user has sufficient credits for an operation"""
    credit_manager = get_credit_manager()
    result = await credit_manager.check_sufficient_credits(current_user.get("uid"), required_credits)
    
    return {
        "user_id": current_user.get("uid"),
        "check_result": result,
        "timestamp": datetime.now().isoformat()
    }

class CreditGrantRequest(BaseModel):
    amount: int
    reason: str = "admin_grant"

@app.post("/credits/grant")
async def grant_credits(credit_request: CreditGrantRequest, request: Request, current_user: dict = Depends(require_auth)):
    """Grant credits to the authenticated user (for admin use or purchases)"""
    credit_manager = get_credit_manager()
    result = await credit_manager.add_credits(
        current_user.get("uid"), 
        credit_request.amount, 
        credit_request.reason
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to grant credits"))
    
    return {
        "user_id": current_user.get("uid"),
        "grant_result": result,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/credits/confirm/{operation_id}")
async def confirm_credit_deduction(operation_id: str, request: Request, current_user: dict = Depends(require_auth)):
    """Confirm credit deduction after successful mindmap display in frontend"""
    credit_manager = get_credit_manager()
    user_id = current_user.get('uid')
    
    try:
        result = await credit_manager.confirm_credit_deduction(user_id, operation_id)
        if result.get('success'):
            logger.info(f"Credit deduction confirmed for user {user_id}, operation {operation_id}")
            return {
                "success": True,
                "message": "Credits deducted successfully",
                "credits_deducted": result.get('credits_deducted'),
                "new_balance": result.get('new_balance'),
                "operation_id": operation_id,
                "timestamp": datetime.now().isoformat()
            }
        else:
            logger.error(f"Failed to confirm credit deduction for user {user_id}, operation {operation_id}: {result.get('error')}")
            raise HTTPException(status_code=400, detail=f"Failed to confirm credit deduction: {result.get('error')}")
    except Exception as e:
        logger.error(f"Error confirming credit deduction: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error confirming credit deduction: {str(e)}")

@app.post("/credits/release/{operation_id}")
async def release_reserved_credits(operation_id: str, request: Request, current_user: dict = Depends(require_auth)):
    """Release reserved credits if frontend fails to display mindmap"""
    credit_manager = get_credit_manager()
    user_id = current_user.get('uid')
    
    try:
        result = await credit_manager.release_reserved_credits(user_id, operation_id)
        if result.get('success'):
            logger.info(f"Reserved credits released for user {user_id}, operation {operation_id}")
            return {
                "success": True,
                "message": "Reserved credits released successfully",
                "credits_released": result.get('credits_released'),
                "operation_id": operation_id,
                "timestamp": datetime.now().isoformat()
            }
        else:
            logger.warning(f"Failed to release reserved credits for user {user_id}, operation {operation_id}: {result.get('error')}")
            # Don't throw an error here as the reservation might already be released
            return {
                "success": True,
                "message": "No reservation found or already released",
                "credits_released": 0,
                "operation_id": operation_id,
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        logger.error(f"Error releasing reserved credits: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error releasing reserved credits: {str(e)}")

@app.post("/credits/cleanup")
async def cleanup_expired_reservations(request: Request, current_user: dict = Depends(require_auth)):
    """Clean up expired credit reservations for the current user"""
    credit_manager = get_credit_manager()
    user_id = current_user.get('uid')
    
    try:
        result = await credit_manager.cleanup_expired_reservations(user_id)
        return {
            "success": True,
            "message": "Cleanup completed",
            "credits_released": result.get('credits_released'),
            "operations_cleaned": result.get('operations_cleaned'),
            "expired_operations": result.get('expired_operations'),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error cleaning up expired reservations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error cleaning up expired reservations: {str(e)}")

@app.post("/upload/")
async def upload_video(request: Request, file: UploadFile = File(...), current_user: dict = Depends(require_auth)):
    credit_manager = get_credit_manager()
    user_id = current_user.get('uid')
    operation_id = None
    
    try:
        # Check if user has sufficient credits
        credit_check = await credit_manager.check_sufficient_credits(user_id)
        if not credit_check.get('sufficient'):
            raise HTTPException(
                status_code=402, 
                detail=f"Insufficient credits. Required: {credit_check.get('required_credits')}, Available: {credit_check.get('current_credits')}"
            )
        
        # Reserve credits (don't deduct yet)
        reservation_result = await credit_manager.reserve_credits(user_id)
        if not reservation_result.get('success'):
            raise HTTPException(status_code=400, detail=f"Failed to reserve credits: {reservation_result.get('error')}")
        
        operation_id = reservation_result.get('operation_id')
        logger.info(f"Credits reserved for user {user_id}: {reservation_result.get('credits_reserved')} credits (Operation: {operation_id})")
        
        # Ensure videos directory exists
        os.makedirs("videos", exist_ok=True)
        
        filepath = f"videos/{file.filename}"
        with open(filepath, "wb") as f:
            f.write(await file.read())
        
        logger.info(f"File uploaded by user {user_id}: {filepath}")
        
        try:
            result = process_video(filepath)
            logger.info(f"Video processing completed successfully for user {user_id}")
            
            # Add operation_id to result so frontend can confirm the transaction
            result['operation_id'] = operation_id
            result['credits_reserved'] = reservation_result.get('credits_reserved')
            
            return result
        except Exception as processing_error:
            # If video processing fails, release the reserved credits
            logger.error(f"Video processing failed for user {user_id}: {str(processing_error)}")
            release_result = await credit_manager.release_reserved_credits(user_id, operation_id)
            if release_result.get('success'):
                logger.info(f"Reserved credits released for user {user_id}: {release_result.get('credits_released')} credits")
            else:
                logger.error(f"Failed to release reserved credits for user {user_id}: {release_result.get('error')}")
            
            raise HTTPException(status_code=500, detail=f"Error processing video: {str(processing_error)}")
            
    except HTTPException:
        # Re-raise HTTP exceptions (like insufficient credits)
        if operation_id:
            # Release reserved credits if any HTTP exception occurs
            await credit_manager.release_reserved_credits(user_id, operation_id)
        raise
    except Exception as e:
        logger.error(f"Error processing upload: {str(e)}")
        if operation_id:
            # Release reserved credits if any exception occurs
            await credit_manager.release_reserved_credits(user_id, operation_id)
        raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")

@app.post("/youtube/")
async def process_youtube(request: Request, youtube: YouTubeURL, current_user: dict = Depends(require_auth)):
    credit_manager = get_credit_manager()
    user_id = current_user.get('uid')
    operation_id = None
    
    try:
        # Check if user has sufficient credits
        credit_check = await credit_manager.check_sufficient_credits(user_id)
        if not credit_check.get('sufficient'):
            raise HTTPException(
                status_code=402, 
                detail=f"Insufficient credits. Required: {credit_check.get('required_credits')}, Available: {credit_check.get('current_credits')}"
            )
        
        # Reserve credits (don't deduct yet)
        reservation_result = await credit_manager.reserve_credits(user_id)
        if not reservation_result.get('success'):
            raise HTTPException(status_code=400, detail=f"Failed to reserve credits: {reservation_result.get('error')}")
        
        operation_id = reservation_result.get('operation_id')
        logger.info(f"Credits reserved for user {user_id}: {reservation_result.get('credits_reserved')} credits (Operation: {operation_id})")
        
        # Ensure videos directory exists
        os.makedirs("videos", exist_ok=True)
        
        # Create unique filename for each download to avoid conflicts
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        output_path = f"videos/youtube_video_{unique_id}.%(ext)s"
        logger.info(f"User {user_id} downloading YouTube video: {youtube.url}")
        
        actual_path = None  # Initialize for cleanup in error handlers
        try:
            # Use enhanced yt-dlp options with better anti-bot measures
            cmd = [
                "yt-dlp",
                "--format", "best[height<=720][ext=mp4]/best[ext=mp4]/best",
                "--output", output_path,
                "--no-playlist",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "--referer", "https://www.youtube.com/",
                "--add-header", "Accept-Language:en-US,en;q=0.9",
                "--add-header", "Accept:text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "--add-header", "Accept-Encoding:gzip, deflate, br",
                "--add-header", "DNT:1",
                "--add-header", "Connection:keep-alive",
                "--add-header", "Upgrade-Insecure-Requests:1",
                "--throttled-rate", "100K",
                "--sleep-interval", "1",
                "--max-sleep-interval", "5",
                "--force-overwrites",  # Force overwrite existing files
                "--no-check-certificates",  # Skip SSL certificate verification
                "--prefer-insecure",  # Use HTTP instead of HTTPS when possible
                "--socket-timeout", "30",  # Set socket timeout
                "--retries", "3",  # Retry failed downloads
                "--fragment-retries", "3",  # Retry failed fragments
                "--extractor-retries", "3",  # Retry extractor failures
                youtube.url
            ]
            
            # Try the download with enhanced options
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                logger.info(f"yt-dlp output: {result.stdout}")
            except subprocess.CalledProcessError as first_error:
                logger.warning(f"First download attempt failed: {first_error.stderr}")
                logger.info("Trying with simpler format and fewer restrictions...")
                
                # Fallback with simpler options
                cmd_fallback = [
                    "yt-dlp",
                    "--format", "worst[ext=mp4]/worst",  # Use worst quality as fallback
                    "--output", output_path,
                    "--no-playlist",
                    "--force-overwrites",
                    "--retries", "5",
                    "--socket-timeout", "60",
                    youtube.url
                ]
                result = subprocess.run(cmd_fallback, capture_output=True, text=True, check=True)
                logger.info(f"yt-dlp fallback successful: {result.stdout}")
            
            # Find the actual downloaded file
            import glob
            downloaded_files = glob.glob(f"videos/youtube_video_{unique_id}.*")
            if not downloaded_files:
                raise Exception("Failed to download video")
            
            actual_path = downloaded_files[0]
            logger.info(f"Downloaded file: {actual_path}")
            
            # Process the video
            processing_result = process_video(actual_path)
            logger.info(f"YouTube video processing completed successfully for user {user_id}")
            
            # Auto-save the mind map to prevent data loss
            try:
                r2_storage = get_r2_storage()
                
                # Extract video title from URL or use default
                video_title = f"YouTube Video Mind Map - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                
                # Save the mind map automatically
                save_result = await r2_storage.save_mindmap(
                    user_id=user_id,
                    mindmap_data=processing_result,
                    title=video_title,
                    encrypt=True
                )
                
                # Add the saved mind map info to the response
                processing_result['auto_saved'] = True
                processing_result['mindmap_id'] = save_result['mindmap_id']
                processing_result['saved_title'] = video_title
                
                logger.info(f"Mind map auto-saved for user {user_id}: {save_result['mindmap_id']}")
                
            except Exception as save_error:
                logger.warning(f"Failed to auto-save mind map for user {user_id}: {save_error}")
                processing_result['auto_saved'] = False
                processing_result['save_error'] = str(save_error)
            
            # Clean up the downloaded file to save disk space
            try:
                os.remove(actual_path)
                logger.info(f"Cleaned up downloaded file: {actual_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up file {actual_path}: {cleanup_error}")
            
            # Add operation_id to result so frontend can confirm the transaction
            processing_result['operation_id'] = operation_id
            processing_result['credits_reserved'] = reservation_result.get('credits_reserved')
            
            # Log response size for debugging
            try:
                import json
                response_json = json.dumps(processing_result)
                response_size = len(response_json)
                logger.info(f"Response size: {response_size} bytes ({response_size/1024:.1f} KB)")
                
                # Check if response is too large (>10MB)
                if response_size > 10 * 1024 * 1024:
                    logger.warning(f"Response size is very large: {response_size/1024/1024:.1f} MB")
                
                # Validate JSON serialization
                logger.info("Response JSON serialization successful")
                
            except Exception as json_error:
                logger.error(f"JSON serialization error: {json_error}")
                # Try to identify the problematic part
                try:
                    json.dumps(processing_result.get('mindmap', {}))
                    logger.info("Mind map data is JSON serializable")
                except:
                    logger.error("Mind map data is NOT JSON serializable")
            
            logger.info(f"Returning YouTube processing result for user {user_id}")
            return processing_result
            
        except subprocess.CalledProcessError as e:
            logger.error(f"yt-dlp error for user {user_id}: {e.stderr}")
            
            # Clean up any partially downloaded files
            try:
                import glob
                downloaded_files = glob.glob(f"videos/youtube_video_{unique_id}.*")
                for file_path in downloaded_files:
                    os.remove(file_path)
                    logger.info(f"Cleaned up partial download: {file_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up partial downloads: {cleanup_error}")
            
            # Release reserved credits on download failure
            release_result = await credit_manager.release_reserved_credits(user_id, operation_id)
            if release_result.get('success'):
                logger.info(f"Reserved credits released for user {user_id}: {release_result.get('credits_released')} credits")
            raise HTTPException(status_code=500, detail=f"Failed to download video: {e.stderr}")
            
        except Exception as processing_error:
            logger.error(f"YouTube video processing failed for user {user_id}: {str(processing_error)}")
            
            # Clean up downloaded file if it exists
            try:
                import glob
                downloaded_files = glob.glob(f"videos/youtube_video_{unique_id}.*")
                for file_path in downloaded_files:
                    os.remove(file_path)
                    logger.info(f"Cleaned up file after error: {file_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up files after error: {cleanup_error}")
            
            # Release reserved credits on processing failure
            release_result = await credit_manager.release_reserved_credits(user_id, operation_id)
            if release_result.get('success'):
                logger.info(f"Reserved credits released for user {user_id}: {release_result.get('credits_released')} credits")
            else:
                logger.error(f"Failed to release reserved credits for user {user_id}: {release_result.get('error')}")
            
            raise HTTPException(status_code=500, detail=f"Error processing video: {str(processing_error)}")
        
    except HTTPException:
        # Re-raise HTTP exceptions (like insufficient credits)
        if operation_id:
            # Release reserved credits if any HTTP exception occurs
            await credit_manager.release_reserved_credits(user_id, operation_id)
        raise
    except Exception as e:
        logger.error(f"Error processing YouTube video: {str(e)}")
        if operation_id:
            # Release reserved credits if any exception occurs
            await credit_manager.release_reserved_credits(user_id, operation_id)
        raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")

@app.post("/vimeo/")
async def process_vimeo(request: Request, vimeo: VimeoURL, current_user: dict = Depends(require_auth)):
    credit_manager = get_credit_manager()
    user_id = current_user.get('uid')
    operation_id = None
    
    try:
        # Check if user has sufficient credits
        credit_check = await credit_manager.check_sufficient_credits(user_id)
        if not credit_check.get('sufficient'):
            raise HTTPException(
                status_code=402, 
                detail=f"Insufficient credits. Required: {credit_check.get('required_credits')}, Available: {credit_check.get('current_credits')}"
            )
        
        # Reserve credits (don't deduct yet)
        reservation_result = await credit_manager.reserve_credits(user_id)
        if not reservation_result.get('success'):
            raise HTTPException(status_code=400, detail=f"Failed to reserve credits: {reservation_result.get('error')}")
        
        operation_id = reservation_result.get('operation_id')
        logger.info(f"Credits reserved for user {user_id}: {reservation_result.get('credits_reserved')} credits (Operation: {operation_id})")
        
        # Ensure videos directory exists
        os.makedirs("videos", exist_ok=True)
        
        # Create unique filename for each download to avoid conflicts
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        output_path = f"videos/vimeo_video_{unique_id}.%(ext)s"
        logger.info(f"User {user_id} downloading Vimeo video: {vimeo.url}")
        
        actual_path = None  # Initialize for cleanup in error handlers
        try:
            # Use yt-dlp for Vimeo downloads with improved options
            cmd = [
                "yt-dlp",
                "--format", "best[height<=720][ext=mp4]/best[ext=mp4]/best",
                "--output", output_path,
                "--no-playlist",
                "--no-check-certificates",
                "--force-overwrites",
                "--socket-timeout", "30",
                "--retries", "5",
                "--fragment-retries", "5",
                "--extractor-retries", "5",
                "--ignore-errors",
                "--no-warnings",
                # Remove impersonation-related options that cause issues
                vimeo.url
            ]
            
            # Try the download with basic options first
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                logger.info(f"yt-dlp output: {result.stdout}")
            except subprocess.CalledProcessError as first_error:
                logger.warning(f"First download attempt failed: {first_error.stderr}")
                logger.info("Trying with audio-only extraction...")
                
                # Fallback to audio-only extraction (which works better for Vimeo)
                cmd_audio = [
                    "yt-dlp",
                    "--format", "bestaudio[ext=m4a]/bestaudio/best",
                    "--output", output_path,
                    "--no-playlist",
                    "--force-overwrites",
                    "--retries", "10",
                    "--socket-timeout", "60",
                    "--ignore-errors",
                    "--extract-flat", "false",
                    vimeo.url
                ]
                
                try:
                    result = subprocess.run(cmd_audio, capture_output=True, text=True, check=True)
                    logger.info(f"yt-dlp audio extraction successful: {result.stdout}")
                except subprocess.CalledProcessError as second_error:
                    logger.warning(f"Audio extraction failed: {second_error.stderr}")
                    logger.info("Trying with minimal options...")
                    
                    # Final fallback with absolute minimal options
                    cmd_minimal = [
                        "yt-dlp",
                        "--output", output_path,
                        "--no-playlist",
                        "--force-overwrites",
                        "--ignore-errors",
                        vimeo.url
                    ]
                    
                    try:
                        result = subprocess.run(cmd_minimal, capture_output=True, text=True, check=True)
                        logger.info(f"yt-dlp minimal extraction successful: {result.stdout}")
                    except subprocess.CalledProcessError as third_error:
                        logger.warning(f"All yt-dlp attempts failed: {third_error.stderr}")
                        logger.info("Trying alternative yt-dlp approach for Vimeo...")
                        
                        # Try alternative yt-dlp approach for Vimeo
                        cmd_vimeo_alt = [
                            "yt-dlp",
                            "--format", "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio",
                            "--output", output_path,
                            "--no-playlist",
                            "--force-overwrites",
                            "--ignore-errors",
                            "--no-check-certificates",
                            "--extract-flat", "false",
                            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            vimeo.url
                        ]
                        
                        try:
                            result = subprocess.run(cmd_vimeo_alt, capture_output=True, text=True, check=True)
                            logger.info(f"Alternative yt-dlp successful: {result.stdout}")
                        except subprocess.CalledProcessError as alt_error:
                            logger.warning(f"Alternative yt-dlp also failed: {alt_error.stderr}")
                            
                            # Try one more simple approach
                            logger.info("Trying simplest yt-dlp approach...")
                            cmd_simple = [
                                "yt-dlp",
                                "--extract-audio",
                                "--audio-format", "mp3",
                                "--output", output_path,
                                "--no-playlist",
                                "--force-overwrites",
                                vimeo.url
                            ]
                            
                            try:
                                result = subprocess.run(cmd_simple, capture_output=True, text=True, check=True)
                                logger.info(f"Simple yt-dlp successful: {result.stdout}")
                            except subprocess.CalledProcessError as simple_error:
                                logger.warning(f"Simple yt-dlp also failed: {simple_error.stderr}")
                                
                                # Final attempt: Try Vimeo API as last resort
                            video_id = extract_vimeo_id(vimeo.url)
                            if video_id and vimeo:
                                access_token = os.getenv("VIMEO_ACCESS_TOKEN")
                                if access_token and access_token != "your_vimeo_access_token_here":
                                    try:
                                        # Create a proper output path for API download
                                        api_output_path = f"videos/vimeo_video_{unique_id}.mp4"
                                        download_vimeo_with_api(video_id, api_output_path, access_token)
                                        logger.info(f"Vimeo API download successful: {api_output_path}")
                                    except Exception as api_error:
                                        logger.error(f"Vimeo API download also failed: {str(api_error)}")
                                        raise subprocess.CalledProcessError(1, cmd_minimal, stderr=f"All download methods failed. Last error: {str(api_error)}")
                                else:
                                    logger.error("Vimeo access token not configured")
                                    raise subprocess.CalledProcessError(1, cmd_minimal, stderr="All download methods failed and Vimeo API not configured")
                            else:
                                logger.error("Could not extract video ID or PyVimeo not available")
                                raise subprocess.CalledProcessError(1, cmd_minimal, stderr="All download methods failed")
            
            # Find the actual downloaded file
            import glob
            downloaded_files = glob.glob(f"videos/vimeo_video_{unique_id}.*")
            if not downloaded_files:
                raise Exception("Failed to download video")
            
            actual_path = downloaded_files[0]
            logger.info(f"Downloaded file: {actual_path}")
            
            # Process the video
            processing_result = process_video(actual_path)
            logger.info(f"Vimeo video processing completed successfully for user {user_id}")
            
            # Auto-save the mind map to prevent data loss
            try:
                r2_storage = get_r2_storage()
                
                # Extract video title from URL or use default
                video_title = f"Vimeo Video Mind Map - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                
                # Save the mind map automatically
                save_result = await r2_storage.save_mindmap(
                    user_id=user_id,
                    mindmap_data=processing_result,
                    title=video_title,
                    encrypt=True
                )
                
                # Add the saved mind map info to the response
                processing_result['auto_saved'] = True
                processing_result['mindmap_id'] = save_result['mindmap_id']
                processing_result['saved_title'] = video_title
                
                logger.info(f"Mind map auto-saved for user {user_id}: {save_result['mindmap_id']}")
                
            except Exception as save_error:
                logger.warning(f"Failed to auto-save mind map for user {user_id}: {save_error}")
                processing_result['auto_saved'] = False
                processing_result['save_error'] = str(save_error)
            
            # Clean up the downloaded file to save disk space
            try:
                os.remove(actual_path)
                logger.info(f"Cleaned up downloaded file: {actual_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up file {actual_path}: {cleanup_error}")
            
            # Add operation_id to result so frontend can confirm the transaction
            processing_result['operation_id'] = operation_id
            processing_result['credits_reserved'] = reservation_result.get('credits_reserved')
            
            logger.info(f"Returning Vimeo processing result for user {user_id}")
            return processing_result
            
        except subprocess.CalledProcessError as e:
            logger.error(f"yt-dlp error for user {user_id}: {e.stderr}")
            
            # Clean up any partially downloaded files
            try:
                import glob
                downloaded_files = glob.glob(f"videos/vimeo_video_{unique_id}.*")
                for file_path in downloaded_files:
                    os.remove(file_path)
                    logger.info(f"Cleaned up partial download: {file_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up partial downloads: {cleanup_error}")
            
            # Release reserved credits on download failure
            release_result = await credit_manager.release_reserved_credits(user_id, operation_id)
            if release_result.get('success'):
                logger.info(f"Reserved credits released for user {user_id}: {release_result.get('credits_released')} credits")
            raise HTTPException(status_code=500, detail=f"Failed to download video: {e.stderr}")
            
        except Exception as processing_error:
            logger.error(f"Vimeo video processing failed for user {user_id}: {str(processing_error)}")
            
            # Clean up downloaded file if it exists
            try:
                import glob
                downloaded_files = glob.glob(f"videos/vimeo_video_{unique_id}.*")
                for file_path in downloaded_files:
                    os.remove(file_path)
                    logger.info(f"Cleaned up file after error: {file_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up files after error: {cleanup_error}")
            
            # Release reserved credits on processing failure
            release_result = await credit_manager.release_reserved_credits(user_id, operation_id)
            if release_result.get('success'):
                logger.info(f"Reserved credits released for user {user_id}: {release_result.get('credits_released')} credits")
            else:
                logger.error(f"Failed to release reserved credits for user {user_id}: {release_result.get('error')}")
            
            raise HTTPException(status_code=500, detail=f"Error processing video: {str(processing_error)}")
        
    except HTTPException:
        # Re-raise HTTP exceptions (like insufficient credits)
        if operation_id:
            # Release reserved credits if any HTTP exception occurs
            await credit_manager.release_reserved_credits(user_id, operation_id)
        raise
    except Exception as e:
        logger.error(f"Error processing Vimeo video: {str(e)}")
        if operation_id:
            # Release reserved credits if any exception occurs
            await credit_manager.release_reserved_credits(user_id, operation_id)
        raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")

def process_video(filepath):
    try:
        logger.info(f"Processing video: {filepath}")
        
        # Check if file exists
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Video file not found: {filepath}")
        
        transcript = transcribe_video(filepath)
        logger.info("Transcription completed")
        
        structured_data = summarize_transcript(transcript)
        logger.info("Summarization completed")
        
        mindmap = generate_mindmap(structured_data)
        logger.info("Mind map generation completed")
        
        return mindmap
    except Exception as e:
        logger.error(f"Error in process_video: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")

# Mind Map Storage Endpoints

@app.post("/mindmaps/save")
async def save_mindmap(
    mindmap_request: MindMapSave, 
    request: Request, 
    current_user: dict = Depends(require_auth)
):
    """Save a mind map to R2 storage"""
    try:
        r2_storage = get_r2_storage()
        user_id = current_user.get("uid")
        
        result = await r2_storage.save_mindmap(
            user_id=user_id,
            mindmap_data=mindmap_request.mindmap_data,
            title=mindmap_request.title,
            encrypt=mindmap_request.encrypt
        )
        
        logger.info(f"Mind map saved for user {user_id}: {result['mindmap_id']}")
        
        return {
            "success": True,
            "mindmap_id": result["mindmap_id"],
            "title": mindmap_request.title,
            "created_at": result["metadata"]["created_at"],
            "message": "Mind map saved successfully"
        }
        
    except Exception as e:
        logger.error(f"Error saving mind map for user {current_user.get('uid')}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save mind map: {str(e)}")

@app.get("/mindmaps/{mindmap_id}")
async def get_mindmap(
    mindmap_id: str, 
    request: Request, 
    current_user: dict = Depends(require_auth)
):
    """Retrieve a specific mind map"""
    try:
        r2_storage = get_r2_storage()
        user_id = current_user.get("uid")
        
        mindmap_data = await r2_storage.get_mindmap(user_id, mindmap_id)
        
        if not mindmap_data:
            raise HTTPException(status_code=404, detail="Mind map not found")
        
        return {
            "success": True,
            "mindmap_id": mindmap_id,
            "title": mindmap_data["metadata"]["title"],
            "created_at": mindmap_data["metadata"]["created_at"],
            "mindmap_data": mindmap_data["mindmap"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving mind map {mindmap_id} for user {current_user.get('uid')}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve mind map: {str(e)}")

@app.get("/mindmaps")
async def list_mindmaps(
    request: Request, 
    current_user: dict = Depends(require_auth),
    limit: int = 50
):
    """List all mind maps for the authenticated user"""
    try:
        r2_storage = get_r2_storage()
        user_id = current_user.get("uid")
        
        mindmaps = await r2_storage.list_user_mindmaps(user_id, limit)
        
        return {
            "success": True,
            "mindmaps": mindmaps,
            "count": len(mindmaps)
        }
        
    except Exception as e:
        logger.error(f"Error listing mind maps for user {current_user.get('uid')}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list mind maps: {str(e)}")

@app.put("/mindmaps/{mindmap_id}")
async def update_mindmap(
    mindmap_id: str,
    mindmap_request: MindMapSave,
    request: Request,
    current_user: dict = Depends(require_auth)
):
    """Update a specific mind map (currently supports title updates)"""
    try:
        r2_storage = get_r2_storage()
        user_id = current_user.get("uid")
        
        # First, verify the mindmap exists and belongs to the user
        existing_mindmap = await r2_storage.get_mindmap(user_id, mindmap_id)
        if not existing_mindmap:
            raise HTTPException(status_code=404, detail="Mind map not found")
        
        # Update the mindmap with new title
        result = await r2_storage.update_mindmap(
            user_id=user_id,
            mindmap_id=mindmap_id,
            title=mindmap_request.title,
            mindmap_data=mindmap_request.mindmap_data if mindmap_request.mindmap_data else existing_mindmap["mindmap"]
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="Failed to update mind map")
        
        logger.info(f"Mind map updated for user {user_id}: {mindmap_id} - new title: {mindmap_request.title}")
        
        return {
            "success": True,
            "mindmap_id": mindmap_id,
            "title": mindmap_request.title,
            "updated_at": result.get("updated_at"),
            "message": "Mind map updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating mind map {mindmap_id} for user {current_user.get('uid')}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update mind map: {str(e)}")

@app.delete("/mindmaps/{mindmap_id}")
async def delete_mindmap(
    mindmap_id: str, 
    request: Request, 
    current_user: dict = Depends(require_auth)
):
    """Delete a specific mind map"""
    try:
        r2_storage = get_r2_storage()
        user_id = current_user.get("uid")
        
        success = await r2_storage.delete_mindmap(user_id, mindmap_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Mind map not found")
        
        logger.info(f"Mind map deleted for user {user_id}: {mindmap_id}")
        
        return {
            "success": True,
            "message": "Mind map deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting mind map {mindmap_id} for user {current_user.get('uid')}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete mind map: {str(e)}")

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
                "mindmapComplete": True,
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
                "autoDownload": False,
                "defaultEncryption": True
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
        user_id = current_user.get("uid")
        
        # In production, you would save these to a database
        # For now, we'll just return success
        logger.info(f"User {user_id} updated settings: {settings_update.dict()}")
        
        return {
            "success": True,
            "message": "Settings updated successfully",
            "updated_settings": settings_update.dict()
        }
        
    except Exception as e:
        logger.error(f"Error updating user settings for user {current_user.get('uid')}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update user settings: {str(e)}")

@app.get("/user/statistics")
async def get_user_statistics(request: Request, current_user: dict = Depends(require_auth)):
    """Get user usage statistics"""
    try:
        user_id = current_user.get("uid")
        r2_storage = get_r2_storage()
        credit_manager = get_credit_manager()
        
        # Get mind maps count
        mindmaps = await r2_storage.list_user_mindmaps(user_id, limit=1000)
        total_mindmaps = len(mindmaps)
        
        # Get credits info
        current_credits = await credit_manager.get_user_credits(user_id)
        
        # Calculate account age (you might want to store registration date)
        account_age_days = 30  # Placeholder
        
        # Get last login (from Firebase user metadata if available)
        last_login = current_user.get('last_sign_in_time') or datetime.now().isoformat()
        
        stats = {
            "totalMindMaps": total_mindmaps,
            "currentCredits": current_credits,
            "creditsUsed": 100 - current_credits,  # Assuming starting with 100
            "accountAgeDays": account_age_days,
            "lastLogin": last_login,
            "storageUsed": sum(mindmap.get('size', 0) for mindmap in mindmaps),
            "averageMindMapSize": sum(mindmap.get('size', 0) for mindmap in mindmaps) / max(total_mindmaps, 1)
        }
        
        return {
            "success": True,
            "statistics": stats
        }
        
    except Exception as e:
        logger.error(f"Error getting user statistics for user {current_user.get('uid')}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user statistics: {str(e)}")

# Paddle Webhook Endpoints

@app.post("/webhooks/paddle")
async def handle_paddle_webhook(request: Request):
    """Handle Paddle webhook notifications for subscription events"""
    try:
        # Get webhook secret from environment
        webhook_secret = os.getenv("PADDLE_WEBHOOK_SECRET")
        if not webhook_secret:
            logger.error("PADDLE_WEBHOOK_SECRET not configured")
            raise HTTPException(status_code=500, detail="Webhook secret not configured")
        
        # Get request body and signature
        body = await request.body()
        body_str = body.decode('utf-8')
        signature = request.headers.get("paddle-signature", "")
        
        # Parse webhook data
        try:
            webhook_data = json.loads(body_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse webhook JSON: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
        # Log the webhook data for debugging
        logger.info(f"🔔 Received Paddle webhook: {json.dumps(webhook_data, indent=2)}")
        logger.info(f"📋 Headers: {dict(request.headers)}")
        logger.info(f"🔑 Signature: {signature}")
        
        # Import and use webhook handler (pass body_str for signature verification)
        from utils.paddle_webhook import handle_paddle_webhook
        
        success = handle_paddle_webhook(webhook_data, signature, webhook_secret, body_str)
        
        if success:
            return {"status": "success", "message": "Webhook processed successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to process webhook")
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error processing Paddle webhook: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")

# Test endpoint to manually allocate credits (for debugging)
class CreditAllocationRequest(BaseModel):
    planId: str = 'student'
    billingPeriod: str = 'monthly'

@app.post("/test/allocate-credits")
async def test_allocate_credits(request: CreditAllocationRequest, current_user: dict = Depends(get_current_user)):
    """Test endpoint to manually allocate credits to a user"""
    try:
        plan_id = request.planId
        billing_period = request.billingPeriod
        user_id = current_user.get('uid')
        
        # Import webhook processor
        from utils.paddle_webhook import process_payment_completed
        
        # Create fake webhook data
        fake_webhook_data = {
            'event_type': 'transaction.completed',
            'data': {
                'id': f'test_txn_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}',
                'status': 'completed',
                'custom_data': {
                    'userId': user_id,
                    'planId': plan_id,
                    'billingPeriod': billing_period
                }
            }
        }
        
        success = process_payment_completed(fake_webhook_data)
        
        if success:
            return {
                "success": True,
                "message": f"Successfully allocated credits for {plan_id} {billing_period} plan",
                "userId": user_id
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to allocate credits")
            
    except Exception as e:
        logger.error(f"Error in test credit allocation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")

@app.get("/webhooks/paddle/test")
async def test_paddle_webhook():
    """Test endpoint to verify webhook configuration"""
    webhook_secret = os.getenv("PADDLE_WEBHOOK_SECRET")
    return {
        "status": "healthy",
        "webhook_secret_configured": bool(webhook_secret),
        "message": "Paddle webhook endpoint is ready"
    }

@app.post("/test/simple-credit-allocation")
async def test_simple_credit_allocation(request: CreditAllocationRequest):
    """Simple test endpoint to manually allocate credits without auth (for testing)"""
    try:
        plan_id = request.planId
        billing_period = request.billingPeriod
        # Use a test user ID for testing
        user_id = "test_user_simple_allocation"
        
        # Import webhook processor
        from utils.paddle_webhook import process_payment_completed
        
        # Create fake webhook data
        fake_webhook_data = {
            'event_type': 'transaction.completed',
            'data': {
                'id': f'test_txn_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}',
                'status': 'completed',
                'custom_data': {
                    'userId': user_id,
                    'planId': plan_id,
                    'billingPeriod': billing_period
                }
            }
        }
        
        success = process_payment_completed(fake_webhook_data)
        
        if success:
            return {
                "success": True,
                "message": f"Successfully allocated credits for {plan_id} {billing_period} plan",
                "userId": user_id,
                "testData": fake_webhook_data
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to allocate credits")
            
    except Exception as e:
        logger.error(f"Error in simple test credit allocation: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")

# LLaMA Groq Testing Endpoints

class LlamaTestRequest(BaseModel):
    text: str
    use_summarization: bool = True

@app.post("/test/llama")
async def test_llama_groq(request: LlamaTestRequest):
    """Test LLaMA model via Groq API for text generation and summarization"""
    try:
        from utils.groq_client import sync_generate_text, sync_chat_completion
        from utils.summarizer import get_llama_summarizer
        
        results = {
            "input_text": request.text,
            "text_length": len(request.text),
            "tests": {}
        }
        
        # Test 1: Simple text generation
        logger.info("Testing LLaMA text generation...")
        generation_result = sync_generate_text(
            model="llama-3.1-8b-instant",
            prompt=f"Analyze this text and provide 3 key insights: {request.text[:500]}",
            temperature=0.5,
            max_tokens=200
        )
        
        results["tests"]["text_generation"] = {
            "success": bool(generation_result),
            "response": generation_result[:300] if generation_result else None,
            "response_length": len(generation_result) if generation_result else 0
        }
        
        # Test 2: Chat completion
        logger.info("Testing LLaMA chat completion...")
        chat_result = sync_chat_completion(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a helpful educational assistant."},
                {"role": "user", "content": f"Summarize the main concepts in this text: {request.text[:600]}"}
            ],
            temperature=0.3,
            max_tokens=250
        )
        
        results["tests"]["chat_completion"] = {
            "success": bool(chat_result),
            "response": chat_result[:300] if chat_result else None,
            "response_length": len(chat_result) if chat_result else 0
        }
        
        # Test 3: Educational summarization (if enabled)
        if request.use_summarization and len(request.text) > 100:
            logger.info("Testing LLaMA educational summarization...")
            
            # Create dummy transcript segments
            segments = [{"text": request.text, "start": 0, "end": len(request.text)}]
            
            from utils.summarizer import summarize_transcript
            summary_result = summarize_transcript(segments)
            
            results["tests"]["educational_summarization"] = {
                "success": bool(summary_result),
                "summary_title": summary_result.get("title", "N/A"),
                "key_points_count": len(summary_result.get("key_points", [])),
                "definitions_count": len(summary_result.get("definitions", [])),
                "processing_model": summary_result.get("processing_model", "unknown"),
                "summary_preview": summary_result.get("summary", "")[:200] if summary_result.get("summary") else None
            }
        
        # Overall success determination
        successful_tests = sum(1 for test in results["tests"].values() if test["success"])
        total_tests = len(results["tests"])
        
        results["overall"] = {
            "success": successful_tests > 0,
            "successful_tests": successful_tests,
            "total_tests": total_tests,
            "success_rate": f"{(successful_tests/total_tests)*100:.1f}%" if total_tests > 0 else "0%"
        }
        
        return results
        
    except Exception as e:
        logger.error(f"Error testing LLaMA Groq: {str(e)}")
        raise HTTPException(status_code=500, detail=f"LLaMA test failed: {str(e)}")

@app.get("/test/llama/status")
async def get_llama_status():
    """Get the status of LLaMA integration"""
    try:
        from utils.groq_client import sync_generate_text, sync_chat_completion
        from utils.summarizer import get_llama_summarizer
        
        # Test basic connectivity
        test_response = sync_generate_text(
            model="llama-3.1-8b-instant",
            prompt="Hello, are you working?",
            max_tokens=20
        )
        
        groq_working = bool(test_response)
        
        # Test chat completion specifically
        chat_test = sync_chat_completion(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Say 'Hello World'"}],
            temperature=0.3,
            max_tokens=10
        )
        
        chat_working = bool(chat_test)
        
        # Test summarizer initialization
        summarizer = get_llama_summarizer(enable_llama=True)
        
        return {
            "groq_connection": groq_working,
            "test_response": test_response[:100] if test_response else None,
            "chat_completion_test": chat_working,
            "chat_response": chat_test[:100] if chat_test else None,
            "summarizer_status": {
                "use_groq": summarizer.use_groq,
                "use_fallback": summarizer.use_fallback,
                "groq_model": summarizer.groq_model
            },
            "recommendation": "✅ Ready for production" if groq_working and chat_working and summarizer.use_groq else "⚠️ Using fallback methods"
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Error checking LLaMA status: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "groq_connection": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "recommendation": "❌ LLaMA not available, check Groq API key"
        }

@app.get("/test/phi3/debug")
async def debug_phi3_connection():
    """Debug phi3 connection issues"""
    try:
        import requests
        
        # Direct API test
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        models_available = response.status_code == 200
        
        if models_available:
            models_data = response.json()
            models_list = [m.get('name', 'unknown') for m in models_data.get('models', [])]
        else:
            models_list = []
        
        # Test direct chat API call
        chat_payload = {
            "model": "phi3",
            "messages": [{"role": "user", "content": "Test message"}],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 20}
        }
        
        direct_chat_success = False
        direct_chat_error = None
        direct_chat_response = None
        
        try:
            chat_response = requests.post(
                "http://localhost:11434/api/chat",
                json=chat_payload,
                timeout=30
            )
            direct_chat_success = chat_response.status_code == 200
            if direct_chat_success:
                direct_chat_response = chat_response.json()
            else:
                direct_chat_error = f"Status {chat_response.status_code}: {chat_response.text}"
        except Exception as e:
            direct_chat_error = str(e)
        
        return {
            "server_accessible": models_available,
            "models_list": models_list,
            "phi3_available": "phi3" in str(models_list),
            "direct_chat_test": {
                "success": direct_chat_success,
                "error": direct_chat_error,
                "response_preview": str(direct_chat_response)[:200] if direct_chat_response else None
            },
            "diagnosis": "Check logs above for specific error details"
        }
        
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "diagnosis": "Failed to debug - check if Ollama server is running"
        }


# Email endpoints
class WelcomeEmailRequest(BaseModel):
    email: str
    name: Optional[str] = "User"

@app.post("/send-welcome-email")
async def send_welcome_email(request: Request, email_request: WelcomeEmailRequest, current_user: dict = Depends(require_auth)):
    """Send welcome email to user (authenticated endpoint)"""
    try:
        # Verify the user is requesting email for their own account
        user_email = current_user.get('email')
        if user_email != email_request.email:
            raise HTTPException(
                status_code=403,
                detail="You can only send welcome email to your own email address"
            )
        
        success = await mjml_email_service.send_welcome_email(
            recipient_email=email_request.email,
            recipient_name=email_request.name or current_user.get('name', 'User')
        )
        
        if success:
            return {"message": "Welcome email sent successfully", "email": email_request.email}
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send welcome email. Please try again later."
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending welcome email: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while sending email"
        )

@app.post("/send-welcome-email-public")
async def send_welcome_email_public(request: Request, email_request: WelcomeEmailRequest):
    """Send welcome email (public endpoint for signup process)"""
    try:
        # Add basic rate limiting by IP
        client_ip = request.client.host
        # In production, you'd want proper rate limiting here
        
        success = await mjml_email_service.send_welcome_email(
            recipient_email=email_request.email,
            recipient_name=email_request.name
        )
        
        if success:
            return {"message": "Welcome email sent successfully", "email": email_request.email}
        else:
            # Don't expose internal errors to public endpoint
            return {"message": "Email request processed", "email": email_request.email}
    
    except Exception as e:
        logger.error(f"Error sending public welcome email: {e}")
        # Return success even on error to prevent information leakage
        return {"message": "Email request processed", "email": email_request.email}

@app.get("/email-service-status")
async def get_email_service_status(current_user: dict = Depends(require_auth)):
    """Get email service status (admin endpoint)"""
    try:
        return {
            "enabled": mjml_email_service.enabled,
            "smtp_server": mjml_email_service.smtp_server,
            "smtp_port": mjml_email_service.smtp_port,
            "sender_email": mjml_email_service.sender_email if mjml_email_service.enabled else None,
            "sender_name": mjml_email_service.sender_name
        }
    except Exception as e:
        logger.error(f"Error getting email service status: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get email service status"
        )

# Interactive Deep Explanation Endpoints

class DeepExplanationRequest(BaseModel):
    detail_text: str
    context: Optional[str] = None
    explanation_level: Optional[str] = "comprehensive"  # basic, intermediate, advanced, comprehensive, expert
    focus_area: Optional[str] = None  # theoretical, practical, historical, comparative

@app.post("/explain/deep")
async def get_deep_explanation(request: Request, explanation_request: DeepExplanationRequest, current_user: dict = Depends(require_auth)):
    """Get deep, interactive explanation for any detail from educational content"""
    try:
        from utils.groq_client import sync_chat_completion
        
        # Construct comprehensive prompt for deep explanation
        context_info = f"\n\nContext: {explanation_request.context}" if explanation_request.context else ""
        focus_info = f"\n\nFocus on: {explanation_request.focus_area}" if explanation_request.focus_area else ""
        
        prompt = f"""You are an expert educational assistant providing ultra-comprehensive explanations. A student/researcher has clicked on a specific detail from educational content and wants a deeper explanation.

DETAIL TO EXPLAIN: "{explanation_request.detail_text}"
EXPLANATION LEVEL: {explanation_request.explanation_level}{context_info}{focus_info}

Please provide an extremely detailed, multi-layered explanation that includes:

1. **Core Explanation**: What this detail means in simple terms
2. **Technical Analysis**: The technical/academic understanding
3. **Why It Matters**: Why this detail is significant
4. **Sub-Explanations**: Break down into component parts with examples
5. **Real-World Applications**: How this applies practically
6. **Expert Insights**: What experts in the field would add
7. **Common Misconceptions**: What people often get wrong
8. **Related Concepts**: How this connects to other ideas
9. **Research Context**: Current research and debates
10. **Interactive Elements**: Questions for further exploration

Format as detailed JSON with the following structure:
{{
  "main_explanation": "Comprehensive explanation of the detail",
  "explanation_levels": {{
    "basic": "Simple explanation for beginners",
    "intermediate": "More detailed explanation",
    "advanced": "Complex explanation with nuances",
    "expert": "Expert-level analysis"
  }},
  "sub_explanations": [
    {{
      "aspect": "specific aspect name",
      "explanation": "detailed explanation of this aspect",
      "examples": ["example 1", "example 2"],
      "why_important": "why this aspect matters"
    }}
  ],
  "practical_applications": [
    {{
      "application": "real-world application",
      "description": "how it's used in practice",
      "examples": ["practical example 1", "practical example 2"]
    }}
  ],
  "expert_insights": [
    {{
      "insight": "expert perspective",
      "explanation": "detailed expert analysis",
      "source_context": "where this insight comes from"
    }}
  ],
  "common_misconceptions": [
    {{
      "misconception": "what people often get wrong",
      "why_wrong": "why this misconception exists",
      "correct_understanding": "the accurate understanding"
    }}
  ],
  "related_concepts": [
    {{
      "concept": "related concept name",
      "relationship": "how it relates to the main detail",
      "explanation": "detailed explanation of the connection"
    }}
  ],
  "research_context": {{
    "current_research": "what researchers are currently studying",
    "debates": "current debates in the field",
    "future_directions": "where research is heading",
    "key_studies": ["important research study 1", "important research study 2"]
  }},
  "interactive_questions": [
    "Question 1 for deeper exploration",
    "Question 2 for critical thinking",
    "Question 3 for practical application"
  ],
  "further_exploration": [
    {{
      "topic": "suggested topic for further study",
      "why_relevant": "why this topic would be valuable to explore",
      "resources": ["resource 1", "resource 2"]
    }}
  ]
}}

Provide the most comprehensive, research-grade explanation possible. Every aspect should be thoroughly explained with examples and context."""

        try:
            # Use Groq/LLaMA for the explanation
            response = sync_chat_completion(
                model="llama-3.1-8b-instant",  # Use available model with 131k context window
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=120000  # Near the model's 131k limit for comprehensive explanations
            )
            
            if response:
                # Try to parse as JSON
                import json
                import re
                
                # Clean the response
                cleaned_response = re.sub(r'```(?:json)?\s*', '', response)
                cleaned_response = re.sub(r'```\s*$', '', cleaned_response)
                
                try:
                    parsed_explanation = json.loads(cleaned_response)
                    
                    # Add metadata
                    parsed_explanation["metadata"] = {
                        "explanation_level": explanation_request.explanation_level,
                        "focus_area": explanation_request.focus_area,
                        "generated_at": datetime.now().isoformat(),
                        "user_id": current_user.get("uid"),
                        "original_detail": explanation_request.detail_text
                    }
                    
                    logger.info(f"Deep explanation generated for user {current_user.get('uid')}")
                    return parsed_explanation
                    
                except json.JSONDecodeError:
                    # If JSON parsing fails, return structured fallback
                    logger.warning("JSON parsing failed for deep explanation, using fallback")
                    return {
                        "main_explanation": response,
                        "explanation_levels": {
                            "basic": f"Basic explanation: {response[:200]}...",
                            "expert": f"Expert analysis: {response}"
                        },
                        "metadata": {
                            "explanation_level": explanation_request.explanation_level,
                            "generated_at": datetime.now().isoformat(),
                            "user_id": current_user.get("uid"),
                            "original_detail": explanation_request.detail_text,
                            "note": "Fallback format due to JSON parsing issue"
                        }
                    }
            else:
                raise Exception("No response from AI model")
                
        except Exception as ai_error:
            logger.error(f"AI explanation failed: {ai_error}")
            # Provide comprehensive fallback explanation
            return _generate_fallback_deep_explanation(explanation_request.detail_text, explanation_request.explanation_level)
            
    except Exception as e:
        logger.error(f"Error generating deep explanation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate deep explanation: {str(e)}")

def _generate_fallback_deep_explanation(detail_text: str, level: str) -> dict:
    """Generate comprehensive fallback explanation when AI is unavailable"""
    return {
        "main_explanation": f"COMPREHENSIVE ANALYSIS: {detail_text} represents a complex concept that requires multi-layered understanding. This detail is significant because it connects to broader theoretical frameworks and practical applications in the field.",
        "explanation_levels": {
            "basic": f"Basic understanding: {detail_text} is a fundamental concept that helps us understand key principles in this area of study.",
            "intermediate": f"Intermediate analysis: {detail_text} involves understanding the relationships between concepts and their practical implications.",
            "advanced": f"Advanced perspective: {detail_text} requires sophisticated analysis of theoretical foundations and research methodologies.",
            "expert": f"Expert insight: {detail_text} represents a nuanced concept with multiple interpretations and ongoing research implications."
        },
        "sub_explanations": [
            {
                "aspect": "theoretical foundation",
                "explanation": f"The theoretical basis of '{detail_text}' involves understanding the underlying principles and academic frameworks that support this concept.",
                "examples": ["Academic research applications", "Theoretical model implementations"],
                "why_important": "Understanding the theory helps in applying the concept correctly and recognizing its limitations."
            },
            {
                "aspect": "practical applications",
                "explanation": f"In practice, '{detail_text}' is applied in various professional and academic contexts to solve real-world problems.",
                "examples": ["Industry implementations", "Professional practice scenarios"],
                "why_important": "Practical understanding enables effective application and problem-solving."
            }
        ],
        "practical_applications": [
            {
                "application": "Professional practice",
                "description": f"'{detail_text}' is commonly used in professional settings to address specific challenges and opportunities.",
                "examples": ["Workplace implementation", "Industry-specific applications"]
            }
        ],
        "expert_insights": [
            {
                "insight": "Research perspective",
                "explanation": f"Experts in the field understand '{detail_text}' as a complex concept with multiple dimensions and ongoing research implications.",
                "source_context": "Based on current academic literature and professional practice"
            }
        ],
        "common_misconceptions": [
            {
                "misconception": "Oversimplification",
                "why_wrong": f"People often oversimplify '{detail_text}' by focusing only on surface-level understanding.",
                "correct_understanding": "The concept requires understanding of multiple layers including theoretical, practical, and contextual dimensions."
            }
        ],
        "related_concepts": [
            {
                "concept": "Foundational theories",
                "relationship": f"'{detail_text}' builds upon and connects to fundamental theories in the field.",
                "explanation": "Understanding these connections helps in developing comprehensive knowledge."
            }
        ],
        "research_context": {
            "current_research": f"Researchers are currently investigating various aspects of '{detail_text}' including its applications and theoretical implications.",
            "debates": "Ongoing scholarly discussions focus on the boundaries and applications of this concept.",
            "future_directions": "Future research will likely explore new applications and theoretical developments.",
            "key_studies": ["Foundational research in the field", "Recent developments and applications"]
        },
        "interactive_questions": [
            f"How does '{detail_text}' connect to your existing knowledge?",
            f"What practical applications of '{detail_text}' can you identify?",
            f"What questions do you still have about '{detail_text}'?"
        ],
        "further_exploration": [
            {
                "topic": "Advanced theoretical frameworks",
                "why_relevant": "Understanding advanced theory provides deeper insight into the concept's foundations.",
                "resources": ["Academic textbooks", "Research journals", "Professional publications"]
            }
        ],
        "metadata": {
            "explanation_level": level,
            "generated_at": datetime.now().isoformat(),
            "original_detail": detail_text,
            "note": "Comprehensive fallback explanation"
        }
    }
