import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
import requests
from firebase_admin import firestore

logger = logging.getLogger(__name__)

class EmailVerificationService:
    def __init__(self):
        self.code_length = int(os.getenv('EMAIL_OTP_LENGTH', '6'))
        self.expiry_minutes = int(os.getenv('EMAIL_OTP_EXPIRY_MINUTES', '10'))
        self.max_attempts = int(os.getenv('EMAIL_OTP_MAX_ATTEMPTS', '5'))
        self.resend_cooldown_seconds = int(os.getenv('EMAIL_OTP_RESEND_COOLDOWN_SECONDS', '60'))
        self.collection = 'emailVerificationOtps'
        self.db = None  # set lazily

    def _get_db(self):
        if self.db is None:
            self.db = firestore.client()
        return self.db

    def _generate_code(self) -> str:
        # Generate numeric OTP of desired length
        digits = '0123456789'
        return ''.join(secrets.choice(digits) for _ in range(self.code_length))

    def _now_utc(self) -> datetime:
        return datetime.utcnow()

    def _send_via_brevo(self, email: str, code: str, name: str = 'there') -> bool:
        # Import instance to reuse config and headers
        from brevo_service import brevo_service
        
        logger.info(f"🔧 Attempting to send OTP email to: {email}")
        logger.info(f"🔧 Brevo service configured: {brevo_service.is_configured()}")
        
        if not brevo_service.is_configured():
            logger.error('❌ Brevo service not configured; cannot send verification email')
            return False

        try:
            # Use the dedicated OTP email method from brevo_service
            success = brevo_service.send_otp_verification_email(
                user_email=email,
                otp_code=code,
                user_name=name,
                expiry_minutes=self.expiry_minutes
            )
            
            if success:
                logger.info(f"✅ Successfully sent OTP email to {email}")
                return True
            else:
                logger.error(f"❌ Failed to send OTP email to {email}")
                return False
                
        except Exception as e:
            logger.error(f"Error in _send_via_brevo: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False

    def can_resend(self, email: str) -> bool:
        doc = self._get_db().collection(self.collection).document(email.lower()).get()
        if not doc.exists:
            return True
        data = doc.to_dict()
        last_sent_at = data.get('last_sent_at')
        if not last_sent_at:
            return True
        # Firestore timestamps come as datetime with tz; compare in UTC-naive
        try:
            last = last_sent_at.replace(tzinfo=None)
        except Exception:
            last = last_sent_at
        return (self._now_utc() - last).total_seconds() >= self.resend_cooldown_seconds

    def create_and_send(self, email: str, name: Optional[str] = None) -> Dict[str, Any]:
        email_key = email.lower()
        if not self.can_resend(email_key):
            return {"success": False, "error": "RESEND_COOLDOWN", "message": "Please wait a moment before requesting another verification email."}

        code = self._generate_code()
        expires_at = self._now_utc() + timedelta(minutes=self.expiry_minutes)
        data = {
            'email': email_key,
            'code': code,
            'expires_at': expires_at,
            'attempts': 0,
            'used': False,
            'last_sent_at': self._now_utc(),
            'created_at': self._now_utc(),
        }
        self._get_db().collection(self.collection).document(email_key).set(data)

        sent = self._send_via_brevo(email_key, code, name or email.split('@')[0])
        if not sent:
            return {"success": False, "error": "EMAIL_FAILED", "message": "We couldn't send your verification email. Please check your email address and try again."}
        return {"success": True}

    def verify(self, email: str, code: str) -> Dict[str, Any]:
        email_key = email.lower()
        doc_ref = self._get_db().collection(self.collection).document(email_key)
        doc = doc_ref.get()
        if not doc.exists:
            return {"success": False, "error": "NOT_REQUESTED", "message": "We couldn't find a verification request for this email. Please request a new verification code."}
        data = doc.to_dict()

        # Expired?
        try:
            expiry = data.get('expires_at').replace(tzinfo=None)
        except Exception:
            expiry = data.get('expires_at')
        if expiry < self._now_utc():
            return {"success": False, "error": "EXPIRED", "message": "This verification code has expired. Please request a new one."}

        # Already used?
        if data.get('used'):
            return {"success": False, "error": "ALREADY_USED", "message": "This verification code has already been used. Your email is already verified!"}

        # Too many attempts?
        attempts = int(data.get('attempts', 0))
        if attempts >= self.max_attempts:
            return {"success": False, "error": "TOO_MANY_ATTEMPTS", "message": "Too many incorrect attempts. Please request a new verification code."}

        if str(code).strip() != str(data.get('code', '')).strip():
            # increment attempts
            doc_ref.update({'attempts': attempts + 1})
            return {"success": False, "error": "INVALID_CODE", "message": "The verification code you entered is incorrect. Please check and try again."}

        # Mark used
        doc_ref.update({'used': True, 'verified_at': self._now_utc()})
        return {"success": True}

# Global instance
email_verification_service = EmailVerificationService()