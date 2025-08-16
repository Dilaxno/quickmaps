import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
from firebase_admin import firestore, auth

logger = logging.getLogger(__name__)

class PasswordResetService:
    def __init__(self):
        # General Configuration
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@quickmaps.pro')
        self.from_name = os.getenv('FROM_NAME', 'QuickMaps')
        self.frontend_url = os.getenv('FRONTEND_URL', 'https://quickmaps.pro')
        if 'localhost' in self.frontend_url or '127.0.0.1' in self.frontend_url:
            self.frontend_url = 'https://quickmaps.pro'
        
        # Initialize Firestore later to avoid initialization order issues
        self.db = None
    
    def _get_db(self):
        """Get Firestore client, initializing if needed"""
        if self.db is None:
            self.db = firestore.client()
        return self.db
    
    def set_db(self, db_client):
        """Set the Firestore database client"""
        self.db = db_client
    
    def generate_reset_token(self) -> str:
        """Generate a secure reset token"""
        return secrets.token_urlsafe(32)
    
    async def create_reset_token(self, email: str) -> str:
        """Create and store a password reset token"""
        token = self.generate_reset_token()
        expires_at = datetime.utcnow() + timedelta(hours=1)  # 1 hour expiry
        
        # Store token in Firestore
        token_data = {
            'email': email,
            'expires_at': expires_at,
            'used': False,
            'created_at': datetime.utcnow()
        }
        
        self._get_db().collection('passwordResetTokens').document(token).set(token_data)
        logger.info(f"Created password reset token for email: {email}")
        
        return token
    
    async def validate_reset_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a password reset token"""
        try:
            token_doc = self._get_db().collection('passwordResetTokens').document(token).get()
            
            if not token_doc.exists:
                logger.warning(f"Invalid reset token attempted: {token}")
                return None
            
            token_data = token_doc.to_dict()
            
            if token_data.get('used', False):
                logger.warning(f"Already used reset token attempted: {token}")
                return None
            
            if token_data.get('expires_at').replace(tzinfo=None) < datetime.utcnow():
                logger.warning(f"Expired reset token attempted: {token}")
                return None
            
            logger.info(f"Valid reset token for email: {token_data.get('email', 'unknown')}")
            return token_data
            
        except Exception as e:
            logger.error(f"Error validating reset token: {e}")
            return None
    
    async def mark_token_as_used(self, token: str) -> bool:
        """Mark a reset token as used"""
        try:
            self._get_db().collection('passwordResetTokens').document(token).update({
                'used': True,
                'used_at': datetime.utcnow()
            })
            logger.info(f"Marked reset token as used: {token}")
            return True
        except Exception as e:
            logger.error(f"Error marking token as used: {e}")
            return False
    
    async def send_password_reset_email(self, email: str, reset_token: str, user_name: str = "there") -> bool:
        """Send password reset email via Resend"""
        
        # Import resend_service locally to avoid circular imports
        from resend_service import resend_service
        
        # Use Resend as the email provider
        if not resend_service.is_configured():
            logger.error("Resend service is not configured. Please add RESEND_API_KEY to your environment variables.")
            return False

        logger.info(f"Sending password reset email to {email} via Resend...")
        # Resend's method is async and expects (email, token)
        success = await resend_service.send_password_reset_email(email, reset_token)
        
        if success:
            logger.info(f"Password reset email sent successfully to {email}")
            return True
        else:
            logger.error(f"Failed to send password reset email to {email}")
            return False
    
    async def send_reset_email(self, email: str, user_name: str = "there") -> bool:
        """Main method to send password reset email - creates token and sends email"""
        try:
            # Create reset token
            reset_token = await self.create_reset_token(email)
            
            # Send email with token
            success = await self.send_password_reset_email(email, reset_token, user_name)
            
            if success:
                logger.info(f"Password reset process completed successfully for {email}")
                return True
            else:
                logger.error(f"Failed to complete password reset process for {email}")
                return False
                
        except Exception as e:
            logger.error(f"Error in send_reset_email for {email}: {e}")
            return False
    
    async def reset_password(self, token: str, new_password: str) -> Dict[str, Any]:
        """Reset password using token"""
        try:
            # Validate token
            token_data = await self.validate_reset_token(token)
            if not token_data:
                logger.warning(f"Invalid token used for password reset: {token}")
                return {"success": False, "error": "INVALID_TOKEN", "message": "Invalid or expired reset token"}
            
            email = token_data.get('email')
            if not email:
                logger.error(f"No email found in token data: {token}")
                return {"success": False, "error": "INVALID_DATA", "message": "Invalid token data"}
            
            # Validate new password
            if not new_password or len(new_password) < 6:
                logger.error(f"Invalid password provided for reset: too short (min 6 characters)")
                return {"success": False, "error": "WEAK_PASSWORD", "message": "Password must be at least 6 characters long"}
            
            # Get user by email from Firebase Auth
            try:
                user = auth.get_user_by_email(email)
                logger.info(f"Found Firebase user for password reset: {user.uid}")
            except auth.UserNotFoundError:
                logger.error(f"User not found in Firebase Auth for email: {email}")
                return {"success": False, "error": "USER_NOT_FOUND", "message": "User account not found"}
            except Exception as e:
                logger.error(f"Error getting Firebase user by email {email}: {e}")
                return {"success": False, "error": "AUTH_ERROR", "message": "Authentication service error"}
            
            # Update user's password in Firebase Authentication
            try:
                auth.update_user(user.uid, password=new_password)
                logger.info(f"✅ Password updated successfully in Firebase Auth for user: {user.uid} (email: {email})")
            except Exception as e:
                logger.error(f"❌ Error updating password in Firebase Auth for user {user.uid}: {e}")
                return {"success": False, "error": "UPDATE_FAILED", "message": "Failed to update password"}
            
            # Mark token as used
            await self.mark_token_as_used(token)
            
            logger.info(f"🎉 Password reset completed successfully for email: {email}")
            return {"success": True, "message": "Password reset successfully"}
            
        except Exception as e:
            logger.error(f"❌ Error resetting password: {e}")
            return {"success": False, "error": "INTERNAL_ERROR", "message": f"Internal server error: {str(e)}"}

# Create global instance
password_reset_service = PasswordResetService()