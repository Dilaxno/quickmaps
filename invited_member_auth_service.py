"""
Invited Member Authentication Service

Handles authentication and session management for invited members
who don't have full Firebase accounts but can access workspaces.
"""

import logging
from typing import Dict, Optional
from fastapi import Request
from firebase_admin import firestore

logger = logging.getLogger(__name__)

class InvitedMemberAuthService:
    """Service for handling invited member authentication"""
    
    def __init__(self, db_client=None):
        self.db = db_client
        
    def set_db(self, db_client):
        """Set the Firestore database client"""
        self.db = db_client
    
    def _normalize_datetime(self, dt):
        """Convert any datetime/timestamp to a naive datetime object for consistent comparison"""
        from datetime import datetime
        if hasattr(dt, 'replace'):
            # It's a datetime object, ensure it's naive
            if dt.tzinfo is not None:
                return dt.replace(tzinfo=None)
            return dt
        elif hasattr(dt, 'timestamp'):
            # It's a Firestore timestamp, convert to naive datetime
            return datetime.fromtimestamp(dt.timestamp())
        else:
            # Unknown type, return as is (will cause error later if used in comparison)
            return dt
        
    async def get_invited_member_info_from_request(self, request: Request) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Extract invited member information from session token in request headers
        
        Args:
            request (Request): FastAPI request object
            
        Returns:
            tuple: (session_id, email, workspace_id, role) or (None, None, None, None) if invalid
        """
        auth_header = request.headers.get("X-Invited-Member-Session")
        if not auth_header:
            return None, None, None, None
        
        session_id = auth_header
        
        try:
            if not self.db:
                return None, None, None, None
                
            session_ref = self.db.collection('invited_member_sessions').document(session_id)
            session_doc = session_ref.get()
            
            if not session_doc.exists:
                return None, None, None, None
                
            session_data = session_doc.to_dict()
            
            # Check if session is expired
            from datetime import datetime
            current_time = datetime.utcnow()
            expires_at = self._normalize_datetime(session_data['expires_at'])
            
            if current_time > expires_at:
                return None, None, None, None
                
            return (
                session_id,
                session_data.get('email', ''),
                session_data.get('workspace_id', ''),
                session_data.get('role', 'view')
            )
            
        except Exception as e:
            logger.error(f"Session verification failed: {e}")
            return None, None, None, None
    
    async def validate_invited_member_access(self, session_id: str, workspace_id: str) -> bool:
        """Validate if invited member has access to a specific workspace"""
        try:
            if not self.db:
                return False
                
            session_ref = self.db.collection('invited_member_sessions').document(session_id)
            session_doc = session_ref.get()
            
            if not session_doc.exists:
                return False
                
            session_data = session_doc.to_dict()
            
            # Check if session is expired
            from datetime import datetime
            current_time = datetime.utcnow()
            expires_at = self._normalize_datetime(session_data['expires_at'])
            
            if current_time > expires_at:
                return False
                
            # Check if workspace matches
            return session_data.get('workspace_id') == workspace_id
            
        except Exception as e:
            logger.error(f"Error validating invited member access: {e}")
            return False

# Create global instance
invited_member_auth_service = InvitedMemberAuthService()
