import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import os
from typing import Optional
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Initialize logger
logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.sender_email = os.getenv("GMAIL_SENDER_EMAIL")
        self.sender_password = os.getenv("GMAIL_APP_PASSWORD")  # Use App Password, not regular password
        self.sender_name = os.getenv("GMAIL_SENDER_NAME", "QuickMind")
        
        # Validate configuration
        if not self.sender_email or not self.sender_password:
            logger.warning("Gmail SMTP configuration incomplete. Email functionality will be disabled.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("Gmail SMTP service initialized successfully")
    
    def create_welcome_email(self, recipient_email: str, recipient_name: str) -> MIMEMultipart:
        """Create a branded welcome email"""
        msg = MIMEMultipart('related')
        msg['From'] = f"{self.sender_name} <{self.sender_email}>"
        msg['To'] = recipient_email
        msg['Subject'] = f"Welcome to QuickMind, {recipient_name}! 🚀"
        
        # Create the HTML content
        html_content = self.get_welcome_email_template(recipient_name)
        
        # Create alternative container
        msg_alternative = MIMEMultipart('alternative')
        msg.attach(msg_alternative)
        
        # Create plain text version
        text_content = f"""
Welcome to QuickMind, {recipient_name}!

Thank you for joining QuickMind - the AI-powered mind mapping platform that transforms your videos and content into interactive mind maps.

Here's what you can do with QuickMind:
• Upload videos and get AI-generated mind maps
• Process YouTube videos directly
• Interactive mind map navigation
• Save and organize your mind maps
• Export in multiple formats

Ready to get started? Visit your dashboard: https://your-domain.com/dashboard

Best regards,
The QuickMind Team

---
Need help? Reply to this email or visit our support center.
        """
        
        # Attach parts
        msg_alternative.attach(MIMEText(text_content, 'plain'))
        msg_alternative.attach(MIMEText(html_content, 'html'))
        
        return msg
    
    def get_welcome_email_template(self, recipient_name: str) -> str:
        """Generate the branded HTML email template"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to QuickMind</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Inter', Arial, sans-serif;
            line-height: 1.6;
            color: #ffffff;
            background-color: #090040;
        }}
        
        .email-container {{
            max-width: 600px;
            margin: 0 auto;
            background: linear-gradient(135deg, #090040 0%, #1a0f5c 100%);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        }}
        
        .header {{
            background: #090040;
            padding: 40px 30px;
            text-align: center;
            position: relative;
        }}
        
        .header::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: radial-gradient(ellipse at center, rgba(255, 255, 255, 0.1) 0%, transparent 70%);
        }}
        
        .logo {{
            width: 80px;
            height: 80px;
            background: #ffffff;
            border-radius: 50%;
            margin: 0 auto 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            z-index: 1;
            padding: 10px;
            box-shadow: 0 8px 20px rgba(255, 255, 255, 0.2);
        }}
        
        .logo img {{
            width: 100%;
            height: 100%;
            object-fit: contain;
        }}
        
        .header h1 {{
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 10px;
            position: relative;
            z-index: 1;
            color: #ffffff;
        }}
        
        .header p {{
            font-size: 16px;
            opacity: 0.9;
            position: relative;
            z-index: 1;
            color: #ffffff;
        }}
        
        .content {{
            padding: 40px 30px;
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
        }}
        
        .welcome-text {{
            font-size: 18px;
            margin-bottom: 30px;
            text-align: center;
            color: #ffffff;
        }}
        
        .features {{
            margin: 30px 0;
        }}
        
        .feature {{
            display: flex;
            align-items: flex-start;
            margin-bottom: 20px;
            padding: 15px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}
        
        .feature-icon {{
            width: 24px;
            height: 24px;
            background: #ffffff;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 15px;
            flex-shrink: 0;
            font-weight: bold;
            color: #090040;
            font-size: 14px;
        }}
        
        .feature-text {{
            flex: 1;
        }}
        
        .feature-title {{
            font-weight: 600;
            margin-bottom: 5px;
            font-size: 16px;
            color: #ffffff;
        }}
        
        .feature-description {{
            opacity: 0.9;
            font-size: 14px;
            color: #ffffff;
        }}
        
        .cta-section {{
            text-align: center;
            margin: 40px 0 20px;
        }}
        
        .cta-button {{
            display: inline-block;
            background: #ffffff;
            color: #090040;
            padding: 16px 32px;
            border-radius: 50px;
            text-decoration: none;
            font-weight: 600;
            font-size: 16px;
            transition: all 0.3s ease;
            box-shadow: 0 10px 30px rgba(255, 255, 255, 0.2);
        }}
        
        .cta-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 15px 40px rgba(255, 255, 255, 0.3);
        }}
        
        .footer {{
            padding: 30px;
            text-align: center;
            background: #090040;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
        }}
        
        .footer p {{
            opacity: 0.8;
            font-size: 14px;
            margin-bottom: 10px;
            color: #ffffff;
        }}
        
        .social-links {{
            margin: 20px 0;
        }}
        
        .social-links a {{
            display: inline-block;
            width: 40px;
            height: 40px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 50%;
            margin: 0 10px;
            text-decoration: none;
            color: #ffffff;
            line-height: 40px;
            text-align: center;
            transition: all 0.3s ease;
        }}
        
        .social-links a:hover {{
            background: rgba(255, 255, 255, 0.2);
            transform: translateY(-2px);
        }}
        
        @media (max-width: 600px) {{
            .email-container {{
                margin: 10px;
                border-radius: 12px;
            }}
            
            .header, .content, .footer {{
                padding: 20px;
            }}
            
            .header h1 {{
                font-size: 24px;
            }}
            
            .feature {{
                flex-direction: column;
                text-align: center;
            }}
            
            .feature-icon {{
                margin: 0 auto 10px;
            }}
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <div class="logo">
                <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAfQAAAH0CAYAAADL1t+KAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAEv2lUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPD94cGFja2V0IGJlZ2luPSfvu78nIGlkPSdXNU0wTXBDZWhpSHpyZVN6TlRjemtjOWQnPz4KPHg6eG1wbWV0YSB4bWxuczp4PSdhZG9iZTpuczptZXRhLyc+CjxyZGY6UkRGIHhtbG5zOnJkZj0naHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyc+CgogPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9JycKICB4bWxuczpBdHRyaWI9J2h0dHA6Ly9ucy5hdHRyaWJ1dGlvbi5jb20vYWRzLzEuMC8nPgogIDxBdHRyaWI6QWRzPgogICA8cmRmOlNlcT4KICAgIDxyZGY6bGkgcmRmOnBhcnNlVHlwZT0nUmVzb3VyY2UnPgogICAgIDxBdHRyaWI6Q3JlYXRlZD4yMDI1LTA4LTAyPC9BdHRyaWI6Q3JlYXRlZD4KICAgICA8QXR0cmliOkV4dElkPjI5NWUyY2I0LTkyOWMtNDM4Yi1hNWUxLTg0NTU2MDJiZmQzMjwvQXR0cmliOkV4dElkPgogICAgIDxBdHRyaWI6RmJJZD41MjUyNjU5MTQxNzk1ODA8L0F0dHJpYjpGYklkPgogICAgIDxBdHRyaWI6VG91Y2hUeXBlPjI8L0F0dHJpYjpUb3VjaFR5cGU+CiAgICA8L3JkZjpsaT4KICAgPC9yZGY6U2VxPgogIDwvQXR0cmliOkFkcz4KIDwvcmRmOkRlc2NyaXB0aW9uPgoKIDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PScnCiAgeG1sbnM6ZGM9J2h0dHA6Ly9wdXJsLm9yZy9kYy9lbGVtZW50cy8xLjEvJz4KICA8ZGM6dGl0bGU+CiAgIDxyZGY6QWx0PgogICAgPHJkZjpsaSB4bWw6bGFuZz0neC1kZWZhdWx0Jz5Mb2dvSWNvbkJyYW5kZWQgLSAxPC9yZGY6bGk+CiAgIDwvcmRmOkFsdD4KICA8L2RjOnRpdGxlPgogPC9yZGY6RGVzY3JpcHRpb24+CgogPHJkZjpEZXNjcmlwdGlv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" alt="QuickMind Logo" />
            </div>
            <h1>Welcome to QuickMind!</h1>
            <p>Transform your content into interactive mind maps</p>
        </div>
        
        <div class="content">
            <div class="welcome-text">
                <strong>Hi {recipient_name},</strong><br><br>
                Thank you for joining QuickMind! We're excited to help you transform your videos and content into beautiful, interactive mind maps powered by AI.
            </div>
            
            <div class="features">
                <div class="feature">
                    <div class="feature-icon">🎥</div>
                    <div class="feature-text">
                        <div class="feature-title">Video Processing</div>
                        <div class="feature-description">Upload any video and get AI-generated mind maps in minutes</div>
                    </div>
                </div>
                
                <div class="feature">
                    <div class="feature-icon">📺</div>
                    <div class="feature-text">
                        <div class="feature-title">YouTube Integration</div>
                        <div class="feature-description">Process YouTube videos directly with just a URL</div>
                    </div>
                </div>
                
                <div class="feature">
                    <div class="feature-icon">🧠</div>
                    <div class="feature-text">
                        <div class="feature-title">Interactive Mind Maps</div>
                        <div class="feature-description">Navigate and interact with your content in new ways</div>
                    </div>
                </div>
                
                <div class="feature">
                    <div class="feature-icon">💾</div>
                    <div class="feature-text">
                        <div class="feature-title">Save & Export</div>
                        <div class="feature-description">Save your mind maps and export in multiple formats</div>
                    </div>
                </div>
            </div>
            
            <div class="cta-section">
                <a href="http://localhost:3000/dashboard" class="cta-button">
                    Get Started Now →
                </a>
            </div>
        </div>
        
        <div class="footer">
            <p>Ready to revolutionize how you process information?</p>
            
            <div class="social-links">
                <a href="#" title="Twitter">𝕏</a>
                <a href="#" title="LinkedIn">in</a>
                <a href="#" title="GitHub">🐱</a>
            </div>
            
            <p style="margin-top: 20px; font-size: 12px; opacity: 0.7;">
                Need help? Reply to this email or visit our support center.<br>
                © 2024 QuickMind. All rights reserved.
            </p>
        </div>
    </div>
</body>
</html>
        """
    
    async def send_welcome_email(self, recipient_email: str, recipient_name: str = "User") -> bool:
        """Send welcome email to new user"""
        if not self.enabled:
            logger.warning("Email service disabled. Skipping welcome email.")
            return False
        
        try:
            # Create message
            message = self.create_welcome_email(recipient_email, recipient_name)
            
            # Create secure connection and send email
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.sender_email, self.sender_password)
                
                text = message.as_string()
                server.sendmail(self.sender_email, recipient_email, text)
            
            logger.info(f"Welcome email sent successfully to {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send welcome email to {recipient_email}: {e}")
            return False
    
    async def send_custom_email(self, recipient_email: str, subject: str, html_content: str, 
                              text_content: Optional[str] = None) -> bool:
        """Send custom email"""
        if not self.enabled:
            logger.warning("Email service disabled. Skipping custom email.")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.sender_name} <{self.sender_email}>"
            msg['To'] = recipient_email
            msg['Subject'] = subject
            
            # Create text version if not provided
            if not text_content:
                # Simple HTML to text conversion
                import re
                text_content = re.sub('<[^<]+?>', '', html_content)
                text_content = re.sub(r'\s+', ' ', text_content).strip()
            
            # Attach parts
            msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.sender_email, self.sender_password)
                
                text = msg.as_string()
                server.sendmail(self.sender_email, recipient_email, text)
            
            logger.info(f"Custom email sent successfully to {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send custom email to {recipient_email}: {e}")
            return False

# Create global email service instance
email_service = EmailService()