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
import re
from datetime import datetime, timezone

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from affiliate_attribution_middleware import AffiliateAttributionMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, firestore, auth

# Import configuration
from config import *

# Import user-friendly error handling
from user_friendly_errors import get_user_friendly_error, get_context_specific_error, format_validation_error

# Import existing services
from groq_processor import groq_generator
from quiz_generator import quiz_generator
from r2_storage import r2_storage
from pdf_processor import pdf_processor
from payment_service import PaymentService, PaymentResult
from affiliate_service import AffiliateService
from notification_service import NotificationService
from device_service import device_service
from resend_service import resend_service
from credit_service import credit_service
from timestamp_mapper import timestamp_mapper
from tts_service import tts_service
from password_reset_service import password_reset_service
from diagram_generator import diagram_generator
from video_validation_service import video_validation_service
from semantic_search_service import semantic_search_service
from ocr_service import ocr_service

# Email verification OTP endpoints
from email_verification_service import email_verification_service

# Import new utility services
from routes import affiliate_routes
from routes import sira_routes
from transcription_service import transcription_service
from youtube_service import youtube_service
from auth_service import auth_service
from job_manager import job_manager
from file_utils import file_utils
from processing_service import processing_service
from affiliate_recompute_job import start_affiliate_recompute_scheduler, stop_affiliate_recompute_scheduler
from citations_routes import router as citations_router
from collaboration_service import collaboration_service
from invited_member_auth_service import invited_member_auth_service

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

class UpdateBookmarkRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
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

class SemanticSearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 20

class ExplainRequest(BaseModel):
    phrase: str

class CreateWorkspaceRequest(BaseModel):
    name: str
    description: Optional[str] = None

class InviteRequest(BaseModel):
    email: str
    role: str
    workspace_name: Optional[str] = None

class RoleUpdateRequest(BaseModel):
    role: str

class AcceptInvitationRequest(BaseModel):
    invitation_token: str

app = FastAPI(title="Quickmaps Backend", version="1.1.0")

# Add validation exception handler
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

@app.on_event("shutdown")
async def shutdown_event():
    try:
        stop_affiliate_recompute_scheduler(logger)
    except Exception:
        pass

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

# User-friendly HTTPException and generic exception handlers
from fastapi import HTTPException as FastAPIHTTPException

@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    """Return user-friendly messages for HTTP errors while logging technical details."""
    try:
        logger.error(f"HTTPException on {request.method} {request.url}: {exc.detail}")
    except Exception:
        logger.error(f"HTTPException on {request.method} {request.url}")

    status_code = getattr(exc, 'status_code', 500) or 500
    detail = getattr(exc, 'detail', None)

    # Preserve structured details (dict) to avoid breaking clients relying on fields
    if isinstance(detail, dict):
        return JSONResponse(status_code=status_code, content=detail)

    # Map common statuses to friendly messages
    friendly_messages = {
        400: "We couldn't process your request. Please check the information and try again.",
        401: "Please sign in to continue.",
        402: "Your current plan doesn't include this feature. Please upgrade to continue.",
        403: "You don’t have permission to do that.",
        404: "We couldn't find what you're looking for.",
        405: "This action isn't allowed.",
        408: "The request timed out. Please try again.",
        409: "There’s a conflict with your request. Please refresh and try again.",
        413: "This is too large to process. Please try a smaller file.",
        415: "This file type isn’t supported.",
        429: "You’ve reached the current rate limit. Please wait and try again.",
        500: "Something went wrong on our side. Please try again in a moment.",
        502: "The service is temporarily unavailable. Please try again shortly.",
        503: "The service is temporarily unavailable. Please try again shortly.",
        504: "The request took too long. Please try again.",
    }

    message = friendly_messages.get(status_code, "We ran into a problem. Please try again.")
    return JSONResponse(status_code=status_code, content={"detail": message})

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all handler to avoid exposing technical errors to users."""
    logger.error(f"Unhandled error on {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. Please try again in a moment."}
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
    
    # Start periodic affiliate totals recompute scheduler (every 6 hours by default)
    try:
        if db:
            start_affiliate_recompute_scheduler(logger, db, interval_seconds=int(os.getenv('AFFILIATE_RECOMPUTE_INTERVAL_SEC', str(6*60*60))))
            logger.info("🗓️ Affiliate totals recompute scheduler started")
        else:
            logger.warning("Skipping affiliate recompute scheduler: no DB")
    except Exception as e:
        logger.error(f"Failed to start affiliate recompute scheduler: {e}")

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
affiliate_service = AffiliateService(db_client=db)
logger.info("Payment, notification and affiliate services initialized")

# Mount affiliate routes
try:
    affiliate_routes.init(db)
    app.include_router(affiliate_routes.router)
    app.include_router(citations_router)
    app.include_router(sira_routes.router)
    logger.info("Affiliate, citations, and Sira routes mounted")
except Exception as e:
    logger.error(f"Failed to mount affiliate routes: {e}")

# Initialize services with database
credit_service.db = db
device_service.db = db
logger.info("Credit and device services initialized")

# Paddle API Configuration
PADDLE_API_KEY = os.getenv('PADDLE_API_KEY')
PADDLE_ENVIRONMENT = os.getenv('PADDLE_ENVIRONMENT', 'live')
PADDLE_BASE_URL = 'https://api.paddle.com' if PADDLE_ENVIRONMENT in ['live', 'production'] else 'https://sandbox-api.paddle.com'
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
device_service.db = db
logger.info("Credit and device services initialized with Firestore client")
# Initialize collaboration service with Firestore client
try:
    collaboration_service.set_db(db)
    invited_member_auth_service.set_db(db)
    logger.info("Collaboration service initialized")
except Exception as e:
    logger.error(f"Failed to initialize collaboration service: {e}")

# Add CORS middleware
# Ensure quickmaps.pro origins are explicitly allowed so browsers receive proper CORS headers
try:
    configured_origins = CORS_ORIGINS or []
    if isinstance(configured_origins, str):
        configured_origins = [configured_origins]
except Exception:
    configured_origins = []

extra_origins = [
    "https://quickmaps.pro",
    "https://www.quickmaps.pro",
    "https://api.quickmaps.pro",  # Add API subdomain
]

# Add local development origins when not running in production
if os.getenv("ENVIRONMENT", "").lower() not in ("prod", "production", "live"):
    extra_origins += [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

# Always allow extra origins from environment (comma-separated)
extra_from_env = os.getenv("CORS_EXTRA_ORIGINS", "")
if extra_from_env:
    for origin in extra_from_env.split(","):
        origin = origin.strip()
        if origin:
            extra_origins.append(origin)

# When credentials are allowed, wildcard "*" is not permitted by browsers.
# Remove "*" and use explicit origins.
sanitized_origins = [o for o in configured_origins if o != "*"]
allowed_origins = sorted(set(sanitized_origins + extra_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"] if CORS_METHODS == ["*"] else CORS_METHODS,
    allow_headers=["*"] if CORS_HEADERS == ["*"] else CORS_HEADERS,
    expose_headers=["Content-Disposition"],
    max_age=86400,
)

# Log CORS configuration for debugging
logger.info(f"🌐 CORS configured with origins: {allowed_origins}")
logger.info(f"🌐 CORS methods: {CORS_METHODS}")
logger.info(f"🌐 CORS headers: {CORS_HEADERS}")

# Force CORS headers on all responses (including errors) and handle generic preflight
@app.middleware("http")
async def force_cors_headers(request: Request, call_next):
    # Short-circuit preflight if it reaches here
    if request.method == "OPTIONS":
        # Mirror requested headers if provided
        acrh = request.headers.get("Access-Control-Request-Headers", "Authorization,Content-Type,Accept,X-Requested-With")
        origin = request.headers.get("origin")
        # Choose allowed origin
        if origin in allowed_origins:
            allow_origin = origin
        else:
            allow_origin = allowed_origins[0] if allowed_origins else "*"
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": allow_origin,
                "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                "Access-Control-Allow-Headers": acrh,
                "Access-Control-Allow-Credentials": "true",
                "Vary": "Origin",
            }
        )

    # Proceed with normal handling
    response = await call_next(request)
    try:
        origin = request.headers.get("origin")
        if origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            # Preserve exposed headers
            if "Content-Disposition" not in response.headers.get("Access-Control-Expose-Headers", ""):
                response.headers["Access-Control-Expose-Headers"] = (
                    (response.headers.get("Access-Control-Expose-Headers", "") + ",Content-Disposition").strip(",")
                )
            response.headers["Vary"] = "Origin"
        else:
            # Fallback to first allowed if origin missing/unexpected
            if allowed_origins:
                response.headers.setdefault("Access-Control-Allow-Origin", allowed_origins[0])
                response.headers.setdefault("Access-Control-Allow-Credentials", "true")
                response.headers.setdefault("Vary", "Origin")
    except Exception:
        # Ensure at least some CORS headers in worst-case scenarios
        response.headers.setdefault("Access-Control-Allow-Origin", "*")
    return response

# Capture ?ref=... and set cookie
app.add_middleware(AffiliateAttributionMiddleware)

# Create directories for uploads and outputs
for directory in [UPLOAD_DIR, OUTPUT_DIR, TEMP_DIR, STATIC_DIR]:
    directory.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Notion OAuth endpoints
@app.get("/auth/notion/url")
async def get_notion_auth_url(request: Request = None, state: str = None):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        # Build Notion OAuth URL
        NOTION_CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
        NOTION_REDIRECT_URI = os.getenv('NOTION_REDIRECT_URI', 'http://localhost:5173/auth/notion/callback')
        NOTION_SCOPES = os.getenv('NOTION_SCOPES', 'read,write')
        if not NOTION_CLIENT_ID:
            raise HTTPException(status_code=500, detail="Notion is not configured")
        import urllib.parse as up
        params = {
            'client_id': NOTION_CLIENT_ID,
            'response_type': 'code',
            'owner': 'user',
            'redirect_uri': NOTION_REDIRECT_URI,
            'state': state or 'default',
        }
        # Notion scopes are passed in 'scope' param as space-delimited
        params['scope'] = ' '.join([s.strip() for s in NOTION_SCOPES.replace(',', ' ').split() if s.strip()])
        auth_url = f"https://api.notion.com/v1/oauth/authorize?{up.urlencode(params)}"
        return { 'auth_url': auth_url }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating Notion auth URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate Notion auth URL")

@app.post("/auth/notion/callback")
async def notion_callback(request: Request):
    try:
        body = await request.json()
        code = body.get('code')
        state = body.get('state')
        if not code:
            raise HTTPException(status_code=400, detail="Missing code")
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")

        NOTION_CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
        NOTION_CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
        NOTION_REDIRECT_URI = os.getenv('NOTION_REDIRECT_URI', 'http://localhost:5173/auth/notion/callback')
        if not (NOTION_CLIENT_ID and NOTION_CLIENT_SECRET):
            raise HTTPException(status_code=500, detail="Notion is not configured")

        token_url = 'https://api.notion.com/v1/oauth/token'
        payload = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': NOTION_REDIRECT_URI,
        }
        auth = (NOTION_CLIENT_ID, NOTION_CLIENT_SECRET)
        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, json=payload, auth=auth, headers={ 'Content-Type': 'application/json' })
            if resp.status_code != 200:
                logger.error(f"Notion token exchange failed: {resp.status_code} {resp.text}")
                raise HTTPException(status_code=400, detail="Notion authorization failed")
            data = resp.json()
        # Persist in Firestore or temp store
        tokens = {
            'access_token': data.get('access_token'),
            'bot_id': data.get('bot_id'),
            'workspace_id': data.get('workspace_id'),
            'workspace_name': data.get('workspace_name'),
            'duplicated_template_id': data.get('duplicated_template_id'),
            'owner': data.get('owner'),
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        try:
            if db:
                db.collection('user_integrations').document(user_id).set({ 'notion': tokens }, merge=True)
        except Exception as de:
            logger.error(f"Failed to store Notion tokens: {de}")
        return { 'success': True, 'access_token': tokens.get('access_token') }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Notion callback: {e}")
        raise HTTPException(status_code=500, detail="Failed to process Notion callback")

@app.get("/auth/notion/status")
async def notion_status(request: Request):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        if not db:
            return { 'connected': False }
        doc = db.collection('user_integrations').document(user_id).get()
        connected = doc.exists and bool((doc.to_dict() or {}).get('notion', {}).get('access_token'))
        return { 'connected': connected }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Notion status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get Notion status")

@app.post("/auth/notion/disconnect")
async def notion_disconnect(request: Request):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        if db:
            db.collection('user_integrations').document(user_id).set({ 'notion': {} }, merge=True)
        return { 'success': True }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting Notion: {e}")
        raise HTTPException(status_code=500, detail="Failed to disconnect Notion")

# ---------------- Obsidian Integration ----------------
@app.get("/auth/obsidian/status")
async def obsidian_status(request: Request):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        if not db:
            return { 'connected': False }
        doc = db.collection('user_integrations').document(user_id).get()
        data = (doc.to_dict() or {}).get('obsidian', {}) if doc.exists else {}
        connected = bool(data.get('vault_name'))
        return { 'connected': connected, 'config': { 'vault_name': data.get('vault_name'), 'base_folder': data.get('base_folder') } }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Obsidian status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get Obsidian status")

class ObsidianConnectRequest(BaseModel):
    vault_name: str
    base_folder: Optional[str] = None

@app.post("/auth/obsidian/connect")
async def obsidian_connect(req: ObsidianConnectRequest, request: Request):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        cfg = { 'vault_name': (req.vault_name or '').strip(), 'base_folder': (req.base_folder or '').strip() or None }
        if not cfg['vault_name']:
            raise HTTPException(status_code=400, detail="Vault name is required")
        db.collection('user_integrations').document(user_id).set({ 'obsidian': cfg }, merge=True)
        return { 'success': True }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error connecting Obsidian: {e}")
        raise HTTPException(status_code=500, detail="Failed to connect Obsidian")

@app.post("/auth/obsidian/disconnect")
async def obsidian_disconnect(request: Request):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        if db:
            db.collection('user_integrations').document(user_id).set({ 'obsidian': {} }, merge=True)
        return { 'success': True }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting Obsidian: {e}")
        raise HTTPException(status_code=500, detail="Failed to disconnect Obsidian")

@app.post("/api/obsidian/pages")
async def create_obsidian_note(req: dict, request: Request = None):
    """Build an obsidian://new URI to create a note in the user's vault.
    Falls back with markdown if too large for URI schemes.
    """
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        # Load stored config
        doc = db.collection('user_integrations').document(user_id).get()
        data = (doc.to_dict() or {}).get('obsidian', {}) if doc.exists else {}
        vault = (req.get('vault_name') or data.get('vault_name') or os.getenv('OBSIDIAN_DEFAULT_VAULT_NAME') or '').strip()
        base_folder = (req.get('base_folder') or data.get('base_folder') or os.getenv('OBSIDIAN_DEFAULT_BASE_FOLDER') or '').strip()
        if not vault:
            raise HTTPException(status_code=400, detail="Obsidian is not connected (vault name missing)")

        # Prepare file name and content
        raw_title = (req.get('title') or '').strip() or 'QuickMaps Note'
        content = (req.get('content') or '').strip()
        file_override = (req.get('file') or '').strip()

        # Sanitize filename
        safe = re.sub(r"[\\/:*?\"<>|]", "-", raw_title).strip()
        safe = re.sub(r"\s+", " ", safe).strip()
        filename = file_override or f"{safe}.md"
        rel_path = f"{base_folder}/{filename}" if base_folder else filename

        # Build obsidian URI
        try:
            import urllib.parse as up
            uri = f"obsidian://new?vault={up.quote(vault)}&file={up.quote(rel_path)}&content={up.quote(content)}"
        except Exception:
            # Minimal fallback without encoding (not recommended)
            uri = f"obsidian://new?vault={vault}&file={rel_path}&content={content}"

        too_large = len(uri) > 1800
        result = { 'success': True, 'obsidian_uri': (None if too_large else uri), 'too_large_for_uri': too_large, 'filename': rel_path }
        if too_large:
            result['markdown'] = content
            result['message'] = 'Content too large for obsidian:// URI. Use the returned markdown to save into your vault.'
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating Obsidian note: {e}")
        raise HTTPException(status_code=500, detail="Failed to create Obsidian note")

# Create a new Notion page (top-level in workspace)
@app.post("/api/notion/pages")
async def create_notion_page(req: dict, request: Request = None):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        if not db:
            raise HTTPException(status_code=500, detail="Database not available")
        # Read user's Notion token
        doc = db.collection('user_integrations').document(user_id).get()
        if not doc.exists:
            raise HTTPException(status_code=400, detail="Notion is not connected")
        notion_data = (doc.to_dict() or {}).get('notion', {})
        access_token = notion_data.get('access_token')
        if not access_token:
            raise HTTPException(status_code=400, detail="Notion is not connected")

        title = (req.get('title') or '').strip() or 'QuickMaps Page'
        content = (req.get('content') or '').strip()
        chunks = req.get('chunks') if isinstance(req.get('chunks'), list) else None
        content_format = (req.get('content_format') or '').strip().lower() or 'markdown'

        # Helpers to build Notion blocks safely
        MAX_RT = 1900  # keep under 2000 to be safe

        def split_rich_text(text: str):
            parts = []
            s = (text or '')
            while len(s) > MAX_RT:
                cut = s.rfind(' ', 0, MAX_RT)
                if cut < int(MAX_RT * 0.6):
                    cut = MAX_RT
                parts.append(s[:cut].strip())
                s = s[cut:].strip()
            if s:
                parts.append(s)
            # Map to Notion rich_text objects
            return [
                {"type": "text", "text": {"content": p}}
                for p in parts if p is not None
            ]

        def make_paragraph(text: str):
            return {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": split_rich_text(text)}
            }

        def make_heading(text: str, level: int):
            level = max(1, min(3, level))
            key = f"heading_{level}"
            return {
                "object": "block",
                "type": key,
                key: {"rich_text": split_rich_text(text)}
            }

        def make_bullet(text: str):
            return {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": split_rich_text(text)}
            }

        def make_numbered(text: str):
            return {
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": split_rich_text(text)}
            }

        def parse_markdown_lines_to_blocks(lines: list[str]):
            blocks = []
            for raw in lines:
                line = raw or ''
                if not line.strip():
                    blocks.append(make_paragraph(""))
                    continue
                m_h = re.match(r"^\s*(#{1,3})\s+(.*)$", line)
                if m_h:
                    blocks.append(make_heading(m_h.group(2).strip(), len(m_h.group(1))))
                    continue
                m_b = re.match(r"^\s*([\-\*\u2022])\s+(.*)$", line)
                if m_b:
                    blocks.append(make_bullet(m_b.group(2).strip()))
                    continue
                m_n = re.match(r"^\s*\d+[\.)]\s+(.*)$", line)
                if m_n:
                    blocks.append(make_numbered(m_n.group(1).strip()))
                    continue
                blocks.append(make_paragraph(line))
            return blocks

        # Build children blocks
        children = []
        if chunks and len(chunks) > 0:
            # Consume provided chunks (already safe-sized by frontend)
            # Treat empty strings as paragraph breaks
            children = parse_markdown_lines_to_blocks(chunks)
        elif content:
            # Split content into paragraphs and lines, then map
            paragraphs = re.split(r"\n{2,}", content)
            lines = []
            for p in paragraphs:
                p = p or ''
                if not p.strip():
                    lines.append("")
                    continue
                for l in p.split("\n"):
                    l = l.rstrip()
                    # Normalize bullets a bit
                    l = re.sub(r"^\s*[\-\*\u2022]\s+", "- ", l)
                    lines.append(l)
                lines.append("")  # blank line between paragraphs
            children = parse_markdown_lines_to_blocks(lines)

        payload = {
            "parent": {"type": "workspace", "workspace": True},
            "properties": {
                "title": {
                    "title": [
                        {"type": "text", "text": {"content": title}}
                    ]
                }
            }
        }
        if children:
            payload["children"] = children

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post("https://api.notion.com/v1/pages", headers=headers, json=payload)
        if resp.status_code not in (200, 201):
            logger.error(f"Notion page create failed: {resp.status_code} {resp.text}")
            raise HTTPException(status_code=400, detail="Failed to create Notion page")
        data = resp.json()
        return {"success": True, "page_id": data.get('id'), "url": data.get('url')}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating Notion page: {e}")
        raise HTTPException(status_code=500, detail="Failed to create Notion page")

# Health check endpoint for CORS debugging
@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "cors_origins": allowed_origins
    }

# OPTIONS handler for preflight requests
@app.options("/{path:path}")
async def options_handler(path: str):
    """Handle preflight OPTIONS requests"""
    return {"message": "OK"}

# ---------------------- Device Management Endpoints ----------------------

@app.post("/api/device/register")
async def register_device_endpoint(request: Request):
    try:
        # Require auth
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")

        # Parse body (tolerant of empty/invalid JSON)
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}

        # Extract network and client hints
        try:
            xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
            client_ip = (xff.split(",")[0].strip() if xff else (request.client.host if request.client else "Unknown"))
        except Exception:
            client_ip = "Unknown"
        user_agent = request.headers.get("user-agent", "")

        # Build device request data for fingerprinting
        req_data = dict(payload or {})
        req_data.update({
            "ip_address": client_ip,
            "user_agent": user_agent,
        })

        is_new, device_info = device_service.register_device(user_id, req_data)
        if not device_info:
            raise HTTPException(status_code=500, detail="Failed to register device")

        return {"success": True, "is_new": is_new, "device": device_info}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering device: {e}")
        raise HTTPException(status_code=500, detail="Failed to register device")

@app.delete("/api/device/{device_id}")
async def delete_device_endpoint(device_id: str, request: Request = None):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")

        success, device = device_service.remove_device(user_id, device_id)
        if not success:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"success": True, "device": device}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing device: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove device")

# ---------------------- Collaboration Endpoints ----------------------

# Invited Member Authentication
@app.post("/api/invited-members/auth")
async def authenticate_invited_member_endpoint(req: dict):
    try:
        email = req.get('email')
        password = req.get('password')
        
        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password are required")
            
        result = await collaboration_service.authenticate_invited_member(email=email, password=password)
        if not result.get('success'):
            raise HTTPException(status_code=401, detail=result.get('error', 'Authentication failed'))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error authenticating invited member: {e}")
        raise HTTPException(status_code=500, detail="Failed to authenticate invited member")

@app.get("/api/invited-members/session/{session_id}")
async def get_invited_member_session_endpoint(session_id: str):
    try:
        result = await collaboration_service.get_invited_member_session(session_id=session_id)
        if not result.get('success'):
            raise HTTPException(status_code=404, detail=result.get('error', 'Session not found'))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting invited member session: {e}")
        raise HTTPException(status_code=500, detail="Failed to get invited member session")

@app.post("/api/workspaces")
async def create_workspace_endpoint(req: CreateWorkspaceRequest, request: Request = None):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        result = await collaboration_service.create_workspace(owner_id=user_id, name=req.name, description=req.description or "")
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to create workspace'))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating workspace: {e}")
        raise HTTPException(status_code=500, detail="Failed to create workspace")

@app.get("/api/workspaces")
async def get_user_workspaces_endpoint(request: Request = None):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        result = await collaboration_service.get_user_workspaces(user_id=user_id)
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to fetch workspaces'))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workspaces: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch workspaces")

@app.get("/api/workspaces/{workspace_id}")
async def get_workspace_details_endpoint(workspace_id: str, request: Request = None):
    try:
        # Try Firebase user first
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if user_id:
            result = await collaboration_service.get_workspace_details(workspace_id=workspace_id, user_id=user_id)
            if result.get('success'):
                return result
            # If user lacks access, attempt invited-member fallback before erroring
            err_msg = (result.get('error') or '')
            err_lower = err_msg.lower()
            if 'access' in err_lower or 'permission' in err_lower:
                session_id, invited_email, invited_ws_id, invited_role = await invited_member_auth_service.get_invited_member_info_from_request(request)
                if session_id and invited_ws_id == workspace_id:
                    try:
                        doc = db.collection('workspaces').document(workspace_id).get()
                        if not doc.exists:
                            raise HTTPException(status_code=404, detail="Workspace not found")
                        w = doc.to_dict() or {}
                        sanitized = {
                            'id': w.get('id') or workspace_id,
                            'name': w.get('name', 'Untitled Workspace'),
                            'description': w.get('description', ''),
                            'owner_id': w.get('owner_id'),
                            'user_role': invited_role or 'view',
                            'user_status': 'active',
                        }
                        return { 'success': True, 'workspace': sanitized }
                    except HTTPException:
                        raise
                    except Exception as e:
                        logger.error(f"Invited member workspace details error: {e}")
                        raise HTTPException(status_code=500, detail="Failed to fetch workspace details")
            # Otherwise propagate not found or generic error
            if 'not found' in err_lower:
                raise HTTPException(status_code=404, detail=err_msg or 'Workspace not found')
            raise HTTPException(status_code=400, detail=err_msg or 'Failed to fetch workspace details')

        # Fallback to invited member session
        session_id, invited_email, invited_ws_id, invited_role = await invited_member_auth_service.get_invited_member_info_from_request(request)
        if session_id and invited_ws_id == workspace_id:
            # Build a minimal workspace view for invited members (view-only)
            try:
                doc = db.collection('workspaces').document(workspace_id).get()
                if not doc.exists:
                    raise HTTPException(status_code=404, detail="Workspace not found")
                w = doc.to_dict() or {}
                # Remove sensitive membership details for invited views
                sanitized = {
                    'id': w.get('id') or workspace_id,
                    'name': w.get('name', 'Untitled Workspace'),
                    'description': w.get('description', ''),
                    'owner_id': w.get('owner_id'),
                    'user_role': invited_role or 'view',
                    'user_status': 'active',
                }
                return { 'success': True, 'workspace': sanitized }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Invited member workspace details error: {e}")
                raise HTTPException(status_code=500, detail="Failed to fetch workspace details")

        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workspace details: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch workspace details")

@app.post("/api/workspaces/{workspace_id}/invite")
async def invite_collaborator_endpoint(workspace_id: str, req: InviteRequest, request: Request = None):
    try:
        logger.info(f"🔍 Inviting collaborator: workspace={workspace_id}, email={req.email}, role={req.role}")
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        
        logger.info(f"✅ User authenticated: {user_id}")
        result = await collaboration_service.invite_collaborator(
            workspace_id=workspace_id,
            inviter_id=user_id,
            email=req.email,
            role=req.role,
            workspace_name=req.workspace_name
        )
        
        logger.info(f"📧 Invitation result: {result}")
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to send invitation'))
        
        logger.info(f"✅ Invitation successful for {req.email}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error inviting collaborator: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to send invitation")

@app.post("/api/invitations/accept")
async def accept_invitation_endpoint(req: AcceptInvitationRequest, request: Request = None):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id or not user_email:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        result = await collaboration_service.accept_invitation(user_id=user_id, user_email=user_email, invitation_token=req.invitation_token)
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to accept invitation'))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting invitation: {e}")
        raise HTTPException(status_code=500, detail="Failed to accept invitation")

@app.put("/api/workspaces/{workspace_id}/collaborators/{member_id}/role")
async def update_collaborator_role_endpoint(workspace_id: str, member_id: str, req: RoleUpdateRequest, request: Request = None):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        result = await collaboration_service.update_collaborator_role(workspace_id=workspace_id, updater_id=user_id, collaborator_id=member_id, new_role=req.role)
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to update role'))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating collaborator role: {e}")
        raise HTTPException(status_code=500, detail="Failed to update role")

@app.put("/api/workspaces/{workspace_id}/collaborators/{member_id}/ban")
async def ban_collaborator_endpoint(workspace_id: str, member_id: str, request: Request = None):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        result = await collaboration_service.ban_collaborator(workspace_id=workspace_id, updater_id=user_id, collaborator_id=member_id)
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to ban collaborator'))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error banning collaborator: {e}")
        raise HTTPException(status_code=500, detail="Failed to ban collaborator")

@app.put("/api/workspaces/{workspace_id}/collaborators/{member_id}/unban")
async def unban_collaborator_endpoint(workspace_id: str, member_id: str, request: Request = None):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        result = await collaboration_service.unban_collaborator(workspace_id=workspace_id, updater_id=user_id, collaborator_id=member_id)
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to unban collaborator'))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unbanning collaborator: {e}")
        raise HTTPException(status_code=500, detail="Failed to unban collaborator")

@app.delete("/api/workspaces/{workspace_id}/collaborators/{member_id}")
async def remove_collaborator_endpoint(workspace_id: str, member_id: str, request: Request = None):
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Please sign in to continue.")
        result = await collaboration_service.remove_collaborator(workspace_id=workspace_id, remover_id=user_id, collaborator_id=member_id)
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to remove collaborator'))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing collaborator: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove collaborator")

@app.get("/api/workspaces/{workspace_id}/saved-notes")
async def get_workspace_saved_notes(workspace_id: str, limit: int = 100, request: Request = None):
    """Allow workspace members or invited viewers to view owner's saved notes."""
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if user_id:
            details = await collaboration_service.get_workspace_details(workspace_id=workspace_id, user_id=user_id)
            if not details.get('success'):
                raise HTTPException(status_code=404, detail=details.get('error', 'Workspace not found'))
            workspace = details.get('workspace') or {}
            has_view = await collaboration_service.check_user_permission(workspace_id=workspace_id, user_id=user_id, required_permission='view')
            if not has_view:
                raise HTTPException(status_code=403, detail="You don’t have permission to view this workspace's notes.")
        else:
            # Invited member path
            session_id, invited_email, invited_ws_id, invited_role = await invited_member_auth_service.get_invited_member_info_from_request(request)
            if not session_id or invited_ws_id != workspace_id:
                raise HTTPException(status_code=401, detail="Please sign in to continue.")
            # Fetch workspace for owner id
            doc = db.collection('workspaces').document(workspace_id).get()
            if not doc.exists:
                raise HTTPException(status_code=404, detail="Workspace not found")
            workspace = doc.to_dict() or {}
        owner_id = workspace.get('owner_id')
        if not owner_id:
            raise HTTPException(status_code=400, detail="Workspace owner not set")
        notes = r2_storage.get_user_saved_notes(user_id=owner_id, limit=limit)
        return {"success": True, "notes": notes, "count": len(notes), "owner_id": owner_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workspace saved notes: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch saved notes")

@app.get("/api/workspaces/{workspace_id}/bookmarks")
async def get_workspace_bookmarks(workspace_id: str, limit: int = 100, request: Request = None):
    """Allow workspace members or invited viewers to view owner's bookmarks."""
    try:
        user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
        if user_id:
            details = await collaboration_service.get_workspace_details(workspace_id=workspace_id, user_id=user_id)
            if not details.get('success'):
                raise HTTPException(status_code=404, detail=details.get('error', 'Workspace not found'))
            workspace = details.get('workspace') or {}
            has_view = await collaboration_service.check_user_permission(workspace_id=workspace_id, user_id=user_id, required_permission='view')
            if not has_view:
                raise HTTPException(status_code=403, detail="You don’t have permission to view this workspace's bookmarks.")
        else:
            session_id, invited_email, invited_ws_id, invited_role = await invited_member_auth_service.get_invited_member_info_from_request(request)
            if not session_id or invited_ws_id != workspace_id:
                raise HTTPException(status_code=401, detail="Please sign in to continue.")
            doc = db.collection('workspaces').document(workspace_id).get()
            if not doc.exists:
                raise HTTPException(status_code=404, detail="Workspace not found")
            workspace = doc.to_dict() or {}
        owner_id = workspace.get('owner_id')
        if not owner_id:
            raise HTTPException(status_code=400, detail="Workspace owner not set")
        bookmarks = r2_storage.get_user_bookmarks(user_id=owner_id, limit=limit)
        return {"success": True, "bookmarks": bookmarks, "count": len(bookmarks), "owner_id": owner_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching workspace bookmarks: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch bookmarks")
# --------------------------------------------------------------------


# Email verification OTP endpoints
class SendOtpRequest(BaseModel):
    email: str
    name: Optional[str] = None

class VerifyOtpRequest(BaseModel):
    email: str
    otp: str

@app.post("/api/auth/send-email-otp")
async def send_email_otp(req: SendOtpRequest):
    try:
        email = (req.email or "").strip().lower()
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        result = email_verification_service.create_and_send(email=email, name=req.name)
        if not result.get('success'):
            err = result.get('error', 'EMAIL_FAILED')
            status = 429 if err == 'RESEND_COOLDOWN' else 400
            return JSONResponse(status_code=status, content={"success": False, "error": err, "detail": result.get('message')})
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending OTP: {e}")
        raise HTTPException(status_code=500, detail="Failed to send verification code")

@app.post("/api/auth/verify-email-otp")
async def verify_email_otp(req: VerifyOtpRequest):
    try:
        email = (req.email or "").strip().lower()
        code = (req.otp or "").strip()
        if not email or not code:
            raise HTTPException(status_code=400, detail="Email and code are required")
        result = email_verification_service.verify(email=email, code=code)
        if not result.get('success'):
            err = result.get('error', 'INVALID_CODE')
            # Invalid attempts -> 400, cooldown-like/attempts -> 429
            status = 429 if err in ('TOO_MANY_ATTEMPTS',) else 400
            return JSONResponse(status_code=status, content={"success": False, "error": err, "detail": result.get('message')})
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying OTP: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify code")

# Basic endpoints
@app.get("/")
async def root():
    return {"message": "Video Transcription API is running", "status": "ok", "version": "1.0.0"}

@app.get("/api/")
async def api_root():
    return {"message": "Video Transcription API", "version": "1.0.0"}

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
        logger.error(f"YouTube download failed: {e}")
        raise HTTPException(status_code=500, detail="We're having trouble downloading this YouTube video. Please check the URL and try again.")

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
        logger.error(f"TED Talk download failed: {e}")
        raise HTTPException(status_code=500, detail="We're having trouble downloading this TED Talk. Please check the URL and try again.")


# Udemy course URL endpoint
@app.post("/process-udemy-url/")
async def process_udemy_url(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    request: Request = None,
    cookies_file: UploadFile | None = File(None),
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
        # Optionally save cookies.txt if provided
        cookies_path = None
        try:
            if cookies_file and cookies_file.filename:
                cookies_dest = UPLOAD_DIR / f"{job_id}_cookies.txt"
                import shutil as _shutil
                with open(cookies_dest, "wb") as _out:
                    _shutil.copyfileobj(cookies_file.file, _out)
                cookies_path = str(cookies_dest)
                logger.info(f"Saved cookies file for job {job_id} to {cookies_path}")
        except Exception as ce:
            logger.warning(f"Failed to save cookies file for job {job_id}: {ce}")
            cookies_path = None

        # Set job to processing status before starting background task
        job_manager.update_job_status(job_id, "processing", "Starting Udemy course download...")
        
        # Start background download and transcription using the same processing service
        background_tasks.add_task(processing_service.process_youtube_url, job_id, url, user_id, cookies_path)
        
        return {"job_id": job_id, "message": "Udemy course download started. Transcription will follow."}
    
    except Exception as e:
        job_manager.set_job_error(job_id, str(e))
        logger.error(f"Udemy course download failed: {e}")
        raise HTTPException(status_code=500, detail="We're having trouble downloading this Udemy course. Please check the URL and try again.")

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
        raise HTTPException(status_code=400, detail=get_user_friendly_error("INVALID_FILE_TYPE", "upload"))
    
    # Check file size (limit to 50MB for PDFs)
    if file.size and file.size > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail=get_context_specific_error("FILE_TOO_LARGE", "upload"))
    
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
        logger.error(f"PDF upload failed: {e}")
        raise HTTPException(status_code=500, detail=get_context_specific_error("UPLOAD_FAILED", "upload"))

# Video upload endpoint
@app.post("/upload-video/")
async def upload_video(
    background_tasks: BackgroundTasks,
    video_file: UploadFile = File(...),
    request: Request = None,
):
    """Handle video file upload and processing with plan-based duration validation"""
    # Validate file type
    allowed_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v']
    file_extension = Path(video_file.filename).suffix.lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Please upload a video file with one of these extensions: {', '.join(allowed_extensions)}"
        )

    # Check file size (soft check; UploadFile may not provide size)
    if hasattr(video_file, 'size') and video_file.size and video_file.size > 1024 * 1024 * 1024:  # 1GB
        raise HTTPException(
            status_code=400,
            detail="Video file is too large. Please upload a file smaller than 1GB."
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
        file_path = UPLOAD_DIR / f"{job_id}_{video_file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(video_file.file, buffer)

        # Server-side duration validation against plan
        try:
            # Determine user's plan from Firestore
            user_plan = video_validation_service.get_user_plan_from_firestore(db, user_id) if user_id else 'free'
            validation = video_validation_service.validate_video_duration(str(file_path), user_plan, user_id)
            if not validation.is_valid:
                # Cleanup and return plan-limited error
                try:
                    if file_path.exists():
                        file_path.unlink(missing_ok=True)  # type: ignore
                except Exception:
                    pass
                # Build suggestion if available
                suggestion = video_validation_service.get_plan_upgrade_suggestion(validation.user_plan, validation.duration_minutes or 0)
                raise HTTPException(
                    status_code=402,
                    detail={
                        "detail": validation.message,
                        "currentPlan": validation.user_plan,
                        "allowedMinutes": validation.allowed_minutes,
                        "durationMinutes": validation.duration_minutes,
                        "suggestion": suggestion,
                    }
                )
        except HTTPException:
            # Propagate plan limit error
            raise
        except Exception as ve:
            logger.error(f"Video validation failed: {ve}")
            # Non-fatal; proceed but warn user gracefully

        # Set job to processing status before starting background task
        job_manager.update_job_status(job_id, "processing", "Starting video processing...")

        # Start background processing using the same pipeline
        background_tasks.add_task(processing_service.process_video_file, job_id, str(file_path), user_id)

        return {"job_id": job_id, "message": "Video uploaded successfully. Processing started."}

    except HTTPException:
        job_manager.set_job_error(job_id, "Video upload failed due to plan limits or validation error")
        raise
    except Exception as e:
        job_manager.set_job_error(job_id, str(e))
        logger.error(f"Video upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload video file. Please try again.")

# Audio upload endpoint (rebuilt; handles CORS preflight explicitly)

def _cors_headers_for_request(request: Request) -> dict:
    try:
        req_origin = request.headers.get("origin")
        if req_origin in allowed_origins:
            return {
                "Access-Control-Allow-Origin": req_origin,
                "Access-Control-Allow-Credentials": "true",
                "Vary": "Origin"
            }
    except Exception:
        pass
    # Fallback: first allowed or wildcard
    hdr = {"Access-Control-Allow-Credentials": "true", "Vary": "Origin"}
    try:
        if allowed_origins:
            hdr["Access-Control-Allow-Origin"] = allowed_origins[0]
        else:
            hdr["Access-Control-Allow-Origin"] = "*"
    except Exception:
        hdr["Access-Control-Allow-Origin"] = "*"
    return hdr


def _preflight_headers(request: Request) -> dict:
    base = _cors_headers_for_request(request)
    base.update({
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "Access-Control-Allow-Headers": request.headers.get(
            "Access-Control-Request-Headers",
            "Authorization,Content-Type,Accept,X-Requested-With"
        ),
    })
    return base


@app.api_route("/upload-audio", methods=["POST", "OPTIONS"])
@app.api_route("/upload-audio/", methods=["POST", "OPTIONS"])
async def upload_audio(
    request: Request,
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(None),
):
    # Handle preflight explicitly
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=_preflight_headers(request))

    """Handle audio file upload and processing"""
    if audio_file is None:
        return JSONResponse(
            status_code=400,
            content={"detail": "No audio file provided"},
            headers=_cors_headers_for_request(request)
        )

    # Validate file type/size
    allowed_extensions = ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.webm']
    file_extension = Path(audio_file.filename).suffix.lower()
    if file_extension not in allowed_extensions:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Invalid file type. Please upload an audio file with one of these extensions: {', '.join(allowed_extensions)}"},
            headers=_cors_headers_for_request(request)
        )

    if audio_file.size and audio_file.size > 500 * 1024 * 1024:
        return JSONResponse(
            status_code=400,
            content={"detail": "Audio file is too large. Please upload a file smaller than 500MB."},
            headers=_cors_headers_for_request(request)
        )

    # Extract user information
    user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)

    # Only check if user has credits (don't deduct yet)
    if user_id and db:
        from credit_service import CreditAction
        credit_result = await credit_service.check_credits(
            user_id=user_id,
            action=CreditAction.VIDEO_UPLOAD
        )
        if not credit_result.has_credits:
            return JSONResponse(
                status_code=402,
                content={"detail": f"Insufficient credits. {credit_result.message}"},
                headers=_cors_headers_for_request(request)
            )

    # Create job
    job_id = job_manager.create_job(
        user_id=user_id,
        user_email=user_email,
        user_name=user_name,
        action_type="AUDIO_UPLOAD"
    )

    try:
        # Upload to R2 as temporary media
        if not r2_storage.is_available():
            raise Exception("Storage is not available for uploads")
        r2_key = r2_storage.upload_temp_media(job_id, audio_file.filename, audio_file.file, audio_file.content_type or 'application/octet-stream')
        if not r2_key:
            raise Exception("Failed to store the uploaded audio in storage")

        # Set job to processing status before starting background task
        job_manager.update_job_status(job_id, "processing", "Starting audio processing...")

        # Start background processing from R2 (uses same pipeline under the hood)
        background_tasks.add_task(processing_service.process_audio_from_r2, job_id, r2_key, user_id)

        return JSONResponse(
            status_code=200,
            content={"job_id": job_id, "message": "Audio uploaded successfully. Processing started."},
            headers=_cors_headers_for_request(request)
        )
    except Exception as e:
        job_manager.set_job_error(job_id, str(e))
        logger.error(f"Audio upload failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Failed to upload audio file. Please try again."},
            headers=_cors_headers_for_request(request)
        )

# Page scan endpoint
@app.post("/process-page-scan/")
async def process_page_scan(
    background_tasks: BackgroundTasks,
    images: list[UploadFile] = File(...),
    request: Request = None,
):
    """Handle multiple image upload for page scanning and OCR processing"""
    
    # Validate number of images
    if len(images) == 0:
        raise HTTPException(status_code=400, detail="No images provided. Please upload at least one image.")
    
    if len(images) > 20:
        raise HTTPException(status_code=400, detail="Too many images. Please upload no more than 20 images at once.")
    
    # Validate each image
    supported_formats = ocr_service.get_supported_formats()
    max_size = 10 * 1024 * 1024  # 10MB per image
    
    for i, image in enumerate(images):
        # Check file extension
        file_extension = Path(image.filename).suffix.lower()
        if file_extension not in supported_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Image {i+1} ({image.filename}) has unsupported format. Supported formats: {', '.join(supported_formats)}"
            )
        
        # Check file size
        if image.size and image.size > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"Image {i+1} ({image.filename}) is too large. Please upload images smaller than 10MB."
            )
        
        # Verify it's actually an image
        if not image.content_type or not image.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail=f"File {i+1} ({image.filename}) is not a valid image file."
            )
    
    # Extract user information from Firebase token
    user_id, user_email, user_name = await auth_service.get_user_info_from_request(request)
    
    # Only check if user has credits (don't deduct yet)
    if user_id and db:
        from credit_service import CreditAction
        credit_result = await credit_service.check_credits(
            user_id=user_id,
            action=CreditAction.PDF_UPLOAD  # Use PDF_UPLOAD action for page scanning
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
        action_type="PAGE_SCAN"
    )
    
    try:
        # Save uploaded images temporarily
        image_paths = []
        for i, image in enumerate(images):
            # Create unique filename for each image
            file_extension = Path(image.filename).suffix.lower()
            safe_filename = f"{job_id}_page_{i+1:03d}{file_extension}"
            file_path = UPLOAD_DIR / safe_filename
            
            # Save image
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(image.file, buffer)
            
            image_paths.append(str(file_path))
        
        # Set job to processing status before starting background task
        job_manager.update_job_status(job_id, "processing", f"Starting OCR processing for {len(images)} images...")
        
        # Start background processing
        background_tasks.add_task(processing_service.process_page_scan, job_id, image_paths, user_id)
        
        return {
            "job_id": job_id, 
            "message": f"Successfully uploaded {len(images)} images. OCR processing started.",
            "image_count": len(images)
        }
    
    except Exception as e:
        job_manager.set_job_error(job_id, str(e))
        logger.error(f"Page scan upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload images for page scanning. Please try again.")

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
    
    # Credits are already deducted during processing, no need to deduct again
    # This endpoint is just for claiming/accessing already processed notes
    
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

# Explain phrase endpoint (Groq - Llama 3.1 8B Instant)
@app.post("/api/explain-phrase")
async def explain_phrase_endpoint(req: ExplainRequest):
    try:
        if not groq_generator.is_available():
            raise HTTPException(status_code=503, detail="Explanation service is not available. Please check AI configuration.")
        
        phrase = (req.phrase or "").strip()
        if not phrase:
            raise HTTPException(status_code=400, detail="Phrase is required")
        
        # Limit phrase length to reasonable amount to prevent abuse
        if len(phrase) > 500:
            phrase = phrase[:500]
        
        # Custom prompt as requested
        prompt = f"Can you generate more detailed explanation about this phrase: ({phrase})"
        
        try:
            response = groq_generator.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a helpful educational assistant that explains concepts clearly and concisely."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=600,
                top_p=0.9
            )
            explanation = response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq API error (explain-phrase): {e}")
            raise HTTPException(status_code=502, detail="Failed to generate explanation. Please try again.")
        
        return {"success": True, "explanation": explanation}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in explain-phrase: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate explanation")

# Define phrase endpoint (Groq - Llama 3.1 8B Instant)
@app.post("/api/define-phrase")
async def define_phrase_endpoint(req: ExplainRequest):
    try:
        if not groq_generator.is_available():
            raise HTTPException(status_code=503, detail="Definition service is not available. Please check AI configuration.")

        phrase = (req.phrase or "").strip()
        if not phrase:
            raise HTTPException(status_code=400, detail="Phrase is required")

        # Limit length to prevent abuse
        if len(phrase) > 500:
            phrase = phrase[:500]

        # Structured, compact definition prompt
        prompt = (
            f"You are an expert educator. Provide a concise, plain-language definition for the term "
            f"\"{phrase}\". Then list synonyms and common confusions in a compact format.\n\n"
            f"Output format (no preface):\n"
            f"Definition: <2-3 sentences, simple language>\n"
            f"Synonyms: <up to 5 synonyms, comma-separated>\n"
            f"Common confusions:\n"
            f"- <Term 1>: <one-line distinction>\n"
            f"- <Term 2>: <one-line distinction>\n"
            f"(Include 1-3 items if relevant)"
        )

        try:
            response = groq_generator.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You explain concepts clearly, briefly, and accurately for students."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=600,
                top_p=0.9
            )
            definition = response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq API error (define-phrase): {e}")
            raise HTTPException(status_code=502, detail="Failed to generate definition. Please try again.")

        return {"success": True, "definition": definition}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in define-phrase: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate definition")

# Examples for phrase endpoint (Groq - Llama 3.1 8B Instant)
@app.post("/api/examples-phrase")
async def examples_phrase_endpoint(req: ExplainRequest):
    try:
        if not groq_generator.is_available():
            raise HTTPException(status_code=503, detail="Examples service is not available. Please check AI configuration.")

        phrase = (req.phrase or "").strip()
        if not phrase:
            raise HTTPException(status_code=400, detail="Phrase is required")

        if len(phrase) > 500:
            phrase = phrase[:500]

        prompt = (
            f"Provide 1–3 concrete, domain-relevant examples for the term \"{phrase}\".\n"
            f"Make each example concise and specific.\n\n"
            f"Output format (no preface):\n"
            f"1) <Short label/title> — <1–2 sentence example>\n"
            f"2) <Short label/title> — <1–2 sentence example>\n"
            f"3) <Short label/title> — <1–2 sentence example>\n"
            f"(Include 1–3 items depending on relevance)"
        )

        try:
            response = groq_generator.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You produce clear, concise, and relevant examples for learners."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.35,
                max_tokens=600,
                top_p=0.9
            )
            examples = response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq API error (examples-phrase): {e}")
            raise HTTPException(status_code=502, detail="Failed to generate examples. Please try again.")

        return {"success": True, "examples": examples}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in examples-phrase: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate examples")

# Translation endpoints (supports UI fallbacks: JSON POST, GET with query, form-encoded; multiple route names)
from fastapi import Body

# Style rewrite endpoints (supports JSON POST, GET with query, and form-encoded)
async def _parse_style_params(request: Request) -> dict:
    """Parse style rewrite parameters from JSON, form or query with flexible aliases."""
    data = {}
    form = None
    try:
        data = await request.json()
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    try:
        form = await request.form()
    except Exception:
        form = None
    query = dict(request.query_params or {})

    def pick(*keys, default=None):
        for k in keys:
            if k in data and data[k] not in (None, ""):
                return data[k]
            if form is not None and k in form and form[k] not in (None, ""):
                return form.get(k)
            if k in query and query[k] not in (None, ""):
                return query.get(k)
        return default

    text = pick('text', 'phrase', 'selection', default="")
    style_raw = pick('style', 'tone', 'target_style', default='lecture_notes')
    model_id = pick('model_id', 'model', default=os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant'))

    # Normalize style
    style_map = {
        'lecture_notes': 'lecture_notes',
        'lecture': 'lecture_notes',
        'notes': 'lecture_notes',
        'cheat_sheet': 'cheat_sheet',
        'cheatsheet': 'cheat_sheet',
        'cheat': 'cheat_sheet',
        'exam_answer': 'exam_answer',
        'exam': 'exam_answer',
        'answer': 'exam_answer',
    }
    style = style_map.get(str(style_raw or '').strip().lower(), 'lecture_notes')

    return {
        'text': str(text or "").strip(),
        'style': style,
        'model_id': model_id,
    }

async def _style_rewrite_with_groq(text: str, style: str, model_id: str) -> dict:
    """Use Groq LLM to rewrite text into the requested style and return compact Markdown."""
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    if not groq_generator.is_available():
        # Fallback: echo text in minimal wrapper
        return {
            'success': True,
            'style': style,
            'content': text,
        }

    # Style-specific instructions
    style_instructions = {
        'lecture_notes': (
            "Rewrite the input as compact lecture notes with clear headings and sub-bullets. "
            "Use concise phrasing, keep sections short, and avoid fluff. Output Markdown only."
        ),
        'cheat_sheet': (
            "Rewrite the input as a one-page cheat sheet. Use bullet points, short formulas, and key takeaways. "
            "Highlight critical terms with bold. Avoid long paragraphs. Output Markdown only."
        ),
        'exam_answer': (
            "Rewrite the input as a structured exam answer with brief intro, key arguments, and short conclusion. "
            "Be precise, avoid informal language, and keep it concise. Output Markdown only."
        ),
    }

    instruction = style_instructions.get(style, style_instructions['lecture_notes'])

    # Clamp text size to prevent excessive prompt
    max_len = 5000
    src = text if len(text) <= max_len else text[:max_len]

    prompt = (
        f"{instruction}\n\n"
        f"Input text (verbatim, do not echo at the end):\n" + src
    )

    try:
        response = groq_generator.client.chat.completions.create(
            model=model_id or os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant'),
            messages=[
                {"role": "system", "content": "You transform text to requested academic styles and output clean Markdown only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=900,
            top_p=0.9
        )
        content = (response.choices[0].message.content or '').strip()
        return { 'success': True, 'style': style, 'content': content }
    except Exception as e:
        logger.error(f"Style rewrite error via Groq: {e}")
        # Soft fallback: return original text
        return { 'success': True, 'style': style, 'content': text }

async def _handle_style(request: Request):
    params = await _parse_style_params(request)
    text = params['text']
    style = params['style']
    model_id = params['model_id']

    result = await _style_rewrite_with_groq(text, style, model_id)
    return JSONResponse(status_code=200, content=result)

# Primary endpoint (preferred by UI)
@app.api_route("/api/rewrite-style", methods=["GET", "POST"])
async def rewrite_style_endpoint(request: Request):
    return await _handle_style(request)

# Alternate names the UI may try
@app.api_route("/api/style-rewrite", methods=["GET", "POST"])
async def rewrite_style_alias_endpoint(request: Request):
    return await _handle_style(request)

async def _parse_translate_params(request: Request) -> dict:
    """Parse translate parameters from JSON, form or query with flexible aliases."""
    data = {}
    form = None
    try:
        data = await request.json()
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    try:
        form = await request.form()
    except Exception:
        form = None
    query = dict(request.query_params or {})

    def pick(*keys, default=None):
        for k in keys:
            if k in data and data[k] not in (None, ""):
                return data[k]
            if form is not None and k in form and form[k] not in (None, ""):
                return form.get(k)
            if k in query and query[k] not in (None, ""):
                return query.get(k)
        return default

    text = pick('text', 'phrase', default="")
    raw_langs = pick('target_languages', 'languages', 'to', default=None)
    include_glossary_raw = pick('include_glossary', 'glossary', 'return_glossary', default=False)
    model_id = pick('model_id', 'model', default=os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant'))

    # Normalize languages
    languages: list[str] = []
    if isinstance(raw_langs, (list, tuple)):
        languages = [str(x).strip() for x in raw_langs if str(x).strip()]
    elif isinstance(raw_langs, str) and raw_langs.strip():
        languages = [s.strip() for s in raw_langs.split(',') if s.strip()]

    # Default to at least one language if none provided
    if not languages:
        languages = ['es']

    # Normalize boolean for include_glossary
    if isinstance(include_glossary_raw, str):
        include_glossary = include_glossary_raw.strip().lower() in ("1", "true", "yes", "y", "on")
    else:
        include_glossary = bool(include_glossary_raw)

    return {
        'text': str(text or "").strip(),
        'languages': languages,
        'include_glossary': include_glossary,
        'model_id': model_id,
    }

async def _translate_with_groq(text: str, languages: list[str], include_glossary: bool, model_id: str) -> dict:
    """Use Groq LLM to produce translations and optional glossary in a single JSON response."""
    if not groq_generator.is_available():
        # Graceful fallback: echo text for each language, empty glossary
        return {
            'success': True,
            'translations': [{ 'lang': lang, 'text': text } for lang in languages],
            'glossary': []
        }

    prompt = (
        "You are a precise multilingual translator. Translate the input text into the specified language codes. "
        "Return strictly valid JSON with no extra commentary. If include_glossary is true, also add a small glossary of 3-7 key terms.\n\n"
        f"Input text: {json.dumps(text)}\n"
        f"Target language codes: {json.dumps(languages)}\n"
        f"Include glossary: {json.dumps(include_glossary)}\n\n"
        "JSON schema:\n"
        "{\n"
        "  \"translations\": [ { \"lang\": <code>, \"text\": <translated text> }, ... ],\n"
        "  \"glossary\": [ { \"term\": <term>, \"definition\": <short definition>, \"targetLang\": <code optional> }, ... ]\n"
        "}\n"
        "Do not wrap in markdown."
    )

    try:
        try:
            response = groq_generator.client.chat.completions.create(
                model=model_id or os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant'),
                messages=[
                    {"role": "system", "content": "You translate accurately and output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=900,
                top_p=0.9,
                response_format={"type": "json_object"}
            )
        except Exception as e_rf:
            logger.warning(f"Groq response_format not supported or failed, retrying without enforcement: {e_rf}")
            response = groq_generator.client.chat.completions.create(
                model=model_id or os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant'),
                messages=[
                    {"role": "system", "content": "You translate accurately and output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=900,
                top_p=0.9
            )
        content = response.choices[0].message.content.strip()
        # Attempt to extract JSON if model added extra text
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1 and end > start:
            content_json = content[start:end+1]
        else:
            content_json = content
        try:
            parsed = json.loads(content_json)
        except Exception as je:
            # Sanitize invalid unicode escapes like \uXXXX (malformed) and stray backslashes
            s = content_json
            # Replace any \u not followed by 4 hex digits with escaped backslash
            s = re.sub(r"\\u(?![0-9a-fA-F]{4})", r"\\\\u", s)
            # Escape lone backslashes that are not valid JSON escapes
            s = re.sub(r"(?<!\\)\\(?![\\\"/bfnrtu])", r"\\\\", s)
            try:
                parsed = json.loads(s)
            except Exception as je2:
                logger.error(f"Lenient JSON parse failed for Groq translation: {je2}")
                raise
        translations = parsed.get('translations')
        glossary = parsed.get('glossary', [])

        # Normalize translations to array
        if isinstance(translations, dict):
            # e.g., {"es": "hola", "fr": "bonjour"}
            translations = [{ 'lang': k, 'text': v } for k, v in translations.items()]
        elif isinstance(translations, list):
            # ensure shape
            norm = []
            for t in translations:
                if isinstance(t, dict) and 'lang' in t and 'text' in t:
                    norm.append({ 'lang': t['lang'], 'text': t['text'] })
            translations = norm
        else:
            # Fallback: build from languages if single string returned
            if isinstance(parsed, str):
                translations = [{ 'lang': languages[0], 'text': parsed }]
            else:
                translations = [{ 'lang': lang, 'text': text } for lang in languages]

        # Normalize glossary
        if not isinstance(glossary, list):
            glossary = []

        return { 'success': True, 'translations': translations, 'glossary': glossary }
    except Exception as e:
        logger.error(f"Translate error via Groq: {e}")
        # Soft fallback
        return {
            'success': True,
            'translations': [{ 'lang': lang, 'text': text } for lang in languages],
            'glossary': []
        }

async def _handle_translate(request: Request):
    params = await _parse_translate_params(request)
    text = params['text']
    languages = params['languages']
    include_glossary = params['include_glossary']
    model_id = params['model_id']

    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    result = await _translate_with_groq(text, languages, include_glossary, model_id)
    return JSONResponse(status_code=200, content=result)

# Primary endpoint (preferred by UI)
@app.api_route("/api/translate", methods=["GET", "POST"])
async def translate_endpoint(request: Request):
    return await _handle_translate(request)

# Alternate names the UI may try
@app.api_route("/api/translate-glossary", methods=["GET", "POST"])
async def translate_glossary_endpoint(request: Request):
    return await _handle_translate(request)

@app.api_route("/api/translate_with_glossary", methods=["GET", "POST"])
async def translate_with_glossary_endpoint(request: Request):
    return await _handle_translate(request)

# ELI5 endpoints (supports JSON POST, GET with query, and form-encoded POST; multiple route names)
async def _parse_eli5_params(request: Request) -> dict:
    """Parse ELI5 parameters from JSON, form or query with flexible aliases."""
    data = {}
    form = None
    try:
        data = await request.json()
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    try:
        form = await request.form()
    except Exception:
        form = None
    query = dict(request.query_params or {})

    def pick(*keys, default=None):
        for k in keys:
            if k in data and data[k] not in (None, ""):
                return data[k]
            if form is not None and k in form and form[k] not in (None, ""):
                return form.get(k)
            if k in query and query[k] not in (None, ""):
                return query.get(k)
        return default

    phrase = pick('phrase', 'text', default="")
    model_id = pick('model_id', 'model', default=os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant'))

    return {
        'phrase': str(phrase or "").strip(),
        'model_id': model_id,
    }

async def _eli5_with_groq(phrase: str, model_id: str) -> dict:
    """Use Groq LLM to produce beginner and intermediate explanations as JSON."""
    if not groq_generator.is_available():
        raise HTTPException(status_code=503, detail="ELI5 service is not available. Please check AI configuration.")

    # Build JSON-enforced prompt
    prompt = (
        "You are a teacher. Explain the input concept at two levels and return strictly valid JSON only.\n\n"
        f"Concept: {json.dumps(phrase)}\n\n"
        "JSON schema:\n"
        "{\n"
        "  \"beginner\": <2-4 short, simple sentences>,\n"
        "  \"intermediate\": <3-6 concise, more detailed sentences>\n"
        "}\n"
        "No commentary or markdown, JSON only."
    )

    try:
        try:
            response = groq_generator.client.chat.completions.create(
                model=model_id or os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant'),
                messages=[
                    {"role": "system", "content": "You explain concepts at beginner and intermediate levels and output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.25,
                max_tokens=700,
                top_p=0.9,
                response_format={"type": "json_object"}
            )
        except Exception as e_rf:
            logger.warning(f"Groq response_format not supported for ELI5 or failed, retrying without enforcement: {e_rf}")
            response = groq_generator.client.chat.completions.create(
                model=model_id or os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant'),
                messages=[
                    {"role": "system", "content": "You explain concepts at beginner and intermediate levels and output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.25,
                max_tokens=700,
                top_p=0.9
            )
        content = response.choices[0].message.content.strip()
        # Attempt to extract/parse JSON
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1 and end > start:
            content_json = content[start:end+1]
        else:
            content_json = content
        try:
            parsed = json.loads(content_json)
        except Exception as je:
            s = content_json
            s = re.sub(r"\\u(?![0-9a-fA-F]{4})", r"\\\\u", s)
            s = re.sub(r"(?<!\\)\\(?![\\\"/bfnrtu])", r"\\\\", s)
            parsed = json.loads(s)
        beginner = str(parsed.get('beginner', '')).strip()
        intermediate = str(parsed.get('intermediate', '')).strip()
        return { 'success': True, 'beginner': beginner, 'intermediate': intermediate }
    except Exception as e:
        logger.error(f"ELI5 error via Groq: {e}")
        raise HTTPException(status_code=502, detail="Failed to generate ELI5 explanation. Please try again.")

async def _handle_eli5(request: Request):
    params = await _parse_eli5_params(request)
    phrase = params['phrase']
    model_id = params['model_id']

    if not phrase:
        raise HTTPException(status_code=400, detail="Phrase is required")

    if len(phrase) > 500:
        phrase = phrase[:500]

    result = await _eli5_with_groq(phrase, model_id)
    return JSONResponse(status_code=200, content=result)

# Primary endpoint (preferred by UI)
@app.api_route("/api/explain-eli5", methods=["GET", "POST"])
async def explain_eli5_endpoint(request: Request):
    return await _handle_eli5(request)

# Alternate name the UI may try
@app.api_route("/api/eli5", methods=["GET", "POST"])
async def eli5_alias_endpoint(request: Request):
    return await _handle_eli5(request)

# Mind map generation endpoints (supports JSON POST, GET with query, and form-encoded POST; multiple route names)
async def _parse_mindmap_params(request: Request) -> dict:
    """Parse Mind Map parameters from JSON, form or query with flexible aliases."""
    data = {}
    form = None
    try:
        data = await request.json()
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    try:
        form = await request.form()
    except Exception:
        form = None
    query = dict(request.query_params or {})

    def pick(*keys, default=None):
        for k in keys:
            if k in data and data[k] not in (None, ""):
                return data[k]
            if form is not None and k in form and form[k] not in (None, ""):
                return form.get(k)
            if k in query and query[k] not in (None, ""):
                return query.get(k)
        return default

    text = pick('text', 'phrase', 'content', default="")
    diagram_type = pick('diagram_type', 'type', default='mindmap')
    model_id = pick('model_id', 'model', default=os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant'))

    return {
        'text': str(text or "").strip(),
        'diagram_type': (diagram_type or 'mindmap').strip(),
        'model_id': model_id,
    }

async def _mindmap_with_groq(text: str, diagram_type: str, model_id: str) -> dict:
    """Use Groq LLM via DiagramGenerator to produce a Mermaid mind map diagram."""
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    # Prefer dedicated diagram generator which already uses llama-3.1-8b-instant
    if diagram_generator.is_available():
        if diagram_type.lower() == 'mindmap':
            diagram = diagram_generator.generate_mindmap_diagram(text)
        else:
            diagram = diagram_generator.generate_diagram_from_notes(text, diagram_type)
        if diagram:
            return { 'success': True, 'diagram': diagram }
        # Fall through to naive fallback if generation failed

    # Fallback: build a trivial mindmap Mermaid from keywords
    try:
        center = (text.split('\n', 1)[0] or 'Topic').strip()[:60]
        # simple keyword extraction
        import re
        words = re.findall(r"[A-Za-z]{4,}", text.lower())
        stop = set(['the','and','for','with','that','this','from','into','over','under','also','than','then','they','them','your','are','was','were','have','has','used','using','use','you','will','shall','should','could','would','can','may','might','not','but','because','therefore','however','moreover','furthermore','about'])
        freq = {}
        for w in words:
            if w in stop: continue
            freq[w] = freq.get(w, 0) + 1
        keywords = [w for w,_ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:8]] or ['idea','concept','detail']
        lines = ["mindmap", f"  root((" + center.replace('(', '').replace(')', '') + "))"]
        for kw in keywords:
            lines.append(f"    {kw[:24]}")
        mermaid = "\n".join(lines)
        return {
            'success': True,
            'diagram': {
                'type': 'mindmap',
                'mermaid_syntax': mermaid,
                'title': center,
                'description': 'Auto-generated mind map from selection',
            }
        }
    except Exception as e:
        logger.error(f"Mindmap fallback generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate mind map")

async def _handle_mindmap(request: Request):
    params = await _parse_mindmap_params(request)
    text = params['text']
    diagram_type = params['diagram_type'] or 'mindmap'
    model_id = params['model_id']

    # Clamp length to reasonable bounds
    if len(text) > 5000:
        text = text[:5000]

    result = await _mindmap_with_groq(text, diagram_type, model_id)
    return JSONResponse(status_code=200, content=result)

# Primary mindmap endpoint
@app.api_route("/api/mindmap", methods=["GET", "POST"])
async def mindmap_endpoint(request: Request):
    return await _handle_mindmap(request)

# Alternate name the UI may try
@app.api_route("/api/generate-mindmap", methods=["GET", "POST"])
async def generate_mindmap_endpoint(request: Request):
    return await _handle_mindmap(request)

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
                files = [p.name for p in OUTPUT_DIR.glob(f"{job_id}_*")]
                logger.info(f"Output files for {job_id}: {files}")
            except Exception as le:
                logger.warning(f"Failed to list output files for {job_id}: {le}")
            raise HTTPException(status_code=404, detail="Job not found")

        # Prefer Markdown notes if available
        source_path = notes_md_file if notes_md_file.exists() else notes_file
        try:
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                notes_text = f.read()
        except Exception as re:
            logger.error(f"Failed reading notes for {job_id} from {source_path}: {re}")
            raise HTTPException(status_code=500, detail="Failed to read notes for diagram generation")

        # Generate diagram content
        diagram = diagram_generator.generate_diagram(notes_text, diagram_type=diagram_type)
        return {"success": True, "diagram": diagram, "job_id": job_id, "type": diagram_type}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating diagram for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate diagram")