import os
import json
from typing import Optional
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from .ip_detection import get_vpn_detector
import logging

# Load environment variables
load_dotenv()

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
def initialize_firebase():
    if not firebase_admin._apps:
        # Create credentials from environment variables
        firebase_config = {
            "type": "service_account",
            "project_id": os.getenv("FIREBASE_PROJECT_ID"),
            "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace('\\n', '\n') if os.getenv("FIREBASE_PRIVATE_KEY") else None,
            "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
            "client_id": os.getenv("FIREBASE_CLIENT_ID"),
            "auth_uri": os.getenv("FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": os.getenv("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
            "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_X509_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs"),
            "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_X509_CERT_URL")
        }
        
        # Check if all required fields are present
        required_fields = ["project_id", "private_key", "client_email"]
        missing_fields = [field for field in required_fields if not firebase_config.get(field)]
        
        if missing_fields:
            print(f"Warning: Missing Firebase configuration fields: {missing_fields}")
            print("Firebase authentication will not be available.")
            return None
        
        try:
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred)
            print("Firebase Admin SDK initialized successfully")
            return True
        except Exception as e:
            print(f"Error initializing Firebase Admin SDK: {e}")
            return None
    return True

# Initialize Firebase on module import
firebase_initialized = initialize_firebase()

# Security scheme
security = HTTPBearer(auto_error=False)

class FirebaseAuth:
    @staticmethod
    async def verify_token(token: str) -> Optional[dict]:
        """Verify Firebase ID token and return user info"""
        if not firebase_initialized:
            return None
            
        try:
            decoded_token = auth.verify_id_token(token)
            return decoded_token
        except Exception as e:
            print(f"Token verification error: {e}")
            return None

    @staticmethod
    async def get_user_info(uid: str) -> Optional[dict]:
        """Get user information from Firebase Auth"""
        if not firebase_initialized:
            return None
            
        try:
            user_record = auth.get_user(uid)
            return {
                "uid": user_record.uid,
                "email": user_record.email,
                "display_name": user_record.display_name,
                "photo_url": user_record.photo_url,
                "email_verified": user_record.email_verified,
                "disabled": user_record.disabled,
                "provider_data": [
                    {
                        "provider_id": provider.provider_id,
                        "uid": provider.uid,
                        "email": provider.email,
                        "display_name": provider.display_name,
                        "photo_url": provider.photo_url
                    }
                    for provider in user_record.provider_data
                ]
            }
        except Exception as e:
            print(f"Error getting user info: {e}")
            return None

# IP checking configuration
VPN_BLOCKING_ENABLED = os.getenv("VPN_BLOCKING_ENABLED", "true").lower() == "true"
STRICT_MODE = os.getenv("VPN_STRICT_MODE", "false").lower() == "true"  # If true, blocks all proxies; if false, only VPN/TOR

def check_ip_allowed(request: Request) -> tuple[bool, dict]:
    """
    Check if the client IP is allowed (not from VPN/Proxy)
    
    Args:
        request: FastAPI request object
        
    Returns:
        Tuple of (is_allowed, detection_result)
    """
    if not VPN_BLOCKING_ENABLED:
        return True, {"message": "VPN blocking disabled"}
    
    detector = get_vpn_detector()
    client_ip = detector.get_client_ip(request)
    
    # Skip checking for localhost/private IPs during development
    if client_ip in ["127.0.0.1", "localhost", "::1"] or client_ip.startswith("192.168.") or client_ip.startswith("10.") or client_ip.startswith("172."):
        logger.info(f"Skipping VPN check for local IP: {client_ip}")
        return True, {"message": f"Local IP allowed: {client_ip}"}
    
    should_block, result = detector.is_blocked_ip(client_ip, strict_mode=STRICT_MODE)
    
    if should_block:
        logger.warning(f"Blocked authentication attempt from {client_ip}: {result.get('proxy_type', 'UNKNOWN')}")
    else:
        logger.info(f"Allowed authentication from {client_ip}")
    
    return not should_block, result

# Dependency to get current user
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), request: Request = None) -> Optional[dict]:
    """FastAPI dependency to get current authenticated user"""
    if not credentials or not firebase_initialized:
        return None
    
    # Check IP if request is provided
    if request:
        ip_allowed, ip_result = check_ip_allowed(request)
        if not ip_allowed:
            logger.warning(f"Authentication blocked due to VPN/Proxy: {ip_result}")
            return None
    
    try:
        token = credentials.credentials
        user_info = await FirebaseAuth.verify_token(token)
        return user_info
    except Exception as e:
        print(f"Authentication error: {e}")
        return None

# Dependency to require authentication
async def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security), request: Request = None) -> dict:
    """FastAPI dependency that requires authentication"""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authorization header is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not firebase_initialized:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is not available"
        )
    
    # Check IP first
    if request:
        ip_allowed, ip_result = check_ip_allowed(request)
        if not ip_allowed:
            proxy_type = ip_result.get('proxy_type', 'UNKNOWN')
            country = ip_result.get('country_name', 'Unknown')
            
            # Create user-friendly error messages based on proxy type
            if proxy_type == 'VPN':
                friendly_message = "For security reasons, VPN connections are not allowed. Please disconnect your VPN and try again."
            elif proxy_type == 'TOR':
                friendly_message = "For security reasons, TOR connections are not allowed. Please use a regular internet connection and try again."
            elif proxy_type in ['PUB', 'WEB']:
                friendly_message = "For security reasons, proxy connections are not allowed. Please use a direct internet connection and try again."
            else:
                friendly_message = "For security reasons, your current internet connection is not allowed. Please try using a different network or contact support if you believe this is an error."
            
            raise HTTPException(
                status_code=403,
                detail=friendly_message,
                headers={
                    "X-Blocked-Reason": "VPN_PROXY_DETECTED",
                    "X-Proxy-Type": proxy_type,
                    "X-Country": country,
                    "X-Technical-Detail": f"VPN/Proxy detected ({proxy_type}) from {country}"
                }
            )
    
    try:
        token = credentials.credentials
        user_info = await FirebaseAuth.verify_token(token)
        
        if not user_info:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user_info
    except HTTPException:
        raise
    except Exception as e:
        print(f"Authentication error: {e}")
        raise HTTPException(
            status_code=401,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Optional authentication dependency
async def optional_auth(credentials: HTTPAuthorizationCredentials = Depends(security), request: Request = None) -> Optional[dict]:
    """FastAPI dependency for optional authentication"""
    if not credentials or not firebase_initialized:
        return None
    
    # Check IP if request is provided
    if request:
        ip_allowed, ip_result = check_ip_allowed(request)
        if not ip_allowed:
            logger.warning(f"Optional authentication blocked due to VPN/Proxy: {ip_result}")
            return None
    
    try:
        token = credentials.credentials
        user_info = await FirebaseAuth.verify_token(token)
        return user_info
    except Exception:
        return None