import os
import logging
from typing import Optional
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class ResendService:
    """
    Resend email service for sending password reset emails and other transactional emails.
    Resend is a modern email API service that provides reliable email delivery.
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
    
    def get_password_reset_template(self, reset_url: str) -> str:
        """Get the HTML template for password reset email"""
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Reset Your Password</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    margin: 0;
                    padding: 20px;
                    background: #f9f9f9;
                }}
                .container {{
                    max-width: 500px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 8px;
                    padding: 30px;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .brand {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #333;
                    margin-bottom: 10px;
                }}
                .message {{
                    font-size: 16px;
                    margin-bottom: 30px;
                }}
                .button {{
                    display: inline-block;
                    background: #007bff;
                    color: white;
                    text-decoration: none;
                    padding: 12px 24px;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                .button-container {{
                    text-align: center;
                    margin: 30px 0;
                }}
                .footer {{
                    font-size: 14px;
                    color: #666;
                    text-align: center;
                    margin-top: 30px;
                }}
                .link {{
                    color: #007bff;
                    word-break: break-all;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="brand">QuickMaps</div>
                </div>
                
                <div class="message">
                    <p>Hi there,</p>
                    <p>You requested a password reset for your QuickMaps account.</p>
                    <p>Click the button below to reset your password:</p>
                </div>
                
                <div class="button-container">
                    <a href="{reset_url}" class="button">Reset Password</a>
                </div>
                
                <div class="message">
                    <p>This link will expire in 1 hour for security.</p>
                    <p>If you did not request this reset, please ignore this email.</p>
                    <p>Link not working? Copy and paste this URL:</p>
                    <p><a href="{reset_url}" class="link">{reset_url}</a></p>
                </div>
                
                <div class="footer">
                    <p>QuickMaps Team</p>
                    <p>This is an automated message, please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def get_password_reset_text(self, reset_url: str) -> str:
        """Get the plain text version for password reset email"""
        return f"""
QuickMaps - Password Reset

Hi there,

You requested a password reset for your QuickMaps account.

Click this link to reset your password:
{reset_url}

This link will expire in 1 hour for security.

If you did not request this reset, please ignore this email.

Best regards,
QuickMaps Team

This is an automated message, please do not reply.
        """
    
    def get_welcome_email_template(self, user_name: str = "there") -> str:
        """Get the HTML template for welcome email"""
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Welcome to {self.from_name}!</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
            <style>
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    margin: 0;
                    padding: 0;
                    background: linear-gradient(135deg, #090040 0%, #200080 100%);
                    min-height: 100vh;
                }}
                .email-wrapper {{
                    padding: 40px 20px;
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }}
                .container {{
                    max-width: 600px;
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                }}
                .header {{
                    background: #090040;
                    color: white;
                    text-align: center;
                    padding: 40px 30px;
                }}
                .brand-name {{
                    font-size: 28px;
                    font-weight: 700;
                    color: white;
                    margin-bottom: 10px;
                    letter-spacing: -0.5px;
                }}
                .tagline {{
                    font-size: 16px;
                    color: white;
                    opacity: 0.9;
                    margin: 0;
                    font-weight: 500;
                }}
                .content {{
                    padding: 40px 30px;
                    text-align: center;
                }}
                .greeting {{
                    font-size: 24px;
                    font-weight: 600;
                    color: #333;
                    margin-bottom: 20px;
                }}
                .message {{
                    font-size: 16px;
                    color: #666;
                    margin-bottom: 30px;
                    line-height: 1.7;
                }}
                .message p {{
                    margin-bottom: 15px;
                }}
                .button-container {{
                    margin: 30px 0;
                }}
                .button {{
                    display: inline-block;
                    background: #090040;
                    color: white !important;
                    text-decoration: none;
                    padding: 16px 32px;
                    border-radius: 10px;
                    font-weight: 600;
                    font-size: 16px;
                    box-shadow: 0 4px 15px rgba(9, 0, 64, 0.4);
                    transition: all 0.3s ease;
                }}
                .button:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 8px 25px rgba(9, 0, 64, 0.6);
                }}
                .features {{
                    background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
                    border-radius: 15px;
                    padding: 25px;
                    margin: 30px 0;
                    text-align: left;
                }}
                .features h3 {{
                    color: #090040;
                    font-size: 18px;
                    font-weight: 600;
                    margin-bottom: 15px;
                    text-align: center;
                }}
                .feature-list {{
                    list-style: none;
                    padding: 0;
                    margin: 0;
                }}
                .feature-list li {{
                    padding: 8px 0;
                    color: #555;
                    font-size: 15px;
                    display: flex;
                    align-items: center;
                }}
                .feature-list li::before {{
                    content: "✨";
                    margin-right: 10px;
                    font-size: 16px;
                }}
                .tips {{
                    background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
                    border-radius: 15px;
                    padding: 25px;
                    margin: 30px 0;
                    border-left: 4px solid #10b981;
                }}
                .tips h3 {{
                    color: #065f46;
                    font-size: 18px;
                    font-weight: 600;
                    margin-bottom: 15px;
                }}
                .tips p {{
                    color: #047857;
                    margin-bottom: 10px;
                    font-size: 15px;
                }}
                .footer {{
                    background: #f8fafc;
                    padding: 30px;
                    text-align: center;
                    border-top: 1px solid #e2e8f0;
                }}
                .footer-text {{
                    color: #64748b;
                    font-size: 14px;
                    margin: 5px 0;
                }}
                .social-links {{
                    margin: 20px 0;
                }}
                @media (max-width: 600px) {{
                    .email-wrapper {{
                        padding: 20px 10px;
                    }}
                    .container {{
                        border-radius: 15px;
                    }}
                    .content {{
                        padding: 30px 20px;
                    }}
                    .header {{
                        padding: 30px 20px;
                    }}
                    .greeting {{
                        font-size: 20px;
                    }}
                    .button {{
                        padding: 14px 28px;
                        font-size: 15px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-wrapper">
                <div class="container">
                    <div class="header">
                        <div class="brand-name">QuickMaps</div>
                        <p class="tagline">Transform your learning with AI-powered notes</p>
                    </div>
                    
                    <div class="content">
                        <div class="greeting">Welcome to QuickMaps, {user_name}! 🎉</div>
                        
                        <div class="message">
                            <p>We're thrilled to have you join our community of learners and note-takers!</p>
                            <p>QuickMaps is designed to help you organize your thoughts, create beautiful notes, and boost your productivity with AI-powered features.</p>
                            <p><strong>🎉 Great news!</strong> You're on the <strong>Free plan with 30 monthly credits</strong> to test the app. Each credit lets you upload videos, PDFs, or create AI-powered content!</p>
                        </div>
                        
                        <div class="button-container">
                            <a href="{self.frontend_url}" class="button" style="color: white !important;">Start Creating Notes</a>
                        </div>
                        
                        <div class="features">
                            <h3>🚀 What you can do with QuickMaps:</h3>
                            <ul class="feature-list">
                                <li>Create and organize beautiful notes</li>
                                <li>Use AI-powered features to enhance your content</li>
                                <li>Collaborate with others on shared projects</li>
                                <li>Access your notes from anywhere, anytime</li>
                                <li>Export and share your work easily</li>
                            </ul>
                        </div>
                        
                        <div class="tips">
                            <h3>💡 Quick Start Tips:</h3>
                            <p><strong>1.</strong> Start by creating your first note - it's as simple as clicking "New Note"</p>
                            <p><strong>2.</strong> Explore our AI features to enhance your content automatically</p>
                            <p><strong>3.</strong> Organize your notes with tags and folders for easy access</p>
                            <p><strong>4.</strong> Need help? Our support team is always here to assist you!</p>
                        </div>
                        
                        <div class="message">
                            <p>Ready to transform the way you take notes? Let's get started!</p>
                        </div>
                    </div>
                    
                    <div class="footer">
                        <p class="footer-text">This email was sent by <strong>QuickMaps</strong></p>
                        <p class="footer-text">Questions? Contact our support team - we're here to help!</p>
                        <div class="social-links">
                            <p class="footer-text">🌐 quickmaps.pro | 📧 support@quickmaps.pro</p>
                        </div>
                        <p class="footer-text">&copy; {datetime.now().year} QuickMaps. All rights reserved.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def get_welcome_email_text(self, user_name: str = "there") -> str:
        """Get the plain text version for welcome email"""
        return f"""
🎉 Welcome to QuickMaps, {user_name}!

We're thrilled to have you join our community of learners and note-takers!

QuickMaps is designed to help you organize your thoughts, create beautiful notes, and boost your productivity with AI-powered features.

🎉 Great news! You're on the Free plan with 30 MONTHLY CREDITS to test the app. Each credit lets you upload videos, PDFs, or create AI-powered content!

🚀 WHAT YOU CAN DO WITH QUICKMAPS:
✨ Create and organize beautiful notes
✨ Use AI-powered features to enhance your content  
✨ Collaborate with others on shared projects
✨ Access your notes from anywhere, anytime
✨ Export and share your work easily

💡 QUICK START TIPS:
1. Start by creating your first note - it's as simple as clicking "New Note"
2. Explore our AI features to enhance your content automatically
3. Organize your notes with tags and folders for easy access
4. Need help? Our support team is always here to assist you!

🌟 GET STARTED:
Visit: {self.frontend_url}

Ready to transform the way you take notes? Let's get started!

Questions? Contact our support team - we're here to help!

🌐 Visit us: quickmaps.pro
📧 Email us: support@quickmaps.pro

Best regards,
The QuickMaps Team

© {datetime.now().year} QuickMaps. All rights reserved.
Transform your learning with AI-powered notes.
        """

    async def send_welcome_email(self, email: str, user_name: str = None) -> bool:
        """Send welcome email to new user"""
        try:
            if not self.is_configured():
                logger.error("Resend service not configured")
                return False
            
            # Extract name from email if not provided
            if not user_name:
                user_name = email.split('@')[0].title()
            
            html_content = self.get_welcome_email_template(user_name)
            text_content = self.get_welcome_email_text(user_name)
            
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [email],
                "subject": f"Welcome to {self.from_name}! 🎉",
                "html": html_content,
                "text": text_content,
                "tags": [
                    {
                        "name": "category",
                        "value": "welcome"
                    }
                ]
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
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
    
    async def send_password_reset_email(self, email: str, reset_token: str) -> bool:
        """
        Send password reset email via Resend API
        
        Args:
            email: Recipient email address
            reset_token: Password reset token
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        if not self.is_configured():
            logger.error("Resend service is not configured")
            return False
        
        try:
            reset_url = f"{self.frontend_url}/reset-password?token={reset_token}"
            
            # Prepare email payload
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [email],
                "subject": f"Reset Your Password - {self.from_name}",
                "html": self.get_password_reset_template(reset_url),
                "text": self.get_password_reset_text(reset_url),
                "tags": [
                    {
                        "name": "category",
                        "value": "password_reset"
                    }
                ]
            }
            
            # Set headers
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Send email via Resend API
            response = requests.post(self.api_url, json=payload, headers=headers)
            
            if response.status_code == 200:
                response_data = response.json()
                email_id = response_data.get('id', 'unknown')
                logger.info(f"Password reset email sent successfully via Resend to: {email} (ID: {email_id})")
                return True
            else:
                logger.error(f"Resend API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send password reset email via Resend to {email}: {e}")
            return False
    
    async def send_welcome_email(self, email: str, user_name: str = None) -> bool:
        """
        Send welcome email to new users
        
        Args:
            email: Recipient email address
            user_name: User's name (optional)
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        if not self.is_configured():
            logger.error("Resend service is not configured")
            return False
        
        try:
            greeting = f"Hi {user_name}!" if user_name else "Hi there!"
            
            html_content = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Welcome to {self.from_name}!</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        margin: 0;
                        padding: 20px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        background: white;
                        border-radius: 16px;
                        overflow: hidden;
                        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
                    }}
                    .header {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        text-align: center;
                        padding: 40px 30px;
                    }}
                    .logo {{
                        font-size: 32px;
                        font-weight: bold;
                        margin-bottom: 10px;
                    }}
                    .content {{
                        padding: 40px 30px;
                    }}
                    .button {{
                        display: inline-block;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white !important;
                        text-decoration: none;
                        padding: 16px 32px;
                        border-radius: 10px;
                        font-weight: 600;
                        margin: 20px 0;
                    }}
                    .footer {{
                        background-color: #f9fafb;
                        padding: 30px;
                        text-align: center;
                        border-top: 1px solid #e5e7eb;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="logo">🗺️ {self.from_name}</div>
                        <p>Transform your learning with AI-powered mind maps</p>
                    </div>
                    <div class="content">
                        <h2>{greeting} Welcome to {self.from_name}! 🎉</h2>
                        <p>We're excited to have you on board! You're now ready to transform your learning experience with our AI-powered mind mapping tools.</p>
                        <p>Here's what you can do:</p>
                        <ul>
                            <li>📹 Upload videos and get instant mind maps</li>
                            <li>📄 Process PDFs and documents</li>
                            <li>🎯 Generate interactive quizzes</li>
                            <li>🔊 Create audio summaries</li>
                        </ul>
                        <div style="text-align: center;">
                            <a href="{self.frontend_url}" class="button">Start Creating Mind Maps</a>
                        </div>
                        <p>If you have any questions, don't hesitate to reach out to our support team at support@quickmaps.pro</p>
                    </div>
                    <div class="footer">
                        <p>© {datetime.now().year} {self.from_name}. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_content = f"""
Welcome to {self.from_name}! 🎉

{greeting}

We're excited to have you on board! You're now ready to transform your learning experience with our AI-powered mind mapping tools.

Here's what you can do:
- 📹 Upload videos and get instant mind maps
- 📄 Process PDFs and documents  
- 🎯 Generate interactive quizzes
- 🔊 Create audio summaries

Get started: {self.frontend_url}

If you have any questions, don't hesitate to reach out to our support team at support@quickmaps.pro

Best regards,
The {self.from_name} Team

© {datetime.now().year} {self.from_name}. All rights reserved.
            """
            
            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [email],
                "subject": f"Welcome to {self.from_name}! 🎉",
                "html": html_content,
                "text": text_content,
                "tags": [
                    {
                        "name": "category",
                        "value": "welcome"
                    }
                ]
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(self.api_url, json=payload, headers=headers)
            
            if response.status_code == 200:
                response_data = response.json()
                email_id = response_data.get('id', 'unknown')
                logger.info(f"Welcome email sent successfully via Resend to: {email} (ID: {email_id})")
                return True
            else:
                logger.error(f"Resend API error for welcome email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send welcome email via Resend to {email}: {e}")
            return False

    def send_otp_verification_email(self, user_email: str, otp_code: str, user_name: Optional[str] = None, expiry_minutes: Optional[int] = None, expiry_seconds: Optional[int] = 60) -> bool:
        """
        Send an email verification OTP via Resend.
        Either expiry_seconds or expiry_minutes can be provided. expiry_seconds takes precedence.
        Returns True on success.
        """
        try:
            if not self.is_configured():
                logger.error("Resend service is not configured")
                return False

            name = user_name or (user_email.split('@')[0].title() if user_email else "there")
            # Determine expiry label
            exp_seconds = expiry_seconds if isinstance(expiry_seconds, int) and expiry_seconds > 0 else None
            if exp_seconds is None:
                # fallback to minutes
                try:
                    mins = int(expiry_minutes) if expiry_minutes is not None else 10
                except Exception:
                    mins = 10
                exp_seconds = max(60, mins * 60)

            # Build email content
            subject = f"Your {self.from_name} verification code"
            html_content = f"""
            <!DOCTYPE html>
            <html lang=\"en\">
              <head>
                <meta charset=\"UTF-8\" />
                <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
                <title>Email Verification</title>
                <style>
                  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#f6f7fb; margin:0; padding:20px; color:#111827; }}
                  .container {{ max-width:520px; margin:0 auto; background:#ffffff; border-radius:16px; box-shadow:0 10px 25px rgba(0,0,0,0.08); overflow:hidden; }}
                  .header {{ background:linear-gradient(135deg,#090040 0%, #4c1d95 100%); color:#fff; padding:26px 22px; text-align:center; }}
                  .brand {{ font-weight:700; font-size:22px; letter-spacing:-0.2px; }}
                  .content {{ padding:26px 22px; }}
                  .greeting {{ font-size:18px; font-weight:600; margin:0 0 10px; }}
                  .message {{ font-size:15px; line-height:1.7; color:#374151; }}
                  .code {{ font-size:28px; font-weight:800; letter-spacing:6px; text-align:center; background:#f9fafb; border:1px solid #e5e7eb; border-radius:12px; padding:16px; margin:18px 0; color:#111827; }}
                  .footer {{ padding:16px 22px; font-size:12px; color:#6b7280; text-align:center; background:#f9fafb; border-top:1px solid #e5e7eb; }}
                </style>
              </head>
              <body>
                <div class=\"container\">
                  <div class=\"header\">
                    <div class=\"brand\">{self.from_name}</div>
                    <div style=\"opacity:.85; font-size:14px;\">Email verification</div>
                  </div>
                  <div class=\"content\">
                    <p class=\"greeting\">Hi {name},</p>
                    <p class=\"message\">Use the code below to verify your email address. This code expires in <strong>{int(exp_seconds)}</strong> seconds.</p>
                    <div class=\"code\">{otp_code}</div>
                    <p class=\"message\" style=\"text-align:center; color:#6b7280;\">If you didn't request this, you can safely ignore this email.</p>
                  </div>
                  <div class=\"footer\">© {datetime.now().year} {self.from_name}. All rights reserved.</div>
                </div>
              </body>
            </html>
            """
            text_content = (
                f"{self.from_name} — Email verification\n\n"
                f"Hi {name},\n\n"
                f"Your verification code is: {otp_code}\n"
                f"This code expires in {int(exp_seconds)} seconds.\n\n"
                f"If you didn't request this, you can ignore this email.\n"
            )

            payload = {
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [user_email],
                "subject": subject,
                "html": html_content,
                "text": text_content,
                "tags": [
                    {"name": "category", "value": "email_verification"},
                    {"name": "type", "value": "otp"}
                ]
            }
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            response = requests.post(self.api_url, json=payload, headers=headers)
            if response.status_code == 200:
                logger.info(f"OTP email sent via Resend to {user_email}")
                return True
            logger.error(f"Resend API error for OTP email: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            logger.error(f"Failed to send OTP verification email via Resend: {e}")
            return False

    async def send_low_credit_warning(self, email: str, user_name: str = None, current_credits: int = 0, plan: str = 'free') -> bool:
        """Send a low credit balance warning email via Resend with an upgrade button."""
        if not self.is_configured():
            logger.error("Resend service is not configured")
            return False
        try:
            name = user_name or (email.split('@')[0].title() if email else "there")
            upgrade_url = f"{self.frontend_url}/pricing?ref=low-credits"
            subject = f"Low credits: {current_credits} remaining — upgrade to keep generating"

            html_content = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="UTF-8" />
              <meta name="viewport" content="width=device-width, initial-scale=1.0" />
              <title>Low Credits Warning</title>
              <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#f6f7fb; margin:0; padding:20px; color:#111827; }}
                .container {{ max-width:600px; margin:0 auto; background:#ffffff; border-radius:16px; box-shadow:0 10px 25px rgba(0,0,0,0.08); overflow:hidden; }}
                .header {{ background:linear-gradient(135deg,#090040 0%, #4c1d95 100%); color:#fff; padding:28px 24px; text-align:center; }}
                .brand {{ font-weight:700; font-size:22px; letter-spacing:-0.2px; }}
                .content {{ padding:28px 24px; }}
                .greeting {{ font-size:18px; font-weight:600; margin:0 0 12px; }}
                .message {{ font-size:15px; line-height:1.7; color:#374151; }}
                .stat {{ background:#f3f4f6; border:1px solid #e5e7eb; border-radius:12px; padding:14px 16px; margin:16px 0; text-align:center; font-weight:600; color:#111827; }}
                .button-wrap {{ text-align:center; margin:24px 0 8px; }}
                .button {{ display:inline-block; text-decoration:none; background:#090040; color:#fff !important; padding:14px 22px; border-radius:10px; font-weight:700; box-shadow:0 6px 20px rgba(9,0,64,0.3); }}
                .footer {{ padding:18px 24px; font-size:12px; color:#6b7280; text-align:center; background:#f9fafb; border-top:1px solid #e5e7eb; }}
              </style>
            </head>
            <body>
              <div class="container">
                <div class="header">
                  <div class="brand">{self.from_name}</div>
                  <div style="opacity:.85; font-size:14px;">Credit balance reminder</div>
                </div>
                <div class="content">
                  <p class="greeting">Hi {name},</p>
                  <div class="message">
                    <p>Your current credit balance is running low.</p>
                  </div>
                  <div class="stat">Remaining credits: {current_credits}</div>
                  <div class="message">
                    <p>To avoid interruptions, upgrade your plan and continue generating notes and diagrams without downtime.</p>
                  </div>
                  <div class="button-wrap">
                    <a href="{upgrade_url}" class="button">Upgrade plan</a>
                  </div>
                  <div class="message" style="text-align:center; font-size:12px; color:#6b7280; margin-top:10px;">
                    or visit {self.frontend_url}/pricing
                  </div>
                </div>
                <div class="footer">
                  © {datetime.now().year} {self.from_name}. All rights reserved.
                </div>
              </div>
            </body>
            </html>
            """

            text_content = f"""
{self.from_name} — Low credits warning

Hi {name},

Your credit balance is running low.
Remaining credits: {current_credits}

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
                logger.info(f"Low credit email sent to {email}")
                return True
            logger.error(f"Resend API error for low credit email: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            logger.error(f"Failed to send low credit email to {email}: {e}")
            return False

# Create global instance
resend_service = ResendService()