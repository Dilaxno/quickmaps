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
        if not brevo_service.is_configured():
            logger.error('Brevo service not configured; cannot send verification email')
            return False

        subject = '✅ Verify your email - QuickMaps'
        html_content = f"""
        <!DOCTYPE html>
        <html lang=\"en\">
        <head>
            <meta charset=\"UTF-8\">
            <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
            <title>Verify your email</title>
            <style>
                body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b1020; color: #e5e7eb; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 32px 20px; }}
                .card {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; padding: 28px; }}
                .title {{ font-size: 22px; font-weight: 800; margin: 0 0 8px 0; }}
                .subtitle {{ color: #9ca3af; margin: 0 0 20px 0; }}
                .code {{ font-size: 36px; font-weight: 800; letter-spacing: 8px; background: rgba(255,255,255,0.08); padding: 16px 20px; border-radius: 12px; text-align: center; border: 1px dashed rgba(255,255,255,0.16); }}
                .footer {{ color: #9ca3af; font-size: 12px; margin-top: 18px; }}
            </style>
        </head>
        <body>
            <div class=\"container\">
                <div class=\"card\">
                    <div class=\"title\">Verify your email</div>
                    <div class=\"subtitle\">Hi {name}, enter this 6-digit code in the app to complete your sign up. The code expires in {self.expiry_minutes} minutes.</div>
                    <div class=\"code\">{code}</div>
                </div>
                <div class=\"footer\">If you didn't request this, you can ignore this email.</div>
            </div>
        </body>
        </html>
        """
        text_content = f"Your QuickMaps verification code is: {code}\nThis code expires in {self.expiry_minutes} minutes. If you didn't request it, ignore this email."
        email_data = {
            "sender": {"name": brevo_service.sender_name, "email": brevo_service.sender_email},
            "to": [{"email": email, "name": name}],
            "subject": subject,
            "htmlContent": html_content,
            "textContent": text_content,
            "tags": ["email-verification", "otp"]
        }
        try:
            response = requests.post(
                f"{brevo_service.base_url}/smtp/email",
                headers=brevo_service._get_headers(),  # reuse headers builder
                json=email_data
            )
            if response.status_code == 201:
                logger.info(f"Sent OTP to {email}")
                return True
            logger.error(f"Brevo OTP send failed: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            logger.error(f"Error sending OTP via Brevo: {e}")
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
            return {"success": False, "error": "RESEND_COOLDOWN", "message": "Please wait before requesting a new code."}

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
            return {"success": False, "error": "EMAIL_FAILED", "message": "Failed to send verification email"}
        return {"success": True}

    def verify(self, email: str, code: str) -> Dict[str, Any]:
        email_key = email.lower()
        doc_ref = self._get_db().collection(self.collection).document(email_key)
        doc = doc_ref.get()
        if not doc.exists:
            return {"success": False, "error": "NOT_REQUESTED", "message": "No verification request for this email"}
        data = doc.to_dict()

        # Expired?
        try:
            expiry = data.get('expires_at').replace(tzinfo=None)
        except Exception:
            expiry = data.get('expires_at')
        if expiry < self._now_utc():
            return {"success": False, "error": "EXPIRED", "message": "Code expired"}

        # Already used?
        if data.get('used'):
            return {"success": False, "error": "ALREADY_USED", "message": "Code already used"}

        # Too many attempts?
        attempts = int(data.get('attempts', 0))
        if attempts >= self.max_attempts:
            return {"success": False, "error": "TOO_MANY_ATTEMPTS", "message": "Too many attempts. Request a new code."}

        if str(code).strip() != str(data.get('code', '')).strip():
            # increment attempts
            doc_ref.update({'attempts': attempts + 1})
            return {"success": False, "error": "INVALID_CODE", "message": "Invalid code"}

        # Mark used
        doc_ref.update({'used': True, 'verified_at': self._now_utc()})
        return {"success": True}

# Global instance
email_verification_service = EmailVerificationService()