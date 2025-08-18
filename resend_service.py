import os
import logging
from typing import Optional
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class ResendService:
    """
    Resend email service for sending password reset, welcome, low credit and other transactional emails.
    All HTML emails share the same branding: dark gradient header, rounded white card, and primary button color.
    """
    
    def __init__(self):
        # Resend API Configuration
        self.api_key = os.getenv('RESEND_API_KEY')
        self.api_url = "https://api.resend.com/emails"
        
        # Email Configuration
        self.from_email = os.getenv('RESEND_FROM_EMAIL', 'noreply@quickmaps.pro')
        self.from_name = os.getenv('FROM_NAME', 'QuickMaps')
        self.frontend_url = os.getenv('FRONTEND_URL', 'https://quickmaps.pro')
        if 'localhost' in self.frontend_url or '127.0.0.1' in self.frontend_url:
            self.frontend_url = 'https://quickmaps.pro'
        
        # Validate configuration
        if not self.api_key:
            logger.warning("Resend API key not configured. Resend service will not be available.")
    
    def is_configured(self) -> bool:
        """Check if Resend service is properly configured"""
        return bool(self.api_key)

    # ---------- Shared Branding ----------
    def _wrap_branded_email(self, header_title: str, header_subtitle: Optional[str], inner_html: str, subject_title: Optional[str] = None) -> str:
        """Wraps provided inner HTML content with a shared branded HTML shell.
        header_title: Brand or category title shown in gradient header (usually self.from_name)
        header_subtitle: Smaller subtitle below brand (can be None)
        inner_html: The main body content
        subject_title: Optional <title> element override
        """
        title_tag = subject_title or header_title or self.from_name
        subtitle_html = f'<div class="subtitle" style="opacity:.85; font-size:14px;">{header_subtitle}</div>' if header_subtitle else ''
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <title>{title_tag}</title>
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#f6f7fb; margin:0; padding:20px; color:#111827; }}
            .container {{ max-width:600px; margin:0 auto; background:#ffffff; border-radius:16px; box-shadow:0 10px 25px rgba(0,0,0,0.08); overflow:hidden; }}
            .header {{ background:linear-gradient(135deg,#090040 0%, #4c1d95 100%); color:#fff; padding:28px 24px; text-align:center; }}
            .brand {{ font-weight:700; font-size:22px; letter-spacing:-0.2px; }}
            .content {{ padding:28px 24px; }}
            .greeting {{ font-size:18px; font-weight:600; margin:0 0 12px; }}
            .message {{ font-size:15px; line-height:1.7; color:#374151; }}
            .button-wrap {{ text-align:center; margin:24px 0 8px; }}
            .button {{ display:inline-block; text-decoration:none; background:#090040; color:#fff !important; padding:14px 22px; border-radius:10px; font-weight:700; box-shadow:0 6px 20px rgba(9,0,64,0.3); }}
            .link {{ color:#4c1d95; word-break: break-all; }}
            .footer {{ padding:18px 24px; font-size:12px; color:#6b7280; text-align:center; background:#f9fafb; border-top:1px solid #e5e7eb; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <div class="brand">{self.from_name}</div>
              {subtitle_html}
            </div>
            <div class="content">
              {inner_html}
            </div>
            <div class="footer">
              © {datetime.now().year} {self.from_name}. All rights reserved.
            </div>
          </div>
        </body>
        </html>
        """

    # ---------- Password Reset Email ----------
    def get_password_reset_template(self, reset_url: str) -> str:
        """Get the HTML template for password reset email, branded like the low credit email."""
        inner = f"""
          <p class="greeting">Hi there,</p>
          <div class="message">
            <p>You requested a password reset for your {self.from_name} account.</p>
            <p>Click the button below to reset your password:</p>
          </div>
          <div class="button-wrap">
            <a href="{reset_url}" class="button">Reset Password</a>
          </div>
          <div class="message" style="margin-top:12px;">
            <p>This link will expire in 1 hour for security.</p>
            <p>If you did not request this reset, you can safely ignore this email.</p>
            <p>Link not working? Copy and paste this URL:</p>
            <p><a href="{reset_url}" class="link">{reset_url}</a></p>
          </div>
        """
        return self._wrap_branded_email(header_title=self.from_name, header_subtitle="Account security", inner_html=inner, subject_title="Reset your password")
    
    def get_password_reset_text(self, reset_url: str) -> str:
        """Get the plain text version for password reset email"""
        return f"""
{self.from_name} - Password Reset

Hi there,

You requested a password reset for your {self.from_name} account.

Reset link:
{reset_url}

This link will expire in 1 hour for security.
If you did not request this reset, please ignore this email.

Best regards,
{self.from_name} Team

This is an automated message, please do not reply.
        """

    # ---------- Welcome Email ----------
    def get_welcome_email_template(self, user_name: str = "there") -> str:
        """Get the HTML template for welcome email, with the same branding as other emails."""
        start_url = self.frontend_url
        inner = f"""
          <div class="greeting">Welcome to {self.from_name}, {user_name}! 🎉</div>
          <div class="message">
            <p>We're thrilled to have you join our community of learners and note-takers!</p>
            <p>{self.from_name} helps you organize your thoughts, create beautiful notes, and boost productivity with AI-powered features.</p>
            <p><strong>🎉 Great news!</strong> You're on the <strong>Free plan with 30 monthly credits</strong> to try the app. Each credit lets you upload videos, PDFs, or create AI-powered content.</p>
          </div>
          <div class="button-wrap">
            <a href="{start_url}" class="button">Start Creating Notes</a>
          </div>
          <div class="message">
            <p style="margin:0;">Questions? Reach us at <a class="link" href="mailto:support@quickmaps.pro">support@quickmaps.pro</a></p>
          </div>
        """
        return self._wrap_branded_email(header_title=self.from_name, header_subtitle="Transform your learning with AI-powered notes", inner_html=inner, subject_title=f"Welcome to {self.from_name}!")
    
    def get_welcome_email_text(self, user_name: str = "there") -> str:
        """Get the plain text version for welcome email"""
        return f"""
🎉 Welcome to {self.from_name}, {user_name}!

We're thrilled to have you join our community of learners and note-takers!

{self.from_name} helps you organize your thoughts, create beautiful notes, and boost productivity with AI-powered features.

🎉 Great news! You're on the Free plan with 30 MONTHLY CREDITS to try the app. Each credit lets you upload videos, PDFs, or create AI-powered content.

Get started: {self.frontend_url}

Questions? Contact our support team — we're here to help!
📧 support@quickmaps.pro

Best regards,
The {self.from_name} Team

© {datetime.now().year} {self.from_name}. All rights reserved.
Transform your learning with AI-powered notes.
        """

    async def send_welcome_email(self, email: str, user_name: str = None) -> bool:
        """Send welcome email to new users (branded consistently)"""
        try:
            if not self.is_configured():
                logger.error("Resend service not configured")
                return False
            name = user_name or (email.split('@')[0].title() if email else "there")
            html_content = self.get_welcome_email_template(name)
            text_content = self.get_welcome_email_text(name)
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [email],
                "subject": f"Welcome to {self.from_name}! 🎉",
                "html": html_content,
                "text": text_content,
                "tags": [{"name": "category", "value": "welcome"}],
            }
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            response = requests.post(self.api_url, json=payload, headers=headers)
            if response.status_code == 200:
                response_data = response.json()
                email_id = response_data.get('id', 'unknown')
                logger.info(f"✅ Welcome email sent successfully to: {email} (ID: {email_id})")
                return True
            else:
                logger.error(f"❌ Failed to send welcome email: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Error sending welcome email: {e}")
            return False

    # ---------- Password Reset Send ----------
    async def send_password_reset_email(self, email: str, reset_token: str) -> bool:
        """
        Send password reset email via Resend API
        """
        if not self.is_configured():
            logger.error("Resend service is not configured")
            return False
        
        try:
            reset_url = f"{self.frontend_url}/reset-password?token={reset_token}"
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [email],
                "subject": f"Reset Your Password - {self.from_name}",
                "html": self.get_password_reset_template(reset_url),
                "text": self.get_password_reset_text(reset_url),
                "tags": [{"name": "category", "value": "password_reset"}],
            }
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            response = requests.post(self.api_url, json=payload, headers=headers)
            if response.status_code == 200:
                response_data = response.json()
                email_id = response_data.get('id', 'unknown')
                logger.info(f"✅ Password reset email sent to {email} (ID: {email_id})")
                return True
            else:
                logger.error(f"❌ Resend API error (password reset): {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to send password reset email to {email}: {e}")
            return False

    # ---------- Low Credit Warning ----------
    async def send_low_credit_warning(self, email: str, user_name: str = None, current_credits: int = 0, plan: str = 'free', next_refill_date: datetime | None = None) -> bool:
        """Send a low credit balance warning email via Resend with an upgrade button.
        If plan is free, include the next refill date if provided.
        """
        if not self.is_configured():
            logger.error("Resend service is not configured")
            return False
        try:
            name = user_name or (email.split('@')[0].title() if email else "there")
            upgrade_url = f"{self.frontend_url}/pricing?ref=low-credits"
            subject = f"Low credits: {current_credits} remaining — upgrade to keep generating"

            refill_html = ""
            refill_text = ""
            if plan == 'free' and next_refill_date:
                try:
                    readable = next_refill_date.strftime('%b %d, %Y')
                except Exception:
                    readable = str(next_refill_date)
                refill_html = f"<p style=\"margin-top:8px;color:#6b7280;font-size:13px\">Free plan credits refill on <strong>{readable}</strong> (30 days from signup or last refill).</p>"
                refill_text = f"\nNext free-plan refill: {readable} (30 days from signup or last refill).\n"

            inner = f"""
              <p class=\"greeting\">Hi {name},</p>
              <div class=\"message\">
                <p>Your current credit balance is running low.</p>
              </div>
              <div class=\"stat\" style=\"background:#f3f4f6; border:1px solid #e5e7eb; border-radius:12px; padding:14px 16px; margin:16px 0; text-align:center; font-weight:600; color:#111827;\">Remaining credits: {current_credits}</div>
              <div class=\"message\">
                <p>To avoid interruptions, upgrade your plan and continue generating notes and diagrams without downtime.</p>
                {refill_html}
              </div>
              <div class=\"button-wrap\"> 
                <a href=\"{upgrade_url}\" class=\"button\">Upgrade plan</a>
              </div>
              <div class=\"message\" style=\"text-align:center; font-size:12px; color:#6b7280; margin-top:10px;\">
                or visit {self.frontend_url}/pricing
              </div>
            """
            html_content = self._wrap_branded_email(header_title=self.from_name, header_subtitle="Credit balance reminder", inner_html=inner, subject_title="Low Credits Warning")

            text_content = f"""
{self.from_name} — Low credits warning

Hi {name},

Your credit balance is running low.
Remaining credits: {current_credits}
{refill_text}
Upgrade to avoid interruptions:
{upgrade_url}

— {self.from_name}
            """

            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [email],
                "subject": subject,
                "html": html_content,
                "text": text_content,
                "tags": [{"name": "category", "value": "low_credits"}],
            }

            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            response = requests.post(self.api_url, json=payload, headers=headers)
            if response.status_code == 200:
                logger.info(f"✅ Low credit email sent to {email}")
                return True
            logger.error(f"❌ Resend API error (low credit): {response.status_code} - {response.text}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to send low credit email to {email}: {e}")
            return False

# Create global instance
resend_service = ResendService()