"""
Authentication Service Module

Handles Firebase authentication and user information extraction.
"""

import logging
from typing import Tuple, Optional
from fastapi import Request
from firebase_admin import auth

logger = logging.getLogger(__name__)

class AuthService:
    """Service for handling Firebase authentication"""
    
    @staticmethod
    async def get_user_info_from_request(request: Request) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Extract user information from Firebase token in request headers
        
        Args:
            request (Request): FastAPI request object
            
        Returns:
            tuple: (user_id, user_email, user_name) or (None, None, None) if invalid
        """
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None, None, None
        
        token = auth_header.split(" ")[1]
        
        try:
            decoded_token = auth.verify_id_token(token)
            user_id = decoded_token['uid']
            user_email = decoded_token.get('email', '')
            user_name = decoded_token.get('name', 
                decoded_token.get('email', '').split('@')[0] if decoded_token.get('email') else 'User')
            return user_id, user_email, user_name
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return None, None, None
    
    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        """
        Verify Firebase ID token
        
        Args:
            token (str): Firebase ID token
            
        Returns:
            dict: Decoded token data or None if invalid
        """
        try:
            decoded_token = auth.verify_id_token(token)
            return decoded_token
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return None
    
    @staticmethod
    def extract_token_from_header(auth_header: str) -> Optional[str]:
        """
        Extract token from Authorization header
        
        Args:
            auth_header (str): Authorization header value
            
        Returns:
            str: Token or None if invalid format
        """
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        return auth_header.split(" ")[1]

# Global instance
auth_service = AuthService()