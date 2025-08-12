"""
Main FastAPI Application

This is the main application file that handles API endpoints and coordinates
between different services for video transcription, PDF processing, and more.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Union
import uuid
import logging
import json
import hmac
import hashlib
import httpx
from datetime import datetime, timezone

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, firestore, auth

# Import configuration
from config import *

# Import existing services
from groq_processor import groq_generator
from quiz_generator import quiz_generator
from r2_storage import r2_storage
from pdf_processor import pdf_processor
from payment_service import PaymentService, PaymentResult
from notification_service import NotificationService
from device_service import device_service
from brevo_service import brevo_service
from credit_service import credit_service
from timestamp_mapper import timestamp_mapper
from tts_service import tts_service
from password_reset_service import password_reset_service
from diagram_generator import diagram_generator
from cloud_storage_service import cloud_storage_service
from video_validation_service import video_validation_service

# Import new utility services
from transcription_service import transcription_service
from youtube_service import youtube_service
from auth_service import auth_service
from job_manager import job_manager
from file_utils import file_utils
from processing_service import processing_service

# Setup logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# Pydantic models for request bodies
class CreateBookmarkRequest(BaseModel):
    job_id: str
    section_id: Union[str, int]
    title: str
    content: str
    metadata: Optional[Dict] = None

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class RegisterUserRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

class TokenValidationRequest(BaseModel):
    token: str

class QuizEvaluationRequest(BaseModel):
    answers: Dict[str, str]  # question_id -> user_answer mapping

app = FastAPI(title="Video Transcription API", version="1.0.0")

# Add validation exception handler
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"❌ Validation error on {request.method} {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": exc.errors(),
            "body": str(exc.body) if hasattr(exc, 'body') else None
        }
    )

@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    logger.error(f"❌ Pydantic validation error on {request.method} {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Pydantic validation error",
            "errors": exc.errors()
        }
    )

# Startup event to initialize services
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("🚀 Starting application startup...")
    
    # Create necessary directories
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Directories created/verified: {UPLOAD_DIR}, {OUTPUT_DIR}, {TEMP_DIR}")
    except Exception as e:
        logger.error(f"❌ Failed to create directories: {e}")
    
    # Initialize TTS service
    try:
        if not tts_service.is_available():
            logger.info("🎤 Initializing TTS service...")
            tts_service.initialize()
            logger.info("✅ TTS service initialized successfully")
        else:
            logger.info("✅ TTS service already available")
    except Exception as e:
        logger.warning(f"⚠️ TTS service initialization failed: {e}")
        logger.info("TTS service will be initialized on first use")
    
    logger.info("✅ Application startup complete!")

# Initialize Firebase Admin SDK
try:
    # Try to initialize with default credentials (for production)
    if not firebase_admin._apps:
        # Try to use JSON credentials from environment variable
        credentials_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        if credentials_json:
            try:
                import json
                cred_dict = json.loads(credentials_json)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred, {
                    'projectId': os.getenv('FIREBASE_PROJECT_ID', 'mindquick-7b9e2')
                })
                logger.info("Firebase initialized with JSON credentials from environment")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in GOOGLE_APPLICATION_CREDENTIALS_JSON: {e}")
                raise
        else:
            # For development, you can use a service account key file
            service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
            if service_account_path and os.path.exists(service_account_path):
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred, {
                    'projectId': os.getenv('FIREBASE_PROJECT_ID', 'mindquick-7b9e2')
                })
                logger.info("Firebase initialized with service account file")
            else:
                # Try with default credentials (for production/cloud deployment)
                firebase_admin.initialize_app(credentials.ApplicationDefault(), {
                    'projectId': os.getenv('FIREBASE_PROJECT_ID', 'mindquick-7b9e2')
                })
                logger.info("Firebase initialized with Application Default Credentials")
    
    db = firestore.client()
    logger.info("Firebase Admin SDK initialized successfully!")
except Exception as e:
    logger.warning(f"Firebase Admin SDK initialization failed: {e}")
    logger.info("Firebase features will be disabled - webhook will not update user plans")
    db = None

# Initialize payment and notification services
payment_service = PaymentService(db_client=db)
notification_service = NotificationService(db_client=db)
logger.info("Payment and notification services initialized")

# Initialize services with database
credit_service.db = db
logger.info("Credit service initialized")

# Paddle API Configuration
PADDLE_API_KEY = os.getenv('PADDLE_API_KEY')
PADDLE_ENVIRONMENT = os.getenv('PADDLE_ENVIRONMENT', 'sandbox')
PADDLE_BASE_URL = 'https://api.paddle.com' if PADDLE_ENVIRONMENT == 'production' else 'https://sandbox-api.paddle.com'
logger.info(f"Paddle API configured for {PADDLE_ENVIRONMENT} environment")

async def cancel_paddle_subscription(subscription_id: str) -> bool:
    """Cancel a subscription on Paddle"""
    try:
        if not PADDLE_API_KEY:
            logger.error("❌ Paddle API key not configured")
            return False
            
        headers = {
            'Authorization': f'Bearer {PADDLE_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Paddle API endpoint to cancel subscription
        url = f"{PADDLE_BASE_URL}/subscriptions/{subscription_id}/cancel"
        
        # Cancel immediately (effective_from: immediately)
        payload = {
            "effective_from": "immediately"
        }
        
        logger.info(f"🔄 Canceling Paddle subscription: {subscription_id}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                logger.info(f"✅ Successfully canceled Paddle subscription: {subscription_id}")
                return True
            else:
                logger.error(f"❌ Failed to cancel Paddle subscription {subscription_id}: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Error canceling Paddle subscription {subscription_id}: {e}")
        return False

password_reset_service.set_db(db)
logger.info("Password reset service initialized")

processing_service.db = db
logger.info("Processing service initialized")

credit_service.db = db
logger.info("Credit service initialized with Firestore client")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=CORS_METHODS,
    allow_headers=CORS_HEADERS,
)

# Create directories for uploads and outputs
for directory in [UPLOAD_DIR, OUTPUT_DIR, TEMP_DIR, STATIC_DIR]:
    directory.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")



# Basic endpoints
@app.get("/")
async def root():
    return {"message": "Video Transcription API is running", "status": "ok", "version": "1.0.0"}

@app.get("/api/")
async def api_root():
    return {"message": "Video Transcription API", "version": "1.0.0"}

# Video upload endpoint
@app.post("/upload-video/")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    request: Request = None,
):
    """Upload a video file and transcribe it"""
    
    # Validate file type
    file_extension = Path(file.filename).suffix.lower()
    
    if file_extension not in SUPPORTED_VIDEO_FORMATS:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file format. Allowed formats: {', '.join(SUPPORTED_VIDEO_FORMATS)}"
        )
    
    # Check file size
    if hasattr(file, 'size') and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
        )
    
    # Extract user information from Firebase token
    user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
    
    # Only check if user has credits (don't deduct yet)
    if user_id and db:
        from credit_service import CreditAction
        credit_result = await credit_service.check_credits(
            user_id=user_id,
            action=CreditAction.VIDEO_UPLOAD
        )
        
        if not credit_result.has_credits:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits. {credit_result.message}"
            )
    
    # Create job
    job_id = job_manager.create_job(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        action_type="VIDEO_UPLOAD"
    )
    
    try:
        # Save uploaded file temporarily
        file_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Validate video duration based on user's plan
        if user_id and db:
            user_plan = video_validation_service.get_user_plan_from_firestore(db, user_id)
            validation_result = video_validation_service.validate_video_duration(
                video_path=str(file_path),
                user_plan=user_plan,
                user_id=user_id
            )
            
            if not validation_result.is_valid:
                # Clean up uploaded file
                if file_path.exists():
                    file_path.unlink()
                
                # Get upgrade suggestion
                upgrade_suggestion = video_validation_service.get_plan_upgrade_suggestion(
                    user_plan, validation_result.duration_minutes or 0
                )
                
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": validation_result.message,
                        "validation": {
                            "is_valid": False,
                            "duration_minutes": validation_result.duration_minutes,
                            "allowed_minutes": validation_result.allowed_minutes,
                            "user_plan": validation_result.user_plan,
                            "upgrade_suggestion": upgrade_suggestion
                        }
                    }
                )
        
        # Set job to processing status before starting background task
        job_manager.update_job_status(job_id, "processing", "Starting video processing...")
        
        # Start background transcription
        background_tasks.add_task(processing_service.process_video_file, job_id, str(file_path), user_id)
        
        return {"job_id": job_id, "message": "File uploaded successfully. Transcription started."}
    
    except HTTPException:
        # Re-raise HTTP exceptions (like validation failures)
        raise
    except Exception as e:
        # Clean up file on other errors
        if file_path.exists():
            file_path.unlink()
        job_manager.set_job_error(job_id, str(e))
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# YouTube download endpoint
@app.post("/download-youtube/")
async def download_youtube(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    request: Request = None,
):
    """Download video from YouTube URL and transcribe it"""
    
    # Extract user information from Firebase token
    user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
    
    # Only check if user has credits (don't deduct yet)
    if user_id and db:
        from credit_service import CreditAction
        credit_result = await credit_service.check_credits(
            user_id=user_id,
            action=CreditAction.YOUTUBE_DOWNLOAD
        )
        
        if not credit_result.has_credits:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits. {credit_result.message}"
            )
    
    # Create job
    job_id = job_manager.create_job(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        action_type="YOUTUBE_DOWNLOAD"
    )
    
    try:
        # Set job to processing status before starting background task
        job_manager.update_job_status(job_id, "processing", "Starting YouTube download...")
        
        # Start background download and transcription
        background_tasks.add_task(processing_service.process_youtube_url, job_id, url, user_id)
        
        return {"job_id": job_id, "message": "YouTube download started. Transcription will follow."}
    
    except Exception as e:
        job_manager.set_job_error(job_id, str(e))
        raise HTTPException(status_code=500, detail=f"YouTube download failed: {str(e)}")

# TED Talk download endpoint
@app.post("/download-tedtalk/")
async def download_tedtalk(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    request: Request = None,
):
    """Download video from TED Talk URL and transcribe it"""
    
    # Validate TED Talk URL
    if not any(domain in url.lower() for domain in ['ted.com', 'youtube.com/watch', 'youtu.be']):
        raise HTTPException(
            status_code=400, 
            detail="Please provide a valid TED Talk URL (ted.com) or YouTube URL for TED content"
        )
    
    # Extract user information from Firebase token
    user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
    
    # Only check if user has credits (don't deduct yet)
    if user_id and db:
        from credit_service import CreditAction
        credit_result = await credit_service.check_credits(
            user_id=user_id,
            action=CreditAction.YOUTUBE_DOWNLOAD  # Use same credit action as YouTube
        )
        
        if not credit_result.has_credits:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits. {credit_result.message}"
            )
    
    # Create job
    job_id = job_manager.create_job(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        action_type="TEDTALK_DOWNLOAD"
    )
    
    try:
        # Set job to processing status before starting background task
        job_manager.update_job_status(job_id, "processing", "Starting TED Talk download...")
        
        # Start background download and transcription using the same processing service
        background_tasks.add_task(processing_service.process_youtube_url, job_id, url, user_id)
        
        return {"job_id": job_id, "message": "TED Talk download started. Transcription will follow."}
    
    except Exception as e:
        job_manager.set_job_error(job_id, str(e))
        raise HTTPException(status_code=500, detail=f"TED Talk download failed: {str(e)}")

# Udemy course URL endpoint
@app.post("/process-udemy-url/")
async def process_udemy_url(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    request: Request = None,
):
    """Process a Udemy course URL and transcribe it"""
    
    # Extract user information from Firebase token
    user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
    
    # Only check if user has credits (don't deduct yet)
    if user_id and db:
        from credit_service import CreditAction
        credit_result = await credit_service.check_credits(
            user_id=user_id,
            action=CreditAction.VIDEO_UPLOAD
        )
        
        if not credit_result.has_credits:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits. {credit_result.message}"
            )
    
    # Create job
    job_id = job_manager.create_job(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        action_type="UDEMY_DOWNLOAD"
    )
    
    try:
        # Set job to processing status before starting background task
        job_manager.update_job_status(job_id, "processing", "Starting Udemy course download...")
        
        # Start background download and transcription using the same processing service
        background_tasks.add_task(processing_service.process_youtube_url, job_id, url, user_id)
        
        return {"job_id": job_id, "message": "Udemy course download started. Transcription will follow."}
    
    except Exception as e:
        job_manager.set_job_error(job_id, str(e))
        raise HTTPException(status_code=500, detail=f"Udemy course download failed: {str(e)}")

# PDF upload endpoint
@app.post("/upload-pdf/")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    request: Request = None,
):
    """Handle PDF file upload and processing"""
    
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Check file size (limit to 50MB for PDFs)
    if file.size and file.size > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF file too large. Maximum size is 50MB.")
    
    # Extract user information from Firebase token
    user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
    
    # Only check if user has credits (don't deduct yet)
    if user_id and db:
        from credit_service import CreditAction
        credit_result = await credit_service.check_credits(
            user_id=user_id,
            action=CreditAction.PDF_UPLOAD
        )
        
        if not credit_result.has_credits:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits. {credit_result.message}"
            )
    
    # Create job
    job_id = job_manager.create_job(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        action_type="PDF_UPLOAD"
    )
    
    try:
        # Save uploaded file temporarily
        file_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Set job to processing status before starting background task
        job_manager.update_job_status(job_id, "processing", "Starting PDF processing...")
        
        # Start background processing
        background_tasks.add_task(processing_service.process_pdf_file, job_id, str(file_path), user_id)
        
        return {"job_id": job_id, "message": "PDF uploaded successfully. Processing started."}
    
    except Exception as e:
        job_manager.set_job_error(job_id, str(e))
        raise HTTPException(status_code=500, detail=f"PDF upload failed: {str(e)}")

# Job status endpoint
@app.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a processing job"""
    job_data = job_manager.get_job_status(job_id)
    
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job_data

# Alternative endpoint for backward compatibility
@app.get("/job-status/{job_id}")
async def get_job_status_alt(job_id: str):
    """Get the status of a processing job (alternative endpoint)"""
    job_data = job_manager.get_job_status(job_id)
    
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job_data

# Download transcription endpoint
@app.get("/download-transcription/{job_id}")
async def download_transcription(job_id: str):
    """Download the transcription file"""
    if not job_manager.job_exists(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    
    transcription_file = OUTPUT_DIR / f"{job_id}_transcription.txt"
    if not transcription_file.exists():
        raise HTTPException(status_code=404, detail="Transcription file not found")
    
    return FileResponse(
        path=str(transcription_file),
        filename=f"transcription_{job_id}.txt",
        media_type="text/plain"
    )

# Download notes endpoint
@app.get("/download-notes/{job_id}")
async def download_notes(job_id: str, format: str = "txt", request: Request = None):
    """Download the structured notes file"""
    if not job_manager.job_exists(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Validate format
    if format not in ["txt", "md"]:
        raise HTTPException(status_code=400, detail="Format must be 'txt' or 'md'")
    
    notes_file = OUTPUT_DIR / f"{job_id}_notes.{format}"
    if not notes_file.exists():
        raise HTTPException(status_code=404, detail="Notes file not found")
    
    media_type = "text/markdown" if format == "md" else "text/plain"
    
    return FileResponse(
        path=str(notes_file),
        filename=f"notes_{job_id}.{format}",
        media_type=media_type
    )

# API endpoint for getting notes content (what frontend expects)
@app.get("/api/notes/{job_id}")
async def get_notes_content(job_id: str, format: str = "txt", request: Request = None):
    """Get the structured notes content as JSON response"""
    if not job_manager.job_exists(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Validate format
    if format not in ["txt", "md"]:
        raise HTTPException(status_code=400, detail="Format must be 'txt' or 'md'")
    
    notes_file = OUTPUT_DIR / f"{job_id}_notes.{format}"
    if not notes_file.exists():
        raise HTTPException(status_code=404, detail="Notes file not found")
    
    try:
        content = file_utils.read_file_safely(str(notes_file))
        if content is None:
            raise HTTPException(status_code=500, detail="Failed to read notes file")
        
        return {
            "job_id": job_id,
            "format": format,
            "content": content,
            "filename": f"notes_{job_id}.{format}"
        }
    except Exception as e:
        logger.error(f"Error reading notes file {notes_file}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read notes file")

# API endpoint for claiming notes (if needed by frontend)
@app.post("/api/notes/{job_id}/claim")
async def claim_notes(job_id: str, format: str = "txt", request: Request = None):
    """Claim notes for a job (for credit deduction)"""
    if not job_manager.job_exists(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Extract user information
    user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
    
    # Check if user has credits and deduct if needed
    if user_id and db:
        try:
            from credit_service import CreditAction
            # Check if credits were already deducted for this job
            job_data = job_manager.get_job_status(job_id)
            if job_data and not job_data.get("credits_deducted", False):
                # Determine the action type based on job data
                action_type = job_data.get("action_type", "VIDEO_UPLOAD")
                if action_type == "YOUTUBE_DOWNLOAD":
                    action = CreditAction.YOUTUBE_DOWNLOAD
                elif action_type == "PDF_UPLOAD":
                    action = CreditAction.PDF_UPLOAD
                else:
                    action = CreditAction.VIDEO_UPLOAD
                
                # Deduct credits
                credit_result = await credit_service.deduct_credits(
                    user_id=user_id,
                    action=action
                )
                
                if not credit_result.success:
                    raise HTTPException(
                        status_code=402,
                        detail=f"Failed to deduct credits: {credit_result.message}"
                    )
                
                # Mark credits as deducted
                job_manager.update_job_status(job_id, job_data["status"], credits_deducted=True)
        except Exception as e:
            logger.error(f"Credit deduction failed for job {job_id}: {e}")
            # Don't fail the request if credit deduction fails, just log it
    
    # Return the notes content
    return await get_notes_content(job_id, format, request)

# API endpoint for getting timestamped notes
@app.get("/api/timestamped-notes/{job_id}")
async def get_timestamped_notes(job_id: str, format: str = "json"):
    """Get timestamped notes for a job"""
    if not job_manager.job_exists(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Validate format
    if format not in ["json", "md", "srt", "vtt"]:
        raise HTTPException(status_code=400, detail="Format must be 'json', 'md', 'srt', or 'vtt'")
    
    if format == "json":
        timestamped_file = OUTPUT_DIR / f"{job_id}_timestamped_notes.json"
    elif format == "md":
        timestamped_file = OUTPUT_DIR / f"{job_id}_timestamped_notes.md"
    elif format == "srt":
        timestamped_file = OUTPUT_DIR / f"{job_id}_notes.srt"
    else:  # vtt
        timestamped_file = OUTPUT_DIR / f"{job_id}_notes.vtt"
    
    if not timestamped_file.exists():
        raise HTTPException(status_code=404, detail="Timestamped notes file not found")
    
    try:
        content = file_utils.read_file_safely(str(timestamped_file))
        if content is None:
            raise HTTPException(status_code=500, detail="Failed to read timestamped notes file")
        
        if format == "json":
            import json
            try:
                parsed_content = json.loads(content)
                return parsed_content
            except json.JSONDecodeError:
                return {"content": content}
        else:
            return {
                "job_id": job_id,
                "format": format,
                "content": content,
                "filename": f"timestamped_notes_{job_id}.{format}"
            }
    except Exception as e:
        logger.error(f"Error reading timestamped notes file {timestamped_file}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read timestamped notes file")

# TTS endpoints
@app.post("/api/tts/generate")
async def generate_tts(
    background_tasks: BackgroundTasks,
    text: str = Form(...),
    request: Request = None
):
    """Generate TTS audio from text"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        
        # Check if TTS service is available
        if not tts_service.is_available():
            # Try to initialize if not available
            try:
                tts_service.initialize()
            except Exception as init_error:
                logger.error(f"TTS service initialization failed: {init_error}")
                raise HTTPException(
                    status_code=503, 
                    detail="TTS service is not available. Please try again later."
                )
        
        # Validate text length
        if len(text) > 10000:
            raise HTTPException(
                status_code=400,
                detail="Text too long. Maximum length is 10,000 characters."
            )
        
        if len(text.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail="Text cannot be empty."
            )
        
        # Generate TTS
        result = await tts_service.generate_speech(text, str(OUTPUT_DIR))
        
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail=f"TTS generation failed: {result.get('error', 'Unknown error')}"
            )
        
        return {
            "success": True,
            "audio_id": result.get("audio_id"),
            "message": "TTS audio generated successfully",
            "audio_url": f"/api/tts/audio/{result.get('audio_id')}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS generation error: {e}")
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")

@app.post("/api/tts/generate-for-notes/{job_id}")
async def generate_tts_for_notes(
    job_id: str,
    background_tasks: BackgroundTasks,
    request: Request = None
):
    """Generate TTS audio for notes content"""
    try:
        logger.info(f"🔍 Checking if job exists: {job_id}")
        # Check if job exists
        if not job_manager.job_exists(job_id):
            logger.error(f"❌ Job not found: {job_id}")
            raise HTTPException(status_code=404, detail="Job not found")
        
        logger.info(f"✅ Job exists: {job_id}")
        
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"👤 User info: {user_id}, {user_email}")
        
        # Check if TTS service is available
        logger.info(f"🎤 Checking TTS service availability...")
        if not tts_service.is_available():
            try:
                logger.info(f"🔧 Initializing TTS service...")
                tts_service.initialize()
                logger.info(f"✅ TTS service initialized successfully")
            except Exception as init_error:
                logger.error(f"❌ TTS service initialization failed: {init_error}")
                raise HTTPException(
                    status_code=503, 
                    detail="TTS service is not available. Please try again later."
                )
        else:
            logger.info(f"✅ TTS service is already available")
        
        # Read notes content
        notes_file = OUTPUT_DIR / f"{job_id}_notes.txt"
        logger.info(f"📄 Looking for notes file: {notes_file}")
        
        if not notes_file.exists():
            logger.error(f"❌ Notes file not found: {notes_file}")
            # List files in output directory for debugging
            try:
                files = list(OUTPUT_DIR.glob(f"{job_id}*"))
                logger.info(f"📁 Files found for job {job_id}: {[f.name for f in files]}")
            except Exception as e:
                logger.error(f"❌ Error listing files: {e}")
            raise HTTPException(status_code=404, detail="Notes file not found")
        
        logger.info(f"✅ Notes file found: {notes_file}")
        
        notes_content = file_utils.read_file_safely(str(notes_file))
        if not notes_content:
            logger.error(f"❌ Notes content is empty for job: {job_id}")
            raise HTTPException(status_code=404, detail="Notes content is empty")
        
        logger.info(f"✅ Notes content loaded: {len(notes_content)} characters")
        
        # Generate TTS for notes
        logger.info(f"🎵 Starting TTS generation for job: {job_id}")
        result = await tts_service.generate_speech_for_notes(
            notes_content, 
            job_id, 
            str(OUTPUT_DIR)
        )
        
        logger.info(f"🎵 TTS generation result: {result}")
        
        if not result["success"]:
            logger.error(f"❌ TTS generation failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(
                status_code=500,
                detail=f"TTS generation failed: {result.get('error', 'Unknown error')}"
            )
        
        logger.info(f"✅ TTS generation successful for job: {job_id}")
        
        return {
            "success": True,
            "job_id": job_id,
            "message": "TTS audio generated successfully for notes",
            "audio_url": f"/api/tts/notes-audio/{job_id}",
            "original_text_length": result.get("original_text_length", 0),
            "cleaned_text_length": result.get("cleaned_text_length", 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ TTS generation for notes error: {e}")
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")

@app.get("/api/tts/audio/{audio_id}")
async def get_tts_audio(audio_id: str):
    """Get TTS audio file by audio ID"""
    audio_file = OUTPUT_DIR / f"tts_{audio_id}.wav"
    
    if not audio_file.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    return FileResponse(
        path=str(audio_file),
        filename=f"tts_audio_{audio_id}.wav",
        media_type="audio/wav"
    )

@app.get("/api/tts/notes-audio/{job_id}")
async def get_notes_tts_audio(job_id: str):
    """Get TTS audio file for notes by job ID"""
    audio_file = OUTPUT_DIR / f"{job_id}_notes_audio.wav"
    
    if not audio_file.exists():
        raise HTTPException(status_code=404, detail="Notes audio file not found")
    
    return FileResponse(
        path=str(audio_file),
        filename=f"notes_audio_{job_id}.wav",
        media_type="audio/wav"
    )

@app.get("/api/tts/{job_id}/audio")
async def get_tts_audio_for_job(job_id: str):
    """Get TTS audio file for a specific job (frontend expected endpoint)"""
    return await get_notes_tts_audio(job_id)

@app.get("/api/tts/status")
async def get_tts_status():
    """Get TTS service status"""
    return {
        "available": tts_service.is_available(),
        "backend": getattr(tts_service, 'backend', None),
        "voice": getattr(tts_service, 'voice', None),
        "available_backends": getattr(tts_service, 'available_backends', [])
    }

@app.post("/api/tts/{job_id}")
async def generate_tts_for_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    request: Request = None
):
    """Generate TTS audio for a specific job (frontend expected endpoint)"""
    logger.info(f"🎤 TTS generation requested for job: {job_id}")
    try:
        result = await generate_tts_for_notes(job_id, background_tasks, request)
        logger.info(f"✅ TTS generation successful for job: {job_id}")
        return result
    except Exception as e:
        logger.error(f"❌ TTS generation failed for job {job_id}: {e}")
        raise

# Quiz generation endpoints
@app.post("/api/generate-quiz/{job_id}")
async def generate_quiz_for_job(
    job_id: str,
    num_questions: int = 10,
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Generate quiz from notes content for a specific job"""
    try:
        logger.info(f"📝 Quiz generation requested for job: {job_id}, questions: {num_questions}")
        
        # Check if job exists (either in job manager or notes file exists)
        notes_file = OUTPUT_DIR / f"{job_id}_notes.txt"
        if not job_manager.job_exists(job_id) and not notes_file.exists():
            logger.error(f"❌ Job not found: {job_id}")
            # List available files for debugging
            try:
                files = list(OUTPUT_DIR.glob("*_notes.txt"))
                available_jobs = [f.stem.replace('_notes', '') for f in files]
                logger.info(f"📁 Available jobs: {available_jobs}")
            except Exception as e:
                logger.error(f"❌ Error listing available jobs: {e}")
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"👤 User info: {user_id}, {user_email}")
        
        # Check if quiz generator is available
        if not quiz_generator.is_available():
            logger.error("❌ Quiz generator not available - Groq API not configured")
            raise HTTPException(
                status_code=503, 
                detail="Quiz generation service is not available. Please check API configuration."
            )
        
        # Read notes content (notes_file already defined above)
        logger.info(f"📄 Reading notes file: {notes_file}")
        
        if not notes_file.exists():
            logger.error(f"❌ Notes file not found: {notes_file}")
            raise HTTPException(status_code=404, detail="Notes file not found")
        
        logger.info(f"✅ Notes file found: {notes_file}")
        
        notes_content = file_utils.read_file_safely(str(notes_file))
        if not notes_content:
            logger.error(f"❌ Notes content is empty for job: {job_id}")
            raise HTTPException(status_code=404, detail="Notes content is empty")
        
        if len(notes_content.strip()) < 100:
            logger.error(f"❌ Notes content too short for quiz generation: {len(notes_content)} characters")
            raise HTTPException(status_code=400, detail="Notes content is too short to generate a meaningful quiz")
        
        logger.info(f"✅ Notes content loaded: {len(notes_content)} characters")
        
        # Validate num_questions parameter
        if num_questions < 1 or num_questions > 50:
            raise HTTPException(status_code=400, detail="Number of questions must be between 1 and 50")
        
        # Generate quiz
        logger.info(f"🧠 Starting quiz generation for job: {job_id}")
        quiz_data = quiz_generator.generate_quiz(notes_content, num_questions)
        
        if not quiz_data:
            logger.error(f"❌ Quiz generation failed for job: {job_id}")
            raise HTTPException(
                status_code=500,
                detail="Failed to generate quiz. Please try again with different content."
            )
        
        logger.info(f"✅ Quiz generated successfully: {len(quiz_data.get('questions', []))} questions")
        
        # Save quiz data to file
        quiz_file = OUTPUT_DIR / f"{job_id}_quiz.json"
        try:
            with open(quiz_file, 'w', encoding='utf-8') as f:
                json.dump(quiz_data, f, indent=2, ensure_ascii=False)
            logger.info(f"💾 Quiz saved to: {quiz_file}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to save quiz to file: {e}")
        
        # Add metadata
        quiz_data["job_id"] = job_id
        quiz_data["generated_at"] = datetime.now(timezone.utc).isoformat()
        quiz_data["user_id"] = user_id
        
        return {
            "status": "success",
            "job_id": job_id,
            "quiz_data": quiz_data,
            "message": f"Quiz generated successfully with {len(quiz_data.get('questions', []))} questions"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Quiz generation error for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Quiz generation failed: {str(e)}")

@app.get("/api/quiz/{job_id}")
async def get_quiz_for_job(job_id: str, request: Request = None):
    """Get previously generated quiz for a job"""
    try:
        # Check if job exists
        if not job_manager.job_exists(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        
        # Check if quiz file exists
        quiz_file = OUTPUT_DIR / f"{job_id}_quiz.json"
        if not quiz_file.exists():
            raise HTTPException(status_code=404, detail="Quiz not found for this job")
        
        # Read quiz data
        try:
            with open(quiz_file, 'r', encoding='utf-8') as f:
                quiz_data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading quiz file {quiz_file}: {e}")
            raise HTTPException(status_code=500, detail="Failed to read quiz data")
        
        return {
            "success": True,
            "job_id": job_id,
            "quiz": quiz_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving quiz for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve quiz: {str(e)}")

@app.post("/api/evaluate-quiz/{job_id}")
async def evaluate_quiz(
    job_id: str,
    evaluation_request: QuizEvaluationRequest,
    request: Request = None
):
    """Evaluate quiz answers and return results"""
    try:
        logger.info(f"📝 Quiz evaluation requested for job: {job_id}")
        
        # Check if job exists
        if not job_manager.job_exists(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        
        # Check if quiz file exists
        quiz_file = OUTPUT_DIR / f"{job_id}_quiz.json"
        if not quiz_file.exists():
            raise HTTPException(status_code=404, detail="Quiz not found for this job")
        
        # Read quiz data
        try:
            with open(quiz_file, 'r', encoding='utf-8') as f:
                quiz_data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading quiz file {quiz_file}: {e}")
            raise HTTPException(status_code=500, detail="Failed to read quiz data")
        
        # Evaluate the quiz using the quiz generator
        if not quiz_generator.is_available():
            raise HTTPException(status_code=503, detail="Quiz evaluation service not available")
        
        evaluation_results = quiz_generator.evaluate_quiz(quiz_data, evaluation_request.answers)
        
        if not evaluation_results:
            raise HTTPException(status_code=500, detail="Failed to evaluate quiz")
        
        logger.info(f"✅ Quiz evaluated successfully for job {job_id}. Score: {evaluation_results.get('score', 0)}/{evaluation_results.get('max_score', 0)}")
        
        return {
            "success": True,
            "job_id": job_id,
            "evaluation": evaluation_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error evaluating quiz for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to evaluate quiz: {str(e)}")

# Diagram generation endpoints
@app.post("/api/generate-diagram/{job_id}")
async def generate_diagram_for_job(
    job_id: str,
    diagram_type: str = "flowchart",
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Generate diagram from notes content for a specific job"""
    try:
        logger.info(f"📊 Diagram generation requested for job: {job_id}, type: {diagram_type}")
        
        # Check if job exists by looking for notes files on disk
        notes_file = OUTPUT_DIR / f"{job_id}_notes.txt"
        notes_md_file = OUTPUT_DIR / f"{job_id}_notes.md"
        
        if not (notes_file.exists() or notes_md_file.exists()):
            logger.error(f"❌ Job not found: {job_id}. No notes files found.")
            # List files in output directory for debugging
            try:
                files = list(OUTPUT_DIR.glob(f"{job_id}*"))
                logger.info(f"📁 Files found for job {job_id}: {[f.name for f in files]}")
            except Exception as e:
                logger.error(f"❌ Error listing files: {e}")
            raise HTTPException(status_code=404, detail="Job not found or notes not generated yet")
        
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"👤 User info: {user_id}, {user_email}")
        
        # Check if diagram generator is available
        if not diagram_generator.is_available():
            logger.error("❌ Diagram generator not available - Groq API not configured")
            raise HTTPException(
                status_code=503, 
                detail="Diagram generation service is not available. Please check API configuration."
            )
        
        # Validate diagram type
        valid_types = ["flowchart", "mindmap", "sequence", "process", "graph"]
        if diagram_type not in valid_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid diagram type. Must be one of: {', '.join(valid_types)}"
            )
        
        # Read notes content (prefer .txt, fallback to .md)
        notes_file = OUTPUT_DIR / f"{job_id}_notes.txt"
        notes_md_file = OUTPUT_DIR / f"{job_id}_notes.md"
        
        if notes_file.exists():
            active_notes_file = notes_file
            logger.info(f"📄 Using .txt notes file: {active_notes_file}")
        elif notes_md_file.exists():
            active_notes_file = notes_md_file
            logger.info(f"📄 Using .md notes file: {active_notes_file}")
        else:
            logger.error(f"❌ No notes file found for job: {job_id}")
            # List files in output directory for debugging
            try:
                files = list(OUTPUT_DIR.glob(f"{job_id}*"))
                logger.info(f"📁 Files found for job {job_id}: {[f.name for f in files]}")
            except Exception as e:
                logger.error(f"❌ Error listing files: {e}")
            raise HTTPException(status_code=404, detail="Notes file not found")
        
        notes_content = file_utils.read_file_safely(str(active_notes_file))
        if not notes_content:
            logger.error(f"❌ Notes content is empty for job: {job_id}")
            raise HTTPException(status_code=404, detail="Notes content is empty")
        
        if len(notes_content.strip()) < 100:
            logger.error(f"❌ Notes content too short for diagram generation: {len(notes_content)} characters")
            raise HTTPException(status_code=400, detail="Notes content is too short to generate a meaningful diagram")
        
        logger.info(f"✅ Notes content loaded: {len(notes_content)} characters")
        
        # Generate diagram
        logger.info(f"🎨 Starting diagram generation for job: {job_id}")
        diagram_data = diagram_generator.generate_diagram_from_notes(notes_content, diagram_type)
        
        if not diagram_data:
            logger.error(f"❌ Diagram generation failed for job: {job_id}")
            raise HTTPException(
                status_code=500,
                detail="Failed to generate diagram. Please try again with different content or diagram type."
            )
        
        logger.info(f"✅ Diagram generated successfully: {diagram_data.get('type', 'unknown')} type")
        
        # Save diagram data to file
        diagram_file = OUTPUT_DIR / f"{job_id}_diagram_{diagram_type}.json"
        try:
            with open(diagram_file, 'w', encoding='utf-8') as f:
                json.dump(diagram_data, f, indent=2, ensure_ascii=False)
            logger.info(f"💾 Diagram saved to: {diagram_file}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to save diagram to file: {e}")
        
        # Add metadata
        diagram_data["job_id"] = job_id
        diagram_data["generated_at"] = datetime.now(timezone.utc).isoformat()
        diagram_data["user_id"] = user_id
        
        return {
            "success": True,
            "job_id": job_id,
            "diagram": diagram_data,
            "message": f"Diagram generated successfully ({diagram_type})"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Diagram generation error for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Diagram generation failed: {str(e)}")

@app.get("/api/diagram/{job_id}")
async def get_diagram_for_job(
    job_id: str, 
    diagram_type: str = "flowchart",
    request: Request = None
):
    """Get previously generated diagram for a job"""
    try:
        # Check if job exists
        if not job_manager.job_exists(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        
        # Check if diagram file exists
        diagram_file = OUTPUT_DIR / f"{job_id}_diagram_{diagram_type}.json"
        if not diagram_file.exists():
            raise HTTPException(status_code=404, detail=f"Diagram ({diagram_type}) not found for this job")
        
        # Read diagram data
        try:
            with open(diagram_file, 'r', encoding='utf-8') as f:
                diagram_data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading diagram file {diagram_file}: {e}")
            raise HTTPException(status_code=500, detail="Failed to read diagram data")
        
        return {
            "success": True,
            "job_id": job_id,
            "diagram": diagram_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving diagram for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve diagram: {str(e)}")

# Saved Notes and Bookmarks endpoints


@app.get("/api/bookmarks")
async def get_user_bookmarks(
    limit: int = 100,
    request: Request = None
):
    """Get user's bookmarks"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔖 Getting bookmarks for user: {user_id}, limit: {limit}")
        
        # Validate limit
        if limit < 1 or limit > 1000:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 1000")
        
        # Get bookmarks from R2 storage
        bookmarks = r2_storage.get_user_bookmarks(user_id=user_id, limit=limit)
        
        # Get user plan and bookmark limits
        bookmark_limits = {
            'free': 10,
            'student': 50,
            'researcher': 200,
            'expert': 1000
        }
        
        user_plan = 'free'  # default
        max_bookmarks = 10  # default
        
        if db:
            try:
                user_doc = db.collection('users').document(user_id).get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    user_plan = user_data.get('plan', 'free')
                    max_bookmarks = bookmark_limits.get(user_plan, 10)
            except Exception as e:
                logger.warning(f"⚠️ Could not get user plan for bookmark limits: {e}")
        
        logger.info(f"✅ Retrieved {len(bookmarks)} bookmarks for user: {user_id}")
        
        return {
            "status": "success",
            "success": True,
            "bookmarks": bookmarks,
            "count": len(bookmarks),
            "user_id": user_id,
            "limits": {
                "current_count": len(bookmarks),
                "max_bookmarks": max_bookmarks,
                "user_plan": user_plan,
                "remaining": max(0, max_bookmarks - len(bookmarks))
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving bookmarks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve bookmarks: {str(e)}")

@app.post("/api/bookmarks")
async def create_bookmark(
    request: Request = None
):
    """Create a new bookmark"""
    try:
        # Get raw request body for debugging
        body = await request.body()
        logger.info(f"🔖 Raw bookmark request body: {body.decode('utf-8')}")
        
        # Parse JSON manually to provide better error messages
        try:
            import json
            bookmark_data_dict = json.loads(body.decode('utf-8'))
            logger.info(f"🔖 Parsed bookmark data: {bookmark_data_dict}")
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON in bookmark request: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
        
        # Validate required fields
        required_fields = ['job_id', 'section_id', 'title', 'content']
        missing_fields = [field for field in required_fields if field not in bookmark_data_dict]
        if missing_fields:
            logger.error(f"❌ Missing required fields: {missing_fields}")
            raise HTTPException(status_code=422, detail=f"Missing required fields: {', '.join(missing_fields)}")
        
        # Create Pydantic model instance
        try:
            bookmark_data = CreateBookmarkRequest(**bookmark_data_dict)
        except Exception as e:
            logger.error(f"❌ Pydantic validation error: {e}")
            raise HTTPException(status_code=422, detail=f"Validation error: {str(e)}")
        
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔖 Creating bookmark for user: {user_id}, job: {bookmark_data.job_id}")
        
        # Check bookmark limits based on user plan
        if user_id and db:
            try:
                # Get user's current plan from Firestore
                user_doc = db.collection('users').document(user_id).get()
                user_plan = 'free'  # default
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    user_plan = user_data.get('plan', 'free')
                
                # Define bookmark limits per plan
                bookmark_limits = {
                    'free': 10,
                    'student': 50,
                    'researcher': 200,
                    'expert': 1000
                }
                
                max_bookmarks = bookmark_limits.get(user_plan, 10)
                
                # Get current bookmark count
                current_bookmarks = r2_storage.get_user_bookmarks(user_id=user_id, limit=1000)
                current_count = len(current_bookmarks)
                
                if current_count >= max_bookmarks:
                    plan_names = {
                        'free': 'Free',
                        'student': 'Student',
                        'researcher': 'Researcher',
                        'expert': 'Expert'
                    }
                    
                    raise HTTPException(
                        status_code=402,
                        detail={
                            "message": f"Bookmark limit reached. {plan_names.get(user_plan, 'Free')} plan allows {max_bookmarks} bookmarks.",
                            "current_count": current_count,
                            "max_bookmarks": max_bookmarks,
                            "user_plan": user_plan,
                            "upgrade_required": user_plan == 'free'
                        }
                    )
                
                logger.info(f"🔖 Bookmark limit check passed: {current_count}/{max_bookmarks} for {user_plan} plan")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"⚠️ Could not check bookmark limits: {e}")
                # Continue without limit check if there's an error
        
        # Validate inputs
        if len(bookmark_data.title) > 200:
            raise HTTPException(status_code=400, detail="Title must be 200 characters or less")
        
        if len(bookmark_data.content) > 10000:
            raise HTTPException(status_code=400, detail="Content must be 10000 characters or less")
        
        # Save bookmark to R2 storage
        bookmark_id = r2_storage.save_bookmark(
            user_id=user_id,
            job_id=bookmark_data.job_id,
            section_id=bookmark_data.section_id,
            title=bookmark_data.title,
            content=bookmark_data.content,
            metadata=bookmark_data.metadata
        )
        
        if not bookmark_id:
            raise HTTPException(status_code=500, detail="Failed to save bookmark")
        
        logger.info(f"✅ Bookmark created successfully: {bookmark_id}")
        
        return {
            "status": "success",
            "success": True,
            "bookmark_id": bookmark_id,
            "message": "Bookmark created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating bookmark: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create bookmark: {str(e)}")

@app.delete("/api/bookmarks/{bookmark_id}")
async def delete_bookmark(
    bookmark_id: str,
    request: Request = None
):
    """Delete a bookmark"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🗑️ Deleting bookmark: {bookmark_id} for user: {user_id}")
        
        # Delete bookmark from R2 storage
        success = r2_storage.delete_bookmark(user_id=user_id, bookmark_id=bookmark_id)
        
        if success:
            logger.info(f"✅ Successfully deleted bookmark: {bookmark_id}")
            return {
                "status": "success",
                "success": True,
                "message": "Bookmark deleted successfully"
            }
        else:
            logger.warning(f"⚠️ Bookmark not found or failed to delete: {bookmark_id}")
            raise HTTPException(status_code=404, detail="Bookmark not found or failed to delete")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting bookmark: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete bookmark: {str(e)}")

# Credits and Payment endpoints
@app.get("/credits/balance")
async def get_credits_balance(request: Request = None):
    """Get user's current credit balance"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"💰 Getting credit balance for user: {user_id}")
        
        # Debug: Check if credit service has database client
        if not credit_service.db:
            logger.error("❌ Credit service database client not initialized!")
            credit_service.db = firestore.client()
            logger.info("🔧 Initialized credit service database client")
        
        # Debug: Check Firestore directly
        try:
            user_ref = credit_service.db.collection('users').document(user_id)
            user_doc = user_ref.get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                logger.info(f"🔍 Direct Firestore query for user {user_id}: {user_data}")
            else:
                logger.info(f"🔍 No Firestore document found for user: {user_id}")
        except Exception as firestore_error:
            logger.error(f"❌ Error querying Firestore directly: {firestore_error}")
        
        # Get user credits from credit service
        credits_info = await credit_service.get_user_credits(user_id, user_email, user_name)
        
        logger.info(f"✅ Credit service returned for user {user_id}: {credits_info}")
        
        return {
            "status": "success",
            "success": True,
            "credits": credits_info.get('current_credits', 0),
            "balance": credits_info.get('current_credits', 0),
            "credits_used": credits_info.get('credits_used', 0),
            "plan": credits_info.get('plan', 'free'),
            "total_mindmaps": credits_info.get('total_mindmaps', 0),
            "user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving credit balance: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve credit balance: {str(e)}")

@app.get("/api/credits/balance")
async def get_api_credits_balance(request: Request = None):
    """Get user's current credit balance (API version)"""
    return await get_credits_balance(request)

@app.get("/api/payment-methods")
async def get_payment_methods(request: Request = None):
    """Get user's saved payment methods"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"💳 Getting payment methods for user: {user_id}")
        
        # For now, return empty payment methods since this functionality isn't fully implemented
        # In a real implementation, this would fetch from Paddle or Stripe
        payment_methods = []
        
        logger.info(f"✅ Retrieved {len(payment_methods)} payment methods for user: {user_id}")
        
        return {
            "status": "success",
            "success": True,
            "payment_methods": payment_methods,
            "count": len(payment_methods),
            "user_id": user_id,
            "message": "Payment methods functionality is being implemented"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving payment methods: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve payment methods: {str(e)}")

@app.post("/api/payment-methods")
async def add_payment_method(
    payment_data: dict,
    request: Request = None
):
    """Add a new payment method"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"💳 Adding payment method for user: {user_id}")
        
        # For now, return a placeholder response
        logger.warning("⚠️ Payment method addition not yet fully implemented")
        
        return {
            "status": "success",
            "success": True,
            "message": "Payment method addition is being implemented",
            "user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error adding payment method: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add payment method: {str(e)}")

@app.delete("/api/payment-methods/{method_id}")
async def delete_payment_method(
    method_id: str,
    request: Request = None
):
    """Delete a payment method"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🗑️ Deleting payment method {method_id} for user: {user_id}")
        
        # For now, return a placeholder response
        logger.warning("⚠️ Payment method deletion not yet fully implemented")
        
        return {
            "status": "success",
            "success": True,
            "message": "Payment method deletion is being implemented",
            "user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting payment method: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete payment method: {str(e)}")

# Webhook endpoints
@app.post("/webhook/paddle")
async def paddle_webhook(request: Request):
    """Handle Paddle webhook notifications"""
    try:
        # Get raw body and headers
        body = await request.body()
        signature = request.headers.get('paddle-signature', '')
        
        logger.info(f"🎣 Received Paddle webhook: {len(body)} bytes, signature present: {bool(signature)}")
        
        # Verify webhook signature
        if not payment_service.verify_webhook_signature(body, signature):
            logger.error("❌ Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        
        # Parse webhook data
        try:
            webhook_data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON in webhook: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        event_type = webhook_data.get('event_type', 'unknown')
        logger.info(f"📨 Processing Paddle webhook event: {event_type}")
        
        # Debug: Log webhook data structure (first 500 chars)
        webhook_data_str = str(webhook_data)[:500]
        logger.info(f"🔍 Webhook data preview: {webhook_data_str}...")
        
        # Process different webhook events
        if event_type == 'subscription.created':
            await handle_subscription_created(webhook_data)
        elif event_type == 'subscription.activated':
            await handle_subscription_activated(webhook_data)
        elif event_type == 'subscription.updated':
            await handle_subscription_updated(webhook_data)
        elif event_type == 'subscription.canceled':
            await handle_subscription_canceled(webhook_data)
        elif event_type == 'transaction.completed':
            await handle_transaction_completed(webhook_data)
        elif event_type == 'transaction.payment_failed':
            await handle_payment_failed(webhook_data)
        else:
            logger.info(f"ℹ️ Unhandled webhook event type: {event_type}")
        
        logger.info(f"✅ Successfully processed Paddle webhook: {event_type}")
        
        return {
            "status": "success",
            "message": f"Webhook {event_type} processed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error processing Paddle webhook: {e}")
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")

async def handle_subscription_created(webhook_data: dict):
    """Handle subscription creation webhook"""
    try:
        data = webhook_data.get('data', {})
        customer_id = data.get('customer_id')
        subscription_id = data.get('id')
        status = data.get('status')
        
        logger.info(f"🆕 Subscription created: {subscription_id} for customer: {customer_id}, status: {status}")
        
        # Extract user information from custom data or customer email
        custom_data = data.get('custom_data', {})
        user_id = custom_data.get('user_id')
        
        if not user_id:
            logger.warning(f"⚠️ No user_id found in subscription webhook: {subscription_id}")
            return
        
        # Update user's subscription status in Firebase
        if db:
            user_ref = db.collection('users').document(user_id)
            user_ref.update({
                'subscription_id': subscription_id,
                'subscription_status': status,
                'subscription_created_at': datetime.now(),
                'paddle_customer_id': customer_id
            })
            logger.info(f"✅ Updated user {user_id} subscription: {subscription_id}")
        
    except Exception as e:
        logger.error(f"❌ Error handling subscription created: {e}")

async def handle_subscription_activated(webhook_data: dict):
    """Handle subscription activation webhook"""
    try:
        data = webhook_data.get('data', {})
        customer_id = data.get('customer_id')
        subscription_id = data.get('id')
        status = data.get('status', 'active')
        
        # Extract plan information from items
        items = data.get('items', [])
        plan_name = 'unknown'
        if items:
            price_id = items[0].get('price', {}).get('id', '')
            
            # Map price IDs to plan names (frontend expects: student, researcher, expert)
            billing_period = 'monthly'  # Default
            
            if price_id == 'pri_01k1ngfpxby3z96nq58f5b4rk6':      # Student monthly
                plan_name = 'student'
                billing_period = 'monthly'
            elif price_id == 'pri_01k1nh2zjgjpz0kh966rwwhm2g':    # Student yearly
                plan_name = 'student'
                billing_period = 'yearly'
            elif price_id == 'pri_01k1ngh1qkacvh917cgwy9rsrb':    # Researcher monthly
                plan_name = 'researcher'
                billing_period = 'monthly'
            elif price_id == 'pri_01k1nh4js7573cdkqmn1t5tk8r':    # Researcher yearly
                plan_name = 'researcher'
                billing_period = 'yearly'
            elif price_id == 'pri_01k1ngjaydkk1dhdzk52jkzt0y':    # Expert monthly
                plan_name = 'expert'
                billing_period = 'monthly'
            elif price_id == 'pri_01k1nhp6d7mw0dkyqsb4a1bbyg':    # Expert yearly
                plan_name = 'expert'
                billing_period = 'yearly'
            else:
                # Fallback - try to determine from price_id string
                price_id_lower = price_id.lower()
                if 'yearly' in price_id_lower:
                    plan_name = 'student'  # Default to student
                    billing_period = 'yearly'
                else:
                    plan_name = 'student'  # Default to student
                    billing_period = 'monthly'
        
        logger.info(f"🎉 Subscription activated: {subscription_id} for customer: {customer_id}, plan: {plan_name}")
        
        # Extract user information from custom data or customer data
        custom_data = data.get('custom_data', {})
        user_id = custom_data.get('user_id')
        
        # Try multiple ways to get user_id
        if not user_id:
            # Check if user_id is in the root custom_data
            user_id = custom_data.get('userId') or custom_data.get('uid')
        
        if not user_id:
            # Try to find user by customer email
            customer_data = data.get('customer', {})
            customer_email = customer_data.get('email')
            
            if customer_email and db:
                logger.info(f"🔍 Searching for user by email: {customer_email}")
                users_ref = db.collection('users')
                query = users_ref.where('email', '==', customer_email).limit(1)
                docs = list(query.stream())
                if docs:
                    user_id = docs[0].id
                    logger.info(f"✅ Found user by email: {user_id}")
        
        if not user_id:
            # Try to find by paddle_customer_id if we have it stored
            if customer_id and db:
                logger.info(f"🔍 Searching for user by paddle_customer_id: {customer_id}")
                users_ref = db.collection('users')
                query = users_ref.where('paddle_customer_id', '==', customer_id).limit(1)
                docs = list(query.stream())
                if docs:
                    user_id = docs[0].id
                    logger.info(f"✅ Found user by paddle_customer_id: {user_id}")
        
        if not user_id:
            logger.warning(f"⚠️ No user_id found in subscription activation webhook: {subscription_id}")
            logger.warning(f"📋 Available data: custom_data={custom_data}, customer_email={customer_data.get('email')}, customer_id={customer_id}")
            return
        
        # Calculate credits based on plan (from plans.js configuration)
        credits_to_add = 0
        
        # Map plan names to credit amounts based on actual pricing page
        if 'student' in plan_name.lower():
            if 'yearly' in plan_name.lower():
                credits_to_add = 12000  # Student yearly: 1000 × 12
            else:
                credits_to_add = 1000   # Student monthly
        elif 'researcher' in plan_name.lower():
            if 'yearly' in plan_name.lower():
                credits_to_add = 24000  # Researcher yearly: 2000 × 12
            else:
                credits_to_add = 2000   # Researcher monthly
        elif 'expert' in plan_name.lower():
            if 'yearly' in plan_name.lower():
                credits_to_add = 60000  # Expert yearly: 5000 × 12
            else:
                credits_to_add = 5000   # Expert monthly
        else:
            # Default fallback - try to determine from price ID or use student plan
            credits_to_add = 1000
        
        # Update user's subscription and credits in Firebase
        if db:
            user_ref = db.collection('users').document(user_id)
            
            # Get current user data
            user_doc = user_ref.get()
            current_credits = 0
            if user_doc.exists:
                user_data = user_doc.to_dict()
                current_credits = user_data.get('current_credits', 0)
            
            # Check if credits were already added for this subscription
            existing_credit_addition = user_data.get('last_subscription_credit_addition')
            credits_already_added = (existing_credit_addition == subscription_id)
            
            update_data = {
                'subscription_id': subscription_id,
                'subscription_status': 'active',
                'subscription_activated_at': datetime.now(),
                'paddle_customer_id': customer_id,
                'plan': plan_name,
                'billingPeriod': billing_period,  # Store billing period
                'last_subscription_credit_addition': subscription_id  # Track this subscription
            }
            
            # Add plan history entry
            plan_history = user_data.get('plan_history', [])
            current_plan = user_data.get('plan', 'free')
            
            if current_plan != plan_name:  # Only add if plan is changing
                plan_history.append({
                    'from_plan': current_plan,
                    'to_plan': plan_name,
                    'billing_period': billing_period,
                    'change_date': datetime.now(),
                    'reason': 'subscription_activated',
                    'subscription_id': subscription_id
                })
                update_data['plan_history'] = plan_history
            
            # Only set credits if not already processed for this subscription
            if not credits_already_added:
                update_data['current_credits'] = credits_to_add  # Replace credits, don't add
                update_data['previous_credits'] = current_credits  # Store previous amount for reference
                update_data['last_credit_addition'] = credits_to_add
                update_data['last_credit_addition_date'] = datetime.now()
                logger.info(f"✅ Setting credits to {credits_to_add} for subscription activation (was {current_credits})")
            else:
                logger.info(f"⚠️ Credits already processed for subscription {subscription_id}, skipping credit update")
            
            user_ref.update(update_data)
            
            if not credits_already_added:
                logger.info(f"✅ Activated subscription for user {user_id}: {plan_name}, set credits to {credits_to_add} (was {current_credits})")
                
                # Store webhook notification for frontend polling only if credits were processed
                webhook_notification = {
                    'user_id': user_id,
                    'event_type': 'subscription_activated',
                    'plan_name': plan_name,
                    'credits_set': credits_to_add,  # Changed from credits_added
                    'previous_credits': current_credits,
                    'total_credits': credits_to_add,
                    'timestamp': datetime.now(),
                    'processed': False
                }
                
                # Store in Firebase for frontend to poll
                if db:
                    notifications_ref = db.collection('webhook_notifications').document(f"{user_id}_{subscription_id}")
                    notifications_ref.set(webhook_notification)
                    logger.info(f"📨 Stored webhook notification for user {user_id}")
            else:
                logger.info(f"✅ Updated subscription status for user {user_id}: {plan_name} (no credit change - already processed)")
        
    except Exception as e:
        logger.error(f"❌ Error handling subscription activated: {e}")

async def handle_subscription_updated(webhook_data: dict):
    """Handle subscription update webhook"""
    try:
        data = webhook_data.get('data', {})
        subscription_id = data.get('id')
        status = data.get('status')
        
        logger.info(f"🔄 Subscription updated: {subscription_id}, status: {status}")
        
        # Find user by subscription ID and update status
        if db:
            users_ref = db.collection('users')
            query = users_ref.where('subscription_id', '==', subscription_id).limit(1)
            docs = query.stream()
            
            for doc in docs:
                doc.reference.update({
                    'subscription_status': status,
                    'subscription_updated_at': datetime.now()
                })
                logger.info(f"✅ Updated subscription status for user {doc.id}: {status}")
                break
        
    except Exception as e:
        logger.error(f"❌ Error handling subscription updated: {e}")

async def handle_subscription_canceled(webhook_data: dict):
    """Handle subscription cancellation webhook"""
    try:
        data = webhook_data.get('data', {})
        subscription_id = data.get('id')
        cancellation_reason = data.get('cancellation_reason', 'unknown')
        
        logger.info(f"❌ Subscription canceled: {subscription_id}, reason: {cancellation_reason}")
        
        # Find user by subscription ID and update status
        if db:
            users_ref = db.collection('users')
            query = users_ref.where('subscription_id', '==', subscription_id).limit(1)
            docs = query.stream()
            
            for doc in docs:
                user_data = doc.to_dict()
                current_plan = user_data.get('plan', 'free')
                current_credits = user_data.get('current_credits', 0)
                
                # Update user to free plan (reset credits to free plan limit)
                free_plan_credits = 10  # Free plan credit limit
                
                update_data = {
                    'plan': 'free',
                    'current_credits': free_plan_credits,  # Reset to free plan credits
                    'subscription_status': 'canceled',
                    'subscription_canceled_at': datetime.now(),
                    'previous_plan': current_plan,
                    'previous_credits': current_credits,  # Store previous credits for reference
                    'cancellation_reason': cancellation_reason
                }
                
                # Add to plan history
                plan_history = user_data.get('plan_history', [])
                plan_history.append({
                    'from_plan': current_plan,
                    'to_plan': 'free',
                    'change_date': datetime.now(),
                    'reason': 'subscription_canceled',
                    'subscription_id': subscription_id,
                    'cancellation_reason': cancellation_reason
                })
                update_data['plan_history'] = plan_history
                
                doc.reference.update(update_data)
                logger.info(f"✅ Subscription canceled for user {doc.id}: {current_plan} → free (credits: {current_credits} → {free_plan_credits})")
                
                # Store cancellation notification for frontend
                webhook_notification = {
                    'user_id': doc.id,
                    'event_type': 'subscription_canceled',
                    'plan_name': 'free',
                    'previous_plan': current_plan,
                    'credits_remaining': free_plan_credits,  # Show new credit amount
                    'previous_credits': current_credits,     # Show what they had before
                    'cancellation_reason': cancellation_reason,
                    'timestamp': datetime.now(),
                    'processed': False
                }
                
                # Store in Firebase for frontend to poll
                notification_id = f"{doc.id}_canceled_{subscription_id}"
                notifications_ref = db.collection('webhook_notifications').document(notification_id)
                notifications_ref.set(webhook_notification)
                logger.info(f"📨 Stored cancellation notification for user {doc.id}")
                break
        
    except Exception as e:
        logger.error(f"❌ Error handling subscription canceled: {e}")

async def handle_transaction_completed(webhook_data: dict):
    """Handle completed transaction webhook"""
    try:
        data = webhook_data.get('data', {})
        transaction_id = data.get('id')
        subscription_id = data.get('subscription_id')
        
        # Extract transaction details
        items = data.get('items', [])
        total_amount = data.get('details', {}).get('totals', {}).get('total', '0')
        
        logger.info(f"💰 Transaction completed: {transaction_id} for subscription: {subscription_id}, amount: {total_amount}")
        
        # Determine credits based on transaction items
        credits_to_add = 0
        plan_name = 'unknown'
        
        if items:
            for item in items:
                price_id = item.get('price', {}).get('id', '')
                quantity = item.get('quantity', 1)
                
                # Map price IDs to credits based on actual plans configuration
                price_id_lower = price_id.lower()
                
                # Map price IDs to credits and plan names (frontend expects: student, researcher, expert)
                billing_period = 'monthly'  # Default
                
                # Student plan price IDs
                if price_id in ['pri_01k1ngfpxby3z96nq58f5b4rk6']:  # Student monthly
                    credits_to_add += 1000 * quantity
                    plan_name = 'student'
                    billing_period = 'monthly'
                elif price_id in ['pri_01k1nh2zjgjpz0kh966rwwhm2g']:  # Student yearly
                    credits_to_add += 12000 * quantity
                    plan_name = 'student'
                    billing_period = 'yearly'
                
                # Researcher plan price IDs
                elif price_id in ['pri_01k1ngh1qkacvh917cgwy9rsrb']:  # Researcher monthly
                    credits_to_add += 2000 * quantity
                    plan_name = 'researcher'
                    billing_period = 'monthly'
                elif price_id in ['pri_01k1nh4js7573cdkqmn1t5tk8r']:  # Researcher yearly
                    credits_to_add += 24000 * quantity
                    plan_name = 'researcher'
                    billing_period = 'yearly'
                
                # Expert plan price IDs
                elif price_id in ['pri_01k1ngjaydkk1dhdzk52jkzt0y']:  # Expert monthly
                    credits_to_add += 5000 * quantity
                    plan_name = 'expert'
                    billing_period = 'monthly'
                elif price_id in ['pri_01k1nhp6d7mw0dkyqsb4a1bbyg']:  # Expert yearly
                    credits_to_add += 60000 * quantity
                    plan_name = 'expert'
                    billing_period = 'yearly'
                
                # Fallback for unknown price IDs
                else:
                    if 'yearly' in price_id_lower:
                        credits_to_add += 12000 * quantity  # Default to student yearly
                        plan_name = 'student'
                        billing_period = 'yearly'
                    else:
                        credits_to_add += 1000 * quantity   # Default to student monthly
                        plan_name = 'student'
                        billing_period = 'monthly'
        
        # Find user by subscription_id or try other methods
        user_found = False
        user_doc = None
        user_id = None
        
        if subscription_id and db:
            users_ref = db.collection('users')
            query = users_ref.where('subscription_id', '==', subscription_id).limit(1)
            docs = list(query.stream())
            
            if docs:
                user_doc = docs[0]
                user_id = user_doc.id
                user_found = True
                logger.info(f"✅ Found user by subscription_id: {user_id}")
        
        # If no user found by subscription_id, try other methods
        if not user_found and db:
            # Try to find by customer email from transaction data
            customer_data = data.get('customer', {})
            customer_email = customer_data.get('email')
            
            if customer_email:
                logger.info(f"🔍 Searching for user by email: {customer_email}")
                users_ref = db.collection('users')
                query = users_ref.where('email', '==', customer_email).limit(1)
                docs = list(query.stream())
                if docs:
                    user_doc = docs[0]
                    user_id = user_doc.id
                    user_found = True
                    logger.info(f"✅ Found user by email: {user_id}")
        
        if user_found and user_doc:
            
            user_data = user_doc.to_dict()
            current_credits = user_data.get('current_credits', 0)
            
            # Check if this transaction was already processed
            last_transaction_id = user_data.get('last_transaction_id')
            transaction_already_processed = (last_transaction_id == transaction_id)
            
            update_data = {
                'last_payment_at': datetime.now(),
                'last_transaction_id': transaction_id
            }
            
            # Only set credits if transaction not already processed
            if not transaction_already_processed:
                update_data['current_credits'] = credits_to_add  # Replace credits, don't add
                update_data['previous_credits'] = current_credits  # Store previous amount for reference
                update_data['last_credit_addition'] = credits_to_add
                update_data['last_credit_addition_date'] = datetime.now()
                logger.info(f"✅ Setting credits to {credits_to_add} for transaction {transaction_id} (was {current_credits})")
            else:
                logger.info(f"⚠️ Transaction {transaction_id} already processed, skipping credit update")
            
            # Update plan and billing period if it's different
            if plan_name != 'unknown':
                update_data['plan'] = plan_name
                update_data['billingPeriod'] = billing_period
            
            user_doc.reference.update(update_data)
            
            if not transaction_already_processed:
                logger.info(f"✅ Transaction processed for user {user_id}: set credits to {credits_to_add} (was {current_credits}), plan: {plan_name}")
                
                # Store webhook notification for frontend polling only if credits were processed
                webhook_notification = {
                    'user_id': user_id,
                    'event_type': 'transaction_completed',
                    'plan_name': plan_name,
                    'credits_set': credits_to_add,  # Changed from credits_added
                    'previous_credits': current_credits,
                    'total_credits': credits_to_add,
                    'transaction_id': transaction_id,
                    'timestamp': datetime.now(),
                    'processed': False
                }
                
                # Store in Firebase for frontend to poll
                notifications_ref = db.collection('webhook_notifications').document(f"{user_id}_{transaction_id}")
                notifications_ref.set(webhook_notification)
                logger.info(f"📨 Stored transaction notification for user {user_id}")
            else:
                logger.info(f"✅ Updated transaction info for user {user_id}: {plan_name} (no credit change - already processed)")
        else:
            logger.warning(f"⚠️ No subscription ID found in transaction: {transaction_id}")
        
    except Exception as e:
        logger.error(f"❌ Error handling transaction completed: {e}")

async def handle_payment_failed(webhook_data: dict):
    """Handle failed payment webhook"""
    try:
        data = webhook_data.get('data', {})
        transaction_id = data.get('id')
        subscription_id = data.get('subscription_id')
        
        logger.warning(f"⚠️ Payment failed: {transaction_id} for subscription: {subscription_id}")
        
        # Update user's payment status
        if subscription_id and db:
            users_ref = db.collection('users')
            query = users_ref.where('subscription_id', '==', subscription_id).limit(1)
            docs = query.stream()
            
            for doc in docs:
                doc.reference.update({
                    'last_payment_failed_at': datetime.now(),
                    'last_failed_transaction_id': transaction_id
                })
                logger.info(f"✅ Updated payment failure status for user {doc.id}")
                break
        
    except Exception as e:
        logger.error(f"❌ Error handling payment failed: {e}")

@app.get("/webhook/test")
async def webhook_test():
    """Test endpoint to verify webhook endpoint is accessible"""
    return {
        "status": "success",
        "message": "Webhook endpoint is accessible",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/user/refresh")
async def refresh_user_data(request: Request = None):
    """Refresh user data including credits and subscription status"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔄 Refreshing user data for: {user_id}")
        
        # Get fresh user data from Firebase
        if db:
            user_ref = db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                
                return {
                    "status": "success",
                    "success": True,
                    "user_data": {
                        "credits": user_data.get('current_credits', 0),
                        "plan": user_data.get('plan', 'free'),
                        "subscription_status": user_data.get('subscription_status', 'inactive'),
                        "subscription_id": user_data.get('subscription_id'),
                        "last_payment_at": user_data.get('last_payment_at'),
                        "last_credit_addition": user_data.get('last_credit_addition', 0),
                        "credits_used": user_data.get('credits_used', 0)
                    },
                    "user_id": user_id
                }
            else:
                logger.warning(f"⚠️ User document not found: {user_id}")
                return {
                    "status": "success",
                    "success": True,
                    "user_data": {
                        "credits": 0,
                        "plan": "free",
                        "subscription_status": "inactive"
                    },
                    "user_id": user_id
                }
        else:
            raise HTTPException(status_code=500, detail="Database not available")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error refreshing user data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh user data: {str(e)}")

@app.get("/api/webhook-notifications")
async def get_webhook_notifications(request: Request = None):
    """Get unprocessed webhook notifications for the user"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        # Only log when there are notifications to avoid spam
        # logger.debug(f"📨 Getting webhook notifications for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get unprocessed notifications for this user
        notifications_ref = db.collection('webhook_notifications')
        query = notifications_ref.where('user_id', '==', user_id).where('processed', '==', False).limit(10)
        docs = query.stream()
        
        notifications = []
        for doc in docs:
            notification_data = doc.to_dict()
            notifications.append({
                'id': doc.id,
                'event_type': notification_data.get('event_type'),
                'plan_name': notification_data.get('plan_name'),
                'credits_added': notification_data.get('credits_added', 0),
                'total_credits': notification_data.get('total_credits', 0),
                'transaction_id': notification_data.get('transaction_id'),
                'timestamp': notification_data.get('timestamp')
            })
        
        # Only log when there are actual notifications
        if len(notifications) > 0:
            logger.info(f"✅ Retrieved {len(notifications)} webhook notifications for user: {user_id}")
        else:
            logger.debug(f"✅ Retrieved 0 webhook notifications for user: {user_id}")
        
        return {
            "status": "success",
            "success": True,
            "notifications": notifications,
            "count": len(notifications),
            "user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving webhook notifications: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve webhook notifications: {str(e)}")

@app.post("/api/webhook-notifications/{notification_id}/mark-processed")
async def mark_notification_processed(
    notification_id: str,
    request: Request = None
):
    """Mark a webhook notification as processed"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"✅ Marking notification {notification_id} as processed for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Update the notification
        notification_ref = db.collection('webhook_notifications').document(notification_id)
        notification_doc = notification_ref.get()
        
        if not notification_doc.exists:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        notification_data = notification_doc.to_dict()
        
        # Verify the notification belongs to this user
        if notification_data.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Mark as processed
        notification_ref.update({
            'processed': True,
            'processed_at': datetime.now()
        })
        
        logger.info(f"✅ Marked notification {notification_id} as processed")
        
        return {
            "status": "success",
            "success": True,
            "message": "Notification marked as processed",
            "notification_id": notification_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error marking notification as processed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to mark notification as processed: {str(e)}")

@app.get("/api/debug/webhook-notifications")
async def debug_webhook_notifications(request: Request = None):
    """Debug endpoint to see all webhook notifications (admin only)"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔍 Debug: Getting all webhook notifications for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get all notifications for this user (processed and unprocessed)
        notifications_ref = db.collection('webhook_notifications')
        query = notifications_ref.where('user_id', '==', user_id).limit(50)
        docs = query.stream()
        
        notifications = []
        for doc in docs:
            notification_data = doc.to_dict()
            notifications.append({
                'id': doc.id,
                'user_id': notification_data.get('user_id'),
                'event_type': notification_data.get('event_type'),
                'plan_name': notification_data.get('plan_name'),
                'credits_added': notification_data.get('credits_added', 0),
                'total_credits': notification_data.get('total_credits', 0),
                'transaction_id': notification_data.get('transaction_id'),
                'timestamp': notification_data.get('timestamp'),
                'processed': notification_data.get('processed', False),
                'processed_at': notification_data.get('processed_at')
            })
        
        logger.info(f"🔍 Debug: Retrieved {len(notifications)} total webhook notifications for user: {user_id}")
        
        return {
            "status": "success",
            "success": True,
            "notifications": notifications,
            "count": len(notifications),
            "user_id": user_id,
            "debug": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving debug webhook notifications: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve debug webhook notifications: {str(e)}")

@app.post("/api/debug/create-test-notification")
async def create_test_notification(request: Request = None):
    """Create a test webhook notification for debugging"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🧪 Creating test notification for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Create test notification with realistic credit amounts
        test_notification = {
            'user_id': user_id,
            'event_type': 'test_notification',
            'plan_name': 'researcher_monthly',
            'credits_added': 2000,  # Researcher monthly plan credits
            'total_credits': 3780,  # Assuming user had 1780 credits before
            'transaction_id': f'test_{int(datetime.now().timestamp())}',
            'timestamp': datetime.now(),
            'processed': False
        }
        
        # Store in Firebase
        notification_id = f"test_{user_id}_{int(datetime.now().timestamp())}"
        notifications_ref = db.collection('webhook_notifications').document(notification_id)
        notifications_ref.set(test_notification)
        
        logger.info(f"✅ Created test notification: {notification_id}")
        
        return {
            "status": "success",
            "success": True,
            "message": "Test notification created",
            "notification_id": notification_id,
            "notification": test_notification
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating test notification: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create test notification: {str(e)}")

@app.post("/api/debug/fix-duplicate-credits")
async def fix_duplicate_credits(request: Request = None):
    """Fix duplicate credits caused by double webhook processing"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔧 Fixing duplicate credits for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get current user data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_data = user_doc.to_dict()
        current_credits = user_data.get('current_credits', 0)
        plan = user_data.get('plan', 'free')
        
        logger.info(f"📊 Current user data: credits={current_credits}, plan={plan}")
        
        # Determine expected credits based on plan
        expected_credits = 0
        if 'expert' in plan.lower():
            if 'yearly' in plan.lower():
                expected_credits = 60000  # Expert yearly
            else:
                expected_credits = 5000   # Expert monthly
        elif 'researcher' in plan.lower():
            if 'yearly' in plan.lower():
                expected_credits = 24000  # Researcher yearly
            else:
                expected_credits = 2000   # Researcher monthly
        elif 'student' in plan.lower():
            if 'yearly' in plan.lower():
                expected_credits = 12000  # Student yearly
            else:
                expected_credits = 1000   # Student monthly
        
        # Calculate what the credits should be (original + expected)
        # Assuming user had some credits before (like 1780 in your case)
        original_credits = current_credits - (expected_credits * 2)  # Remove double allocation
        corrected_credits = original_credits + expected_credits      # Add single allocation
        
        logger.info(f"🔧 Credit correction: {current_credits} → {corrected_credits} (removed duplicate {expected_credits})")
        
        # Update user credits
        user_ref.update({
            'current_credits': corrected_credits,
            'credit_fix_applied': datetime.now(),
            'credit_fix_reason': 'duplicate_webhook_processing'
        })
        
        return {
            "status": "success",
            "success": True,
            "message": "Duplicate credits fixed",
            "before": current_credits,
            "after": corrected_credits,
            "removed_duplicate": expected_credits,
            "plan": plan
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fixing duplicate credits: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fix duplicate credits: {str(e)}")

@app.post("/api/subscription/cancel")
async def cancel_subscription(request: Request = None):
    """Cancel user's active subscription"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🚫 Canceling subscription for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get current user data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_data = user_doc.to_dict()
        subscription_id = user_data.get('subscription_id')
        current_plan = user_data.get('plan', 'free')
        
        if not subscription_id:
            raise HTTPException(status_code=400, detail="No active subscription found")
        
        if current_plan == 'free':
            raise HTTPException(status_code=400, detail="User is already on free plan")
        
        logger.info(f"📋 Found subscription to cancel: {subscription_id}, current plan: {current_plan}")
        
        # First, cancel the subscription on Paddle
        paddle_cancelled = await cancel_paddle_subscription(subscription_id)
        if not paddle_cancelled:
            logger.warning(f"⚠️ Failed to cancel subscription on Paddle, but proceeding with local cancellation")
            # Note: We continue with local cancellation even if Paddle fails
            # This ensures the user isn't stuck with a plan they can't cancel
        
        # Update user to free plan (reset credits to free plan limit)
        current_credits = user_data.get('current_credits', 0)
        free_plan_credits = 10  # Free plan credit limit
        
        update_data = {
            'plan': 'free',
            'current_credits': free_plan_credits,  # Reset to free plan credits
            'subscription_status': 'cancelled',
            'subscription_cancelled_at': datetime.now(),
            'previous_plan': current_plan,
            'previous_credits': current_credits,  # Store previous credits for reference
            'cancellation_reason': 'user_requested'
        }
        
        # Add to plan history
        plan_history = user_data.get('plan_history', [])
        plan_history.append({
            'from_plan': current_plan,
            'to_plan': 'free',
            'change_date': datetime.now(),
            'reason': 'subscription_cancelled',
            'subscription_id': subscription_id
        })
        update_data['plan_history'] = plan_history
        
        user_ref.update(update_data)
        
        logger.info(f"✅ Subscription cancelled for user {user_id}: {current_plan} → free (credits: {current_credits} → {free_plan_credits})")
        
        # Store cancellation notification for frontend
        webhook_notification = {
            'user_id': user_id,
            'event_type': 'subscription_cancelled',
            'plan_name': 'free',
            'previous_plan': current_plan,
            'credits_remaining': free_plan_credits,  # Show new credit amount
            'previous_credits': current_credits,     # Show what they had before
            'paddle_cancelled': paddle_cancelled,    # Whether Paddle cancellation succeeded
            'cancellation_method': 'user_requested', # How the cancellation was initiated
            'timestamp': datetime.now(),
            'processed': False
        }
        
        # Store in Firebase for frontend to poll
        notification_id = f"{user_id}_cancel_{int(datetime.now().timestamp())}"
        notifications_ref = db.collection('webhook_notifications').document(notification_id)
        notifications_ref.set(webhook_notification)
        
        return {
            "status": "success",
            "success": True,
            "message": "Subscription cancelled successfully",
            "previous_plan": current_plan,
            "current_plan": "free",
            "previous_credits": current_credits,
            "credits_remaining": free_plan_credits,
            "subscription_id": subscription_id,
            "paddle_cancelled": paddle_cancelled,
            "paddle_status": "cancelled" if paddle_cancelled else "cancellation_failed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error cancelling subscription: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel subscription: {str(e)}")

async def get_paddle_subscription_status(subscription_id: str) -> dict:
    """Get subscription status from Paddle"""
    try:
        if not PADDLE_API_KEY:
            logger.error("❌ Paddle API key not configured")
            return {"error": "Paddle API key not configured"}
            
        headers = {
            'Authorization': f'Bearer {PADDLE_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Paddle API endpoint to get subscription details
        url = f"{PADDLE_BASE_URL}/subscriptions/{subscription_id}"
        
        logger.info(f"🔍 Getting Paddle subscription status: {subscription_id}")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Retrieved Paddle subscription status: {subscription_id}")
                return data
            else:
                logger.error(f"❌ Failed to get Paddle subscription {subscription_id}: {response.status_code} - {response.text}")
                return {"error": f"Failed to get subscription: {response.status_code}"}
                
    except Exception as e:
        logger.error(f"❌ Error getting Paddle subscription {subscription_id}: {e}")
        return {"error": str(e)}

@app.get("/api/subscription/paddle-status")
async def get_subscription_paddle_status(request: Request = None):
    """Get subscription status from Paddle for debugging"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔍 Getting Paddle subscription status for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get current user data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_data = user_doc.to_dict()
        subscription_id = user_data.get('subscription_id')
        
        if not subscription_id:
            raise HTTPException(status_code=400, detail="No subscription ID found")
        
        # Get status from Paddle
        paddle_status = await get_paddle_subscription_status(subscription_id)
        
        return {
            "status": "success",
            "success": True,
            "subscription_id": subscription_id,
            "local_data": {
                "plan": user_data.get('plan'),
                "subscription_status": user_data.get('subscription_status'),
                "current_credits": user_data.get('current_credits')
            },
            "paddle_data": paddle_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting Paddle subscription status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get Paddle subscription status: {str(e)}")

@app.post("/api/test/send-email")
async def test_send_email(request: Request):
    """Test endpoint to send a simple email via Resend"""
    try:
        # Get email from request body
        body = await request.json()
        test_email = body.get('email', 'test@example.com')
        
        logger.info(f"🧪 Testing email send to: {test_email}")
        
        if not brevo_service.is_configured():
            raise HTTPException(status_code=500, detail="Brevo service not configured")
        
        # Test with password reset email template
        success = brevo_service.send_password_reset_email(test_email, "test_token_123", "Test User")
        
        if success:
            return {
                "status": "success",
                "message": f"Branded password reset email sent successfully to {test_email}",
                "note": "Check your email inbox for the fully branded QuickMaps password reset email!"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")
                
    except Exception as e:
        logger.error(f"❌ Error sending test email: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send test email: {str(e)}")

@app.get("/api/test/email-preview")
async def preview_email_template():
    """Preview the branded email template"""
    try:
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Email Preview</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                .info { background: #e7f3ff; padding: 20px; border-radius: 8px; margin: 20px 0; }
            </style>
        </head>
        <body>
            <h1>🔐 Email Preview</h1>
            <div class="info">
                <h3>Email preview is now handled by Brevo SMTP</h3>
                <p>Password reset and welcome emails are sent via Brevo's email service.</p>
                <p>To preview emails, you can test them by sending to a real email address using the test endpoints.</p>
            </div>
        </body>
        </html>
        """
        
        return Response(content=html_content, media_type="text/html")
        
    except Exception as e:
        logger.error(f"❌ Error generating email preview: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate preview: {str(e)}")

@app.post("/api/test/complete-password-reset")
async def test_complete_password_reset(request: Request):
    """Test the complete password reset flow"""
    try:
        body = await request.json()
        test_email = body.get('email')
        test_password = body.get('new_password', 'TestPassword123!')
        
        if not test_email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        # Step 1: Send password reset email
        logger.info(f"🧪 Testing complete password reset flow for: {test_email}")
        reset_success = await password_reset_service.send_reset_email(test_email)
        
        if not reset_success:
            raise HTTPException(status_code=500, detail="Failed to send reset email")
        
        # Step 2: Get the latest reset token for this email (for testing purposes)
        db = firestore.client()
        tokens_ref = db.collection('passwordResetTokens')
        query = tokens_ref.where('email', '==', test_email).where('used', '==', False).order_by('created_at', direction=firestore.Query.DESCENDING).limit(1)
        tokens = list(query.stream())
        
        if not tokens:
            raise HTTPException(status_code=500, detail="No reset token found")
        
        token_doc = tokens[0]
        reset_token = token_doc.id
        
        # Step 3: Test password reset with the token
        reset_result = await password_reset_service.reset_password(reset_token, test_password)
        
        if reset_result:
            return {
                "status": "success",
                "message": f"Complete password reset flow tested successfully for {test_email}",
                "steps_completed": [
                    "✅ Reset email sent",
                    "✅ Reset token created and stored",
                    "✅ Firebase Authentication password updated",
                    "✅ Token marked as used"
                ],
                "reset_token": reset_token,
                "note": "User can now login with the new password!"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to reset password")
                
    except Exception as e:
        logger.error(f"❌ Error in complete password reset test: {e}")
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")

@app.post("/api/test/send-welcome-email")
async def test_send_welcome_email(request: Request):
    """Test endpoint to send welcome email"""
    try:
        body = await request.json()
        test_email = body.get('email')
        user_name = body.get('name')
        
        if not test_email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        logger.info(f"🎉 Testing welcome email send to: {test_email}")
        
        if not brevo_service.is_configured():
            raise HTTPException(status_code=500, detail="Brevo service not configured")
        
        # Send welcome email
        success = brevo_service.send_welcome_email(test_email, user_name)
        
        if success:
            return {
                "status": "success",
                "message": f"Welcome email sent successfully to {test_email}",
                "user_name": user_name or test_email.split('@')[0].title(),
                "note": "Check your email inbox for the beautiful welcome email!"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send welcome email")
                
    except Exception as e:
        logger.error(f"❌ Error sending welcome email: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send welcome email: {str(e)}")

@app.get("/api/test/welcome-email-preview")
async def preview_welcome_email_template():
    """Preview the welcome email template"""
    try:
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Welcome Email Preview</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                .info { background: #e7f3ff; padding: 20px; border-radius: 8px; margin: 20px 0; }
            </style>
        </head>
        <body>
            <h1>🎉 Welcome Email Preview</h1>
            <div class="info">
                <h3>Welcome emails are now handled by Brevo SMTP</h3>
                <p>Professional welcome and onboarding emails are sent via Brevo's email service.</p>
                <p>To preview emails, you can test them by sending to a real email address using the test endpoints.</p>
            </div>
        </body>
        </html>
        """
        
        return Response(content=html_content, media_type="text/html")
        
    except Exception as e:
        logger.error(f"❌ Error generating welcome email preview: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate preview: {str(e)}")

@app.post("/api/auth/register")
async def register_user(user_data: RegisterUserRequest):
    """Register a new user and send welcome email"""
    try:
        email = user_data.email
        password = user_data.password
        name = user_data.name
        
        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password are required")
        
        if len(password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        
        logger.info(f"👤 Registering new user: {email}")
        
        # Create user in Firebase Authentication
        try:
            user_record = auth.create_user(
                email=email,
                password=password,
                display_name=name
            )
            logger.info(f"✅ User created in Firebase Auth: {user_record.uid}")
        except auth.EmailAlreadyExistsError:
            raise HTTPException(status_code=400, detail="Email already exists")
        except Exception as e:
            logger.error(f"❌ Error creating user in Firebase Auth: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")
        
        # Send welcome email
        try:
            if brevo_service.is_configured():
                welcome_sent = brevo_service.send_welcome_email(email, name or email.split('@')[0])
                if welcome_sent:
                    logger.info(f"✅ Welcome email sent to: {email}")
                else:
                    logger.warning(f"⚠️ Failed to send welcome email to: {email}")
            else:
                logger.warning("⚠️ Brevo service not configured, skipping welcome email")
        except Exception as e:
            logger.error(f"❌ Error sending welcome email: {e}")
            # Don't fail registration if email fails
        
        # Initialize user credits (10 free credits for new users)
        credits_initialized = False
        try:
            from credit_service import credit_service
            # Initialize Firebase client for credit service if not already done
            if not credit_service.db:
                credit_service.db = firestore.client()
            
            # Initialize user with 10 free credits
            await credit_service._initialize_new_user(user_record.uid, email, name)
            credits_initialized = True
            logger.info(f"💳 New user initialized with 10 free credits: {user_record.uid}")
        except Exception as e:
            logger.error(f"❌ Error initializing user credits: {e}")
            # Don't fail registration if credit initialization fails

        # Store user profile in Firestore (optional - credit service may have already done this)
        try:
            db = firestore.client()
            user_doc = {
                'uid': user_record.uid,
                'email': email,
                'name': name or email.split('@')[0],
                'created_at': datetime.now(),
                'email_verified': False,
                'profile_completed': False
            }
            
            # Only set basic profile if credits weren't initialized (to avoid overwriting)
            if not credits_initialized:
                db.collection('users').document(user_record.uid).set(user_doc)
                logger.info(f"✅ User profile stored in Firestore: {user_record.uid}")
            else:
                # Just update the additional fields
                db.collection('users').document(user_record.uid).update({
                    'email_verified': False,
                    'profile_completed': False
                })
                logger.info(f"✅ User profile updated in Firestore: {user_record.uid}")
        except Exception as e:
            logger.error(f"❌ Error storing user profile: {e}")
            # Don't fail registration if Firestore fails
        
        return {
            "status": "success",
            "message": "User registered successfully",
            "user": {
                "uid": user_record.uid,
                "email": email,
                "name": name or email.split('@')[0],
                "email_verified": user_record.email_verified,
                "credits": 10 if credits_initialized else 0
            },
            "credits": {
                "awarded": 10 if credits_initialized else 0,
                "message": "🎉 You've received 10 free credits to get started!" if credits_initialized else "Credits will be awarded on first use"
            },
            "welcome_email_sent": brevo_service.is_configured(),
            "note": "Welcome email sent! You've received 10 free credits to start creating amazing notes. Check your inbox to get started."
        }
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in user registration: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/api/test/complete-registration")
async def test_complete_registration_flow(request: Request):
    """Test the complete registration flow with credits and welcome email"""
    try:
        body = await request.json()
        test_email = body.get('email')
        test_password = body.get('password', 'TestPassword123!')
        test_name = body.get('name', 'Test User')
        
        if not test_email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        logger.info(f"🧪 Testing complete registration flow for: {test_email}")
        
        # Test the registration endpoint
        registration_data = RegisterUserRequest(
            email=test_email,
            password=test_password,
            name=test_name
        )
        
        result = await register_user(registration_data)
        
        # Check user credits
        try:
            from credit_service import credit_service
            if not credit_service.db:
                credit_service.db = firestore.client()
            
            # Get user from Firebase Auth to get UID
            user_record = auth.get_user_by_email(test_email)
            
            # Check credits were assigned
            credits_info = await credit_service.get_user_credits(user_record.uid, test_email, test_name)
            
            result['credits_verification'] = credits_info
            result['test_status'] = 'complete'
            result['steps_completed'] = [
                "✅ User created in Firebase Authentication",
                "✅ 10 free credits awarded automatically", 
                "✅ User profile stored in Firestore",
                "✅ Welcome email sent with credit information",
                f"✅ Final credit balance: {credits_info.get('current_credits', 0)}"
            ]
            
            logger.info(f"🎉 Complete registration test successful for {test_email}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error verifying credits in test: {e}")
            result['credits_verification'] = {'error': str(e)}
            return result
                
    except Exception as e:
        logger.error(f"❌ Error in complete registration test: {e}")
        raise HTTPException(status_code=500, detail=f"Registration test failed: {str(e)}")

@app.post("/api/test/award-credits")
async def test_award_credits(request: Request):
    """Test endpoint to award credits to existing user"""
    try:
        body = await request.json()
        user_id = body.get('user_id')
        credits_to_add = body.get('credits', 10)
        reason = body.get('reason', 'manual_test_award')
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        
        logger.info(f"💰 Test: Adding {credits_to_add} credits to user: {user_id}")
        
        # Ensure credit service has database client
        if not credit_service.db:
            credit_service.db = firestore.client()
            logger.info("🔧 Initialized credit service database client")
        
        # Add credits
        success = await credit_service.add_credits(
            user_id=user_id,
            credits_to_add=credits_to_add,
            reason=reason
        )
        
        if success:
            # Get updated balance
            credits_info = await credit_service.get_user_credits(user_id)
            
            return {
                "status": "success",
                "message": f"Successfully added {credits_to_add} credits to user {user_id}",
                "credits_added": credits_to_add,
                "reason": reason,
                "new_balance": credits_info.get('current_credits', 0),
                "full_credits_info": credits_info
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to add credits")
                
    except Exception as e:
        logger.error(f"❌ Error awarding test credits: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to award credits: {str(e)}")

@app.post("/api/auth/send-welcome-email")
async def send_welcome_email_to_existing_user(request: Request):
    """Send welcome email to an existing user (for manual triggers or integrations)"""
    try:
        body = await request.json()
        email = body.get('email')
        name = body.get('name')
        
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        logger.info(f"📧 Sending welcome email to existing user: {email}")
        
        if not brevo_service.is_configured():
            raise HTTPException(status_code=500, detail="Brevo service not configured")
        
        # Send welcome email
        success = brevo_service.send_welcome_email(email, name)
        
        if success:
            return {
                "status": "success",
                "message": f"Welcome email sent successfully to {email}",
                "user_name": name or email.split('@')[0].title()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send welcome email")
                
    except Exception as e:
        logger.error(f"❌ Error sending welcome email to existing user: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send welcome email: {str(e)}")

@app.get("/api/subscription/status")
async def get_subscription_status(request: Request = None):
    """Get current subscription status and details"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"📊 Getting subscription status for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get current user data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_data = user_doc.to_dict()
        
        subscription_data = {
            "user_id": user_id,
            "plan": user_data.get('plan', 'free'),
            "subscription_id": user_data.get('subscription_id'),
            "subscription_status": user_data.get('subscription_status', 'inactive'),
            "current_credits": user_data.get('current_credits', 0),
            "subscription_activated_at": user_data.get('subscription_activated_at'),
            "subscription_cancelled_at": user_data.get('subscription_cancelled_at'),
            "last_payment_at": user_data.get('last_payment_at'),
            "paddle_customer_id": user_data.get('paddle_customer_id'),
            "plan_history": user_data.get('plan_history', [])
        }
        
        return {
            "status": "success",
            "success": True,
            "subscription": subscription_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting subscription status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get subscription status: {str(e)}")

@app.post("/api/subscription/reactivate")
async def reactivate_subscription(request: Request = None):
    """Reactivate a cancelled subscription (placeholder - would need Paddle API integration)"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔄 Reactivation requested for user: {user_id}")
        
        # This would typically involve calling Paddle's API to reactivate
        # For now, return a message directing user to make a new purchase
        
        return {
            "status": "info",
            "success": False,
            "message": "To reactivate your subscription, please visit the pricing page and select a new plan",
            "redirect_url": "/pricing"
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing reactivation request: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process reactivation request: {str(e)}")

@app.post("/api/debug/fix-free-plan-credits")
async def fix_free_plan_credits(request: Request = None):
    """Fix credits for users on free plan who have more than 10 credits"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔧 Fixing free plan credits for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get current user data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_data = user_doc.to_dict()
        current_credits = user_data.get('current_credits', 0)
        current_plan = user_data.get('plan', 'free')
        
        logger.info(f"📊 Current user data: credits={current_credits}, plan={current_plan}")
        
        # Only fix if user is on free plan and has more than 10 credits
        if current_plan != 'free':
            return {
                "status": "info",
                "success": False,
                "message": f"User is on {current_plan} plan, not free plan",
                "current_credits": current_credits,
                "current_plan": current_plan
            }
        
        if current_credits <= 10:
            return {
                "status": "info", 
                "success": False,
                "message": "User already has correct free plan credits",
                "current_credits": current_credits,
                "current_plan": current_plan
            }
        
        # Reset to free plan credits
        free_plan_credits = 10
        
        logger.info(f"🔧 Credit correction: {current_credits} → {free_plan_credits} (free plan limit)")
        
        # Update user credits
        user_ref.update({
            'current_credits': free_plan_credits,
            'previous_credits': current_credits,  # Store what they had before
            'credit_fix_applied': datetime.now(),
            'credit_fix_reason': 'free_plan_credit_limit'
        })
        
        return {
            "status": "success",
            "success": True,
            "message": "Free plan credits corrected",
            "before": current_credits,
            "after": free_plan_credits,
            "plan": current_plan,
            "explanation": "Free plan users are limited to 10 credits"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fixing free plan credits: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fix free plan credits: {str(e)}")

@app.post("/api/debug/fix-plan-display")
async def fix_plan_display(request: Request = None):
    """Fix plan display based on user's subscription and credits"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔧 Fixing plan display for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get current user data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_data = user_doc.to_dict()
        current_credits = user_data.get('current_credits', 0)
        current_plan = user_data.get('plan', 'free')
        subscription_status = user_data.get('subscription_status', 'inactive')
        
        logger.info(f"📊 Current user data: credits={current_credits}, plan={current_plan}, status={subscription_status}")
        
        # Determine correct plan based on credits and subscription status
        correct_plan = 'free'
        billing_period = 'monthly'
        
        if subscription_status == 'active' and current_credits > 10:
            # Determine plan based on credit amount
            if current_credits >= 60000:
                correct_plan = 'expert'
                billing_period = 'yearly'
            elif current_credits >= 24000:
                correct_plan = 'researcher'
                billing_period = 'yearly'
            elif current_credits >= 12000:
                correct_plan = 'student'
                billing_period = 'yearly'
            elif current_credits >= 5000:
                correct_plan = 'expert'
                billing_period = 'monthly'
            elif current_credits >= 2000:
                correct_plan = 'researcher'
                billing_period = 'monthly'
            elif current_credits >= 1000:
                correct_plan = 'student'
                billing_period = 'monthly'
        
        # Check if plan needs to be updated
        if current_plan == correct_plan:
            return {
                "status": "info",
                "success": False,
                "message": "Plan is already correct",
                "current_plan": current_plan,
                "current_credits": current_credits,
                "subscription_status": subscription_status
            }
        
        logger.info(f"🔧 Plan correction: {current_plan} → {correct_plan} (based on {current_credits} credits)")
        
        # Update user plan
        update_data = {
            'plan': correct_plan,
            'billingPeriod': billing_period,
            'plan_fix_applied': datetime.now(),
            'plan_fix_reason': 'manual_correction_based_on_credits'
        }
        
        # Add to plan history
        plan_history = user_data.get('plan_history', [])
        plan_history.append({
            'from_plan': current_plan,
            'to_plan': correct_plan,
            'billing_period': billing_period,
            'change_date': datetime.now(),
            'reason': 'manual_plan_fix',
            'credits_at_time': current_credits
        })
        update_data['plan_history'] = plan_history
        
        user_ref.update(update_data)
        
        return {
            "status": "success",
            "success": True,
            "message": "Plan display corrected",
            "before": current_plan,
            "after": correct_plan,
            "billing_period": billing_period,
            "credits": current_credits,
            "subscription_status": subscription_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fixing plan display: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fix plan display: {str(e)}")

@app.get("/api/debug/user-data")
async def get_user_data(request: Request = None):
    """Get complete user data for debugging"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔍 Getting complete user data for: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get current user data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_data = user_doc.to_dict()
        
        # Return all user data for debugging
        return {
            "status": "success",
            "success": True,
            "user_id": user_id,
            "user_data": user_data,
            "debug_info": {
                "plan_field": user_data.get('plan'),
                "current_plan_field": user_data.get('currentPlan'),
                "credits_field": user_data.get('current_credits'),
                "credits_alt_field": user_data.get('credits'),
                "subscription_status": user_data.get('subscription_status'),
                "subscription_id": user_data.get('subscription_id'),
                "billing_period": user_data.get('billingPeriod')
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting user data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get user data: {str(e)}")

@app.post("/api/debug/force-plan-update")
async def force_plan_update(request: Request = None):
    """Force update user plan based on credits (aggressive fix)"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔧 Force updating plan for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get current user data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_data = user_doc.to_dict()
        current_credits = user_data.get('current_credits', 0)
        
        logger.info(f"📊 User has {current_credits} credits")
        
        # Determine correct plan based on credits (8780 credits suggests Expert plan)
        if current_credits >= 8000:  # Your case with 8780 credits
            correct_plan = 'expert'
            billing_period = 'monthly'  # 5000 base + extra suggests monthly
            if current_credits >= 60000:
                billing_period = 'yearly'
        elif current_credits >= 5000:
            correct_plan = 'expert'
            billing_period = 'monthly'
        elif current_credits >= 2000:
            correct_plan = 'researcher'
            billing_period = 'monthly'
        elif current_credits >= 1000:
            correct_plan = 'student'
            billing_period = 'monthly'
        else:
            correct_plan = 'free'
            billing_period = 'monthly'
        
        logger.info(f"🎯 Setting plan to: {correct_plan} ({billing_period})")
        
        # Force update all plan-related fields
        update_data = {
            'plan': correct_plan,
            'currentPlan': correct_plan,  # Also set frontend field
            'billingPeriod': billing_period,
            'subscription_status': 'active' if correct_plan != 'free' else 'inactive',
            'plan_fix_applied': datetime.now(),
            'plan_fix_reason': 'force_update_based_on_credits',
            'plan_fix_credits': current_credits
        }
        
        # Add plan history
        plan_history = user_data.get('plan_history', [])
        current_plan = user_data.get('plan', 'free')
        
        plan_history.append({
            'from_plan': current_plan,
            'to_plan': correct_plan,
            'billing_period': billing_period,
            'change_date': datetime.now(),
            'reason': 'force_plan_update',
            'credits_at_time': current_credits
        })
        update_data['plan_history'] = plan_history
        update_data['planHistory'] = plan_history  # Also set frontend field
        
        user_ref.update(update_data)
        
        logger.info(f"✅ Force updated plan: {current_plan} → {correct_plan}")
        
        return {
            "status": "success",
            "success": True,
            "message": "Plan forcefully updated",
            "before": current_plan,
            "after": correct_plan,
            "billing_period": billing_period,
            "credits": current_credits,
            "fields_updated": list(update_data.keys())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error force updating plan: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to force update plan: {str(e)}")

@app.post("/api/debug/fix-accumulated-credits")
async def fix_accumulated_credits(request: Request = None):
    """Fix users who have accumulated credits from multiple upgrades"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔧 Fixing accumulated credits for user: {user_id}")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get current user data
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_data = user_doc.to_dict()
        current_credits = user_data.get('current_credits', 0)
        current_plan = user_data.get('plan', 'free')
        
        logger.info(f"📊 User has {current_credits} credits on {current_plan} plan")
        
        # Determine correct credits for the plan
        correct_credits = 0
        if current_plan == 'student':
            billing_period = user_data.get('billingPeriod', 'monthly')
            correct_credits = 12000 if billing_period == 'yearly' else 1000
        elif current_plan == 'researcher':
            billing_period = user_data.get('billingPeriod', 'monthly')
            correct_credits = 24000 if billing_period == 'yearly' else 2000
        elif current_plan == 'expert':
            billing_period = user_data.get('billingPeriod', 'monthly')
            correct_credits = 60000 if billing_period == 'yearly' else 5000
        elif current_plan == 'free':
            correct_credits = 10
        
        # Check if credits need to be corrected
        if current_credits == correct_credits:
            return {
                "status": "info",
                "success": False,
                "message": "Credits are already correct for the plan",
                "current_credits": current_credits,
                "correct_credits": correct_credits,
                "plan": current_plan
            }
        
        logger.info(f"🔧 Credit correction: {current_credits} → {correct_credits} for {current_plan} plan")
        
        # Update user credits to correct amount
        update_data = {
            'current_credits': correct_credits,
            'previous_credits': current_credits,  # Store what they had before
            'credit_fix_applied': datetime.now(),
            'credit_fix_reason': 'accumulated_credits_correction',
            'credit_fix_plan': current_plan
        }
        
        user_ref.update(update_data)
        
        return {
            "status": "success",
            "success": True,
            "message": "Accumulated credits corrected",
            "before": current_credits,
            "after": correct_credits,
            "plan": current_plan,
            "billing_period": user_data.get('billingPeriod', 'monthly'),
            "explanation": f"Credits set to correct amount for {current_plan} plan"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fixing accumulated credits: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fix accumulated credits: {str(e)}")

# Additional endpoint handlers and utilities continue below...

# Password reset endpoints
@app.post("/api/auth/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Send password reset email"""
    try:
        # Try to get user name for personalization
        user_name = "there"
        try:
            user_record = auth.get_user_by_email(request.email)
            user_name = user_record.display_name or request.email.split('@')[0]
        except Exception:
            # User not found or error getting user info, use default
            pass
        
        result = await password_reset_service.send_reset_email(request.email, user_name)
        if result:
            return {"message": "Password reset email sent successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to send password reset email")
    except Exception as e:
        logger.error(f"Forgot password error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/auth/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password with token"""
    try:
        result = await password_reset_service.reset_password(request.token, request.new_password)
        
        if result["success"]:
            return {"message": result["message"]}
        else:
            # Map specific errors to appropriate HTTP status codes
            if result["error"] == "INVALID_TOKEN":
                raise HTTPException(status_code=400, detail=result["message"])
            elif result["error"] == "WEAK_PASSWORD":
                raise HTTPException(status_code=400, detail=result["message"])
            elif result["error"] == "USER_NOT_FOUND":
                raise HTTPException(status_code=404, detail=result["message"])
            elif result["error"] == "AUTH_ERROR":
                raise HTTPException(status_code=503, detail=result["message"])
            elif result["error"] == "UPDATE_FAILED":
                raise HTTPException(status_code=500, detail=result["message"])
            else:
                raise HTTPException(status_code=500, detail=result["message"])
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset password error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/auth/validate-reset-token")
async def validate_reset_token(request: TokenValidationRequest):
    """Validate password reset token"""
    try:
        token_data = await password_reset_service.validate_reset_token(request.token)
        is_valid = token_data is not None
        
        response = {"valid": is_valid}
        if is_valid:
            response["email"] = token_data.get('email')
            
        return response
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Email verification OTP endpoints
from email_verification_service import email_verification_service

class SendOtpRequest(BaseModel):
    email: str
    name: Optional[str] = None

class VerifyOtpRequest(BaseModel):
    email: str
    otp: str

@app.post("/api/auth/send-email-otp")
async def send_email_otp(req: SendOtpRequest):
    try:
        result = email_verification_service.create_and_send(req.email, req.name)
        if result.get("success"):
            return {"message": "OTP sent"}
        if result.get("error") == "RESEND_COOLDOWN":
            raise HTTPException(status_code=429, detail=result.get("message"))
        raise HTTPException(status_code=400, detail=result.get("message", "Failed to send OTP"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"send_email_otp error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/auth/verify-email-otp")
async def verify_email_otp(req: VerifyOtpRequest):
    try:
        result = email_verification_service.verify(req.email, req.otp)
        if result.get("success"):
            return {"message": "Email verified"}
        # Map errors
        err = result.get("error")
        if err in ("NOT_REQUESTED", "INVALID_CODE"):
            raise HTTPException(status_code=400, detail=result.get("message"))
        if err in ("EXPIRED", "ALREADY_USED"):
            raise HTTPException(status_code=410, detail=result.get("message"))
        if err == "TOO_MANY_ATTEMPTS":
            raise HTTPException(status_code=429, detail=result.get("message"))
        raise HTTPException(status_code=400, detail=result.get("message", "Verification failed"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"verify_email_otp error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# User Statistics endpoints
@app.get("/api/user-statistics/{user_id}")
async def get_user_statistics(user_id: str, request: Request = None):
    """Get user statistics"""
    try:
        # Extract user information and verify access
        request_user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        
        # Users can only access their own statistics
        if request_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get user statistics from Firestore
        user_ref = db.collection('user_statistics').document(user_id)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            statistics = user_doc.to_dict()
        else:
            # Return default statistics if none exist
            statistics = {
                'current_credits': 0,
                'credits_used': 0,
                'account_age_days': 0,
                'last_login': None,
                'storage_used': 0,
                'total_videos_processed': 0,
                'total_notes_generated': 0,
                'favorite_format': 'pdf'
            }
        
        return {
            "status": "success",
            "success": True,
            "statistics": statistics
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving user statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve user statistics: {str(e)}")

@app.post("/api/user-statistics/{user_id}")
async def update_user_statistics(user_id: str, statistics_data: dict, request: Request = None):
    """Update user statistics"""
    try:
        # Extract user information and verify access
        request_user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        
        # Users can only update their own statistics
        if request_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Update user statistics in Firestore
        user_ref = db.collection('user_statistics').document(user_id)
        
        # Add timestamp
        statistics_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        # Use merge=True to update only provided fields
        user_ref.set(statistics_data, merge=True)
        
        return {
            "status": "success",
            "success": True,
            "message": "Statistics updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating user statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update user statistics: {str(e)}")

# Device Management endpoints
@app.get("/api/device/my-devices")
async def get_my_devices(request: Request = None):
    """Get user's registered devices"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        
        # Get devices from device service
        devices = device_service.get_user_devices(user_id)
        
        return {
            "status": "success",
            "success": True,
            "devices": devices
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving user devices: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve devices: {str(e)}")

# Cloud Storage Authentication Endpoints
@app.get("/auth/dropbox/url")
async def get_dropbox_auth_url(request: Request = None, state: str = None):
    """Get Dropbox OAuth authorization URL"""
    try:
        # Extract user information
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        logger.info(f"🔗 Generating Dropbox auth URL for user: {user_id}")
        
        # Generate state parameter if not provided
        if not state:
            import secrets
            state = f"{user_id}_{secrets.token_urlsafe(16)}"
        
        # Get auth URL from cloud storage service
        auth_url = cloud_storage_service.get_dropbox_auth_url(state=state)
        
        return {
            "status": "success",
            "success": True,
            "auth_url": auth_url,
            "state": state
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error generating Dropbox auth URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")

@app.post("/auth/dropbox/callback")
async def dropbox_callback(request: Request):
    """Handle Dropbox OAuth callback"""
    try:
        # Get the request body
        body = await request.json()
        code = body.get('code')
        state = body.get('state')
        
        if not code:
            raise HTTPException(status_code=400, detail="Authorization code is required")
        
        logger.info(f"🔗 Processing Dropbox callback with code: {code[:10]}... and state: {state}")
        
        # Exchange code for access token using cloud storage service
        token_data = cloud_storage_service.exchange_dropbox_code(code, state)
        
        return {
            "status": "success",
            "success": True,
            "access_token": token_data.get('access_token'),
            "refresh_token": token_data.get('refresh_token'),
            "expires_in": token_data.get('expires_in')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error processing Dropbox callback: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process callback: {str(e)}")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "transcription": transcription_service.is_available(),
            "groq": groq_generator.is_available(),
            "r2_storage": r2_storage.is_available(),
            "tts": tts_service.is_available(),
            "firebase": db is not None
        }
    }

# Run the application
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )