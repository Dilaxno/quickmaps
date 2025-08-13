import os
import requests
import json
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class BrevoEmailService:
    def __init__(self):
        self.api_key = os.getenv('BREVO_API_KEY')
        self.sender_email = os.getenv('BREVO_SENDER_EMAIL')
        self.sender_name = os.getenv('BREVO_SENDER_NAME', 'QuickMaps')
        self.frontend_url = os.getenv('FRONTEND_URL', 'https://quickmaps.pro')
        if 'localhost' in self.frontend_url or '127.0.0.1' in self.frontend_url:
            self.frontend_url = 'https://quickmaps.pro'
        self.base_url = 'https://api.brevo.com/v3'
        
        # Debug logging
        logger.info(f"🔧 Brevo service initialization:")
        logger.info(f"  API Key configured: {'✅ Yes' if self.api_key else '❌ No'}")
        logger.info(f"  Sender Email: {self.sender_email if self.sender_email else '❌ Not set'}")
        logger.info(f"  Sender Name: {self.sender_name}")
        logger.info(f"  Frontend URL: {self.frontend_url}")
        
        if not self.api_key or not self.sender_email:
            logger.warning("Brevo credentials not configured. Email notifications will be disabled.")
        else:
            logger.info("✅ Brevo service configured successfully!")
    
    def is_configured(self) -> bool:
        """Check if Brevo service is properly configured"""
        return bool(self.api_key and self.sender_email)
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Brevo API requests"""
        return {
            'accept': 'application/json',
            'api-key': self.api_key,
            'content-type': 'application/json'
        }
    
    def send_new_device_alert(self, user_email: str, user_name: str, device_info: Dict[str, Any]) -> bool:
        """
        Send email alert when user logs in from a new device
        
        Args:
            user_email: User's email address
            user_name: User's display name
            device_info: Dictionary containing device information
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.api_key or not self.sender_email:
            logger.warning("Brevo not configured, skipping new device alert email")
            return False
        
        try:
            # Format device information
            device_name = device_info.get('device_name', 'Unknown Device')
            browser = device_info.get('browser', 'Unknown Browser')
            os_info = device_info.get('os', 'Unknown OS')
            ip_address = device_info.get('ip_address', 'Unknown IP')
            location = device_info.get('location', 'Unknown Location')
            login_time = device_info.get('login_time', datetime.now().isoformat())
            
            # Format login time for display
            try:
                login_dt = datetime.fromisoformat(login_time.replace('Z', '+00:00'))
                formatted_time = login_dt.strftime('%B %d, %Y at %I:%M %p UTC')
            except:
                formatted_time = login_time
            
            # Email content
            subject = "🔐 New Device Login Alert - Mindmaps"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>New Device Login Alert</title>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: white; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
                    .content {{ padding: 30px; }}
                    .alert-box {{ background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                    .device-info {{ background-color: #f8f9fa; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                    .info-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 8px 0; border-bottom: 1px solid #e9ecef; }}
                    .info-label {{ font-weight: 600; color: #495057; }}
                    .info-value {{ color: #6c757d; }}
                    .security-tips {{ background-color: #e7f3ff; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                    .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; color: #6c757d; font-size: 14px; }}
                    .btn {{ display: inline-block; padding: 12px 24px; background-color: #667eea; color: white; text-decoration: none; border-radius: 6px; margin: 10px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔐 New Device Login Detected</h1>
                        <p>We noticed a login from a new device</p>
                    </div>
                    
                    <div class="content">
                        <p>Hello {user_name},</p>
                        
                        <div class="alert-box">
                            <strong>⚠️ Security Alert:</strong> We detected a login to your Mindmaps account from a new device on {formatted_time}.
                        </div>
                        
                        <div class="device-info">
                            <h3>Device Information:</h3>
                            <div class="info-row">
                                <span class="info-label">Device:</span>
                                <span class="info-value">{device_name}</span>
                            </div>
                            <div class="info-row">
                                <span class="info-label">Browser:</span>
                                <span class="info-value">{browser}</span>
                            </div>
                            <div class="info-row">
                                <span class="info-label">Operating System:</span>
                                <span class="info-value">{os_info}</span>
                            </div>
                            <div class="info-row">
                                <span class="info-label">IP Address:</span>
                                <span class="info-value">{ip_address}</span>
                            </div>
                            <div class="info-row">
                                <span class="info-label">Location:</span>
                                <span class="info-value">{location}</span>
                            </div>
                            <div class="info-row">
                                <span class="info-label">Login Time:</span>
                                <span class="info-value">{formatted_time}</span>
                            </div>
                        </div>
                        
                        <p><strong>Was this you?</strong></p>
                        <p>If you recognize this login, no action is needed. This device has been added to your trusted devices.</p>
                        
                        <p><strong>Don't recognize this device?</strong></p>
                        <p>If this wasn't you, please secure your account immediately:</p>
                        
                        <div class="security-tips">
                            <h4>🛡️ Immediate Actions:</h4>
                            <ul>
                                <li>Change your password immediately</li>
                                <li>Review your account activity</li>
                                <li>Remove any unrecognized devices</li>
                                <li>Enable two-factor authentication if not already enabled</li>
                            </ul>
                        </div>
                        
                        <p style="text-align: center;">
                            <a href="https://mindmaps.com/profile-settings" class="btn">Manage Your Devices</a>
                        </p>
                        
                        <p>You can view and manage all your registered devices in your Profile Settings.</p>
                    </div>
                    
                    <div class="footer">
                        <p>This is an automated security notification from Mindmaps.</p>
                        <p>If you have any concerns, please contact our support team.</p>
                        <p>&copy; 2024 Mindmaps. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Plain text version
            text_content = f"""
            New Device Login Alert - Mindmaps
            
            Hello {user_name},
            
            We detected a login to your Mindmaps account from a new device on {formatted_time}.
            
            Device Information:
            - Device: {device_name}
            - Browser: {browser}
            - Operating System: {os_info}
            - IP Address: {ip_address}
            - Location: {location}
            - Login Time: {formatted_time}
            
            Was this you?
            If you recognize this login, no action is needed. This device has been added to your trusted devices.
            
            Don't recognize this device?
            If this wasn't you, please secure your account immediately:
            - Change your password immediately
            - Review your account activity
            - Remove any unrecognized devices
            - Enable two-factor authentication if not already enabled
            
            You can manage your devices at: https://mindmaps.com/profile-settings
            
            This is an automated security notification from Mindmaps.
            """
            
            # Prepare email data
            email_data = {
                "sender": {
                    "name": self.sender_name,
                    "email": self.sender_email
                },
                "to": [
                    {
                        "email": user_email,
                        "name": user_name
                    }
                ],
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_content,
                "tags": ["security", "device-alert", "login"]
            }
            
            # Send email
            response = requests.post(
                f"{self.base_url}/smtp/email",
                headers=self._get_headers(),
                data=json.dumps(email_data)
            )
            
            if response.status_code == 201:
                logger.info(f"New device alert email sent successfully to {user_email}")
                return True
            else:
                logger.error(f"Failed to send new device alert email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending new device alert email: {str(e)}")
            return False
    
    def send_device_removed_notification(self, user_email: str, user_name: str, device_info: Dict[str, Any]) -> bool:
        """
        Send email notification when a device is removed from account
        
        Args:
            user_email: User's email address
            user_name: User's display name
            device_info: Dictionary containing removed device information
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.api_key or not self.sender_email:
            logger.warning("Brevo not configured, skipping device removal notification")
            return False
        
        try:
            device_name = device_info.get('device_name', 'Unknown Device')
            removal_time = datetime.now().strftime('%B %d, %Y at %I:%M %p UTC')
            
            subject = "🔐 Device Removed from Your Account - Mindmaps"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Device Removed Notification</title>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: white; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
                    .content {{ padding: 30px; }}
                    .info-box {{ background-color: #e7f3ff; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                    .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; color: #6c757d; font-size: 14px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔐 Device Removed</h1>
                        <p>A device has been removed from your account</p>
                    </div>
                    
                    <div class="content">
                        <p>Hello {user_name},</p>
                        
                        <div class="info-box">
                            <p><strong>Device Removed:</strong> {device_name}</p>
                            <p><strong>Removal Time:</strong> {removal_time}</p>
                        </div>
                        
                        <p>This device will no longer have access to your Mindmaps account and will need to be re-registered if you want to use it again.</p>
                        
                        <p>If you didn't remove this device, please secure your account immediately by changing your password and reviewing your account activity.</p>
                    </div>
                    
                    <div class="footer">
                        <p>This is an automated security notification from Mindmaps.</p>
                        <p>&copy; 2024 Mindmaps. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_content = f"""
            Device Removed from Your Account - MindQuick
            
            Hello {user_name},
            
            A device has been removed from your MindQuick account:
            
            Device Removed: {device_name}
            Removal Time: {removal_time}
            
            This device will no longer have access to your account and will need to be re-registered if you want to use it again.
            
            If you didn't remove this device, please secure your account immediately by changing your password and reviewing your account activity.
            
            This is an automated security notification from Mindmaps.
            """
            
            email_data = {
                "sender": {
                    "name": self.sender_name,
                    "email": self.sender_email
                },
                "to": [
                    {
                        "email": user_email,
                        "name": user_name
                    }
                ],
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_content,
                "tags": ["security", "device-removal"]
            }
            
            response = requests.post(
                f"{self.base_url}/smtp/email",
                headers=self._get_headers(),
                data=json.dumps(email_data)
            )
            
            if response.status_code == 201:
                logger.info(f"Device removal notification sent successfully to {user_email}")
                return True
            else:
                logger.error(f"Failed to send device removal notification: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending device removal notification: {str(e)}")
            return False
    
    def send_welcome_email(self, user_email: str, user_name: str, welcome_credits: int = 10) -> bool:
        """
        Send a modern branded welcome email to new users with welcome credits information
        
        Args:
            user_email: User's email address
            user_name: User's display name
            welcome_credits: Number of welcome credits given to the user
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.api_key or not self.sender_email:
            logger.warning("Brevo not configured, skipping welcome email")
            return False
        
        try:
            current_year = datetime.now().year
            
            subject = f"🎉 Welcome to QuickMaps - Your {welcome_credits} Free Credits Are Ready!"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Welcome to QuickMaps</title>
                <style>
                    body {{ 
                        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; 
                        margin: 0; 
                        padding: 20px; 
                        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); 
                        line-height: 1.6;
                    }}
                    .container {{ 
                        max-width: 600px; 
                        margin: 0 auto; 
                        background-color: white; 
                        box-shadow: 0 10px 30px rgba(9, 0, 64, 0.1);
                        border-radius: 16px;
                        overflow: hidden;
                    }}
                    .header {{ 
                        background: linear-gradient(135deg, #090040 0%, #1a0f5c 100%); 
                        color: white; 
                        padding: 40px 30px; 
                        text-align: center; 
                        position: relative;
                    }}
                    .logo {{
                        margin-bottom: 20px;
                    }}
                    .logo img {{
                        height: 50px;
                        width: auto;
                        max-width: 200px;
                    }}
                    .header h1 {{ 
                        margin: 0; 
                        font-size: 32px; 
                        font-weight: 800; 
                        position: relative; 
                        z-index: 1;
                        color: #ffffff;
                        text-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }}
                    .header p {{ 
                        margin: 10px 0 0 0; 
                        font-size: 16px; 
                        opacity: 0.95; 
                        position: relative; 
                        z-index: 1;
                        color: #ffffff;
                    }}
                    .content {{ 
                        padding: 40px 30px; 
                    }}
                    .welcome-message {{ 
                        font-size: 20px; 
                        color: #090040; 
                        margin-bottom: 30px; 
                        text-align: center;
                        font-weight: 600;
                    }}
                    .credits-box {{ 
                        background: linear-gradient(135deg, #090040 0%, #1a0f5c 100%); 
                        color: white; 
                        border-radius: 12px; 
                        padding: 30px; 
                        text-align: center; 
                        margin: 30px 0; 
                        position: relative;
                        overflow: hidden;
                        box-shadow: 0 6px 20px rgba(9, 0, 64, 0.3);
                    }}
                    .credits-box::before {{
                        content: '🎁';
                        position: absolute;
                        top: -10px;
                        right: -10px;
                        font-size: 60px;
                        opacity: 0.2;
                    }}
                    .credits-amount {{ 
                        font-size: 48px; 
                        font-weight: 800; 
                        margin: 0; 
                        text-shadow: 0 2px 4px rgba(0,0,0,0.2);
                    }}
                    .credits-text {{ 
                        font-size: 20px; 
                        margin: 10px 0 0 0; 
                        opacity: 0.95;
                    }}
                    .features-grid {{ 
                        display: grid; 
                        grid-template-columns: 1fr 1fr; 
                        gap: 20px; 
                        margin: 30px 0; 
                    }}
                    .feature-card {{ 
                        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); 
                        border-radius: 12px; 
                        padding: 20px; 
                        text-align: center; 
                        border: 2px solid #e5e7eb;
                        transition: all 0.3s ease;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                    }}
                    .feature-card:hover {{
                        border-color: #090040;
                        transform: translateY(-3px);
                        box-shadow: 0 6px 15px rgba(9, 0, 64, 0.15);
                    }}
                    .feature-icon {{ 
                        font-size: 32px; 
                        margin-bottom: 10px; 
                        display: block;
                    }}
                    .feature-title {{ 
                        font-weight: 700; 
                        color: #090040; 
                        margin: 0 0 8px 0; 
                        font-size: 16px;
                    }}
                    .feature-desc {{ 
                        color: #6b7280; 
                        font-size: 14px; 
                        margin: 0;
                    }}
                    .cta-section {{ 
                        background: linear-gradient(135deg, #f9fafb 0%, #f1f5f9 100%); 
                        border-radius: 12px; 
                        padding: 30px; 
                        text-align: center; 
                        margin: 30px 0; 
                    }}
                    .cta-button {{ 
                        display: inline-block; 
                        background: linear-gradient(135deg, #090040 0%, #1a0f5c 100%); 
                        color: white; 
                        text-decoration: none; 
                        padding: 18px 36px; 
                        border-radius: 12px; 
                        font-weight: 700; 
                        font-size: 16px; 
                        margin: 15px 0; 
                        transition: all 0.3s ease;
                        box-shadow: 0 6px 20px rgba(9, 0, 64, 0.3);
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                    }}
                    .cta-button:hover {{
                        transform: translateY(-3px);
                        box-shadow: 0 8px 25px rgba(9, 0, 64, 0.4);
                    }}
                    .tips-section {{ 
                        background: linear-gradient(135deg, #e0f2fe 0%, #e7f3ff 100%); 
                        border-left: 4px solid #090040; 
                        border-radius: 12px; 
                        padding: 25px; 
                        margin: 30px 0; 
                        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                    }}
                    .tips-title {{ 
                        color: #090040; 
                        font-weight: 700; 
                        margin: 0 0 15px 0; 
                        font-size: 18px;
                    }}
                    .tips-list {{ 
                        color: #374151; 
                        margin: 0; 
                        padding-left: 20px;
                    }}
                    .tips-list li {{ 
                        margin-bottom: 8px; 
                    }}
                    .footer {{ 
                        background: linear-gradient(135deg, #090040 0%, #1a0f5c 100%); 
                        color: #e5e7eb; 
                        padding: 32px; 
                        text-align: center; 
                        font-size: 14px; 
                    }}
                    .footer-brand {{ 
                        color: white; 
                        font-weight: 800; 
                        font-size: 20px; 
                        margin-bottom: 10px;
                    }}
                    .social-links {{ 
                        margin: 20px 0; 
                    }}
                    .social-links a {{ 
                        color: #ffffff; 
                        text-decoration: none; 
                        margin: 0 15px; 
                        font-weight: 600;
                    }}
                    @media (max-width: 600px) {{
                        .features-grid {{ 
                            grid-template-columns: 1fr; 
                        }}
                        .header {{ 
                            padding: 30px 20px; 
                        }}
                        .content {{ 
                            padding: 30px 20px; 
                        }}
                        .header h1 {{ 
                            font-size: 28px; 
                        }}
                        .credits-amount {{ 
                            font-size: 40px; 
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🚀 Welcome to QuickMaps!</h1>
                        <p>🗺️ Transform your learning with AI-powered visual notes</p>
                    </div>
                    
                    <div class="content">
                        <div class="welcome-message">
                            <strong>Hi {user_name}!</strong><br>
                            We're thrilled to have you join our community of visual learners and mind mappers.
                        </div>
                        
                        <div class="credits-box">
                            <h2 class="credits-amount">{welcome_credits}</h2>
                            <p class="credits-text">Free Credits to Get You Started!</p>
                        </div>
                        
                        <p style="text-align: center; color: #495057; font-size: 16px;">
                            Your welcome credits have been automatically added to your account. 
                            Start exploring QuickMaps' powerful visual learning features right away!
                        </p>
                        
                        <div class="features-grid">
                            <div class="feature-card">
                                <span class="feature-icon">🎥</span>
                                <h3 class="feature-title">Video To Notes</h3>
                                <p class="feature-desc">Upload videos and get AI-generated visual notes and mind maps</p>
                            </div>
                            <div class="feature-card">
                                <span class="feature-icon">📄</span>
                                <h3 class="feature-title">PDF Mind Maps</h3>
                                <p class="feature-desc">Transform documents into beautiful visual learning maps</p>
                            </div>
                            <div class="feature-card">
                                <span class="feature-icon">🧠</span>
                                <h3 class="feature-title">Smart Quizzes</h3>
                                <p class="feature-desc">Generate interactive quizzes from your visual notes automatically</p>
                            </div>
                            <div class="feature-card">
                                <span class="feature-icon">🗺️</span>
                                <h3 class="feature-title">Visual Learning</h3>
                                <p class="feature-desc">Experience knowledge through beautiful, interactive mind maps</p>
                            </div>
                        </div>
                        
                        <div class="cta-section">
                            <h3 style="margin: 0 0 15px 0; color: #090040; font-weight: 700;">Ready to Transform Your Learning?</h3>
                            <p style="margin: 0 0 20px 0; color: #495057;">
                                Upload your first document or video and discover the power of visual learning with AI.
                            </p>
                            <a href="{self.frontend_url}" class="cta-button">🚀 Start Creating Maps</a>
                        </div>
                        
                        <div class="tips-section">
                            <h4 class="tips-title">💡 Pro Tips to Maximize Your Credits:</h4>
                            <ul class="tips-list">
                                <li>Start with shorter videos or documents to explore the visual features</li>
                                <li>Try the interactive quiz generation to test your knowledge</li>
                                <li>Save and organize your favorite visual notes and mind maps</li>
                                <li>Experiment with different content types to find your learning style</li>
                            </ul>
                        </div>
                        
                        <div style="text-align: center; margin: 30px 0; padding: 20px; background: linear-gradient(135deg, #e0f2fe 0%, #e7f3ff 100%); border-radius: 12px; border-left: 4px solid #090040;">
                            <p style="margin: 0; color: #090040; font-weight: 600;">
                                🎯 <strong>Need Help?</strong> Our support team is here to guide your visual learning journey.
                            </p>
                        </div>
                    </div>
                    
                    <div class="footer">
                        <div class="footer-brand">🗺️ QuickMaps</div>
                        <p>Creating amazing visual notes and mind maps with AI-powered intelligence.</p>
                        
                        <div class="social-links">
                            <a href="{self.frontend_url}/help">Help Center</a>
                            <a href="{self.frontend_url}/features">Features</a>
                            <a href="{self.frontend_url}/pricing">Pricing</a>
                        </div>
                        
                        <p style="margin: 20px 0 0 0; font-size: 12px;">
                            &copy; {current_year} QuickMaps. All rights reserved.<br>
                            You're receiving this email because you created a QuickMaps account.
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Plain text version
            text_content = f"""
            🗺️ QUICKMAPS - Welcome to Visual Learning!
            
            Hi {user_name}!
            
            We're thrilled to have you join our community of visual learners and mind mappers.
            
            🎉 WELCOME GIFT: {welcome_credits} FREE CREDITS!
            
            Your welcome credits have been automatically added to your account and you can start using QuickMaps right away!
            
            What you can create with QuickMaps:
            
            🎥 Video To Notes - Upload videos and get AI-generated visual notes and mind maps
            📄 PDF Mind Maps - Transform documents into beautiful visual learning maps
            🧠 Smart Quizzes - Generate interactive quizzes from your visual notes automatically
            🗺️ Visual Learning - Experience knowledge through beautiful, interactive mind maps
            
            💡 Pro Tips to Maximize Your Credits:
            • Start with shorter videos or documents to explore the visual features
            • Try the interactive quiz generation to test your knowledge  
            • Save and organize your favorite visual notes and mind maps
            • Experiment with different content types to find your learning style
            
            Ready to transform your learning? Visit: {self.frontend_url}
            
            Need help? Our support team is here to guide your visual learning journey.
            
            Welcome to the future of visual learning!
            The QuickMaps Team
            
            ---
            🗺️ QuickMaps - Creating amazing visual notes and mind maps with AI
            © {current_year} QuickMaps. All rights reserved.
            You're receiving this email because you created a QuickMaps account.
            """
            
            # Prepare email data
            email_data = {
                "sender": {
                    "name": self.sender_name,
                    "email": self.sender_email
                },
                "to": [
                    {
                        "email": user_email,
                        "name": user_name
                    }
                ],
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_content,
                "tags": ["welcome", "onboarding", "new-user", "credits"]
            }
            
            # Send email
            response = requests.post(
                f"{self.base_url}/smtp/email",
                headers=self._get_headers(),
                data=json.dumps(email_data)
            )
            
            if response.status_code == 201:
                logger.info(f"Welcome email sent successfully to {user_email}")
                return True
            else:
                logger.error(f"Failed to send welcome email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending welcome email: {str(e)}")
            return False

    def send_password_reset_email(self, user_email: str, reset_token: str, user_name: str = "there") -> bool:
        """
        Send password reset email via Brevo
        
        Args:
            user_email: User's email address
            reset_token: Password reset token
            user_name: User's display name
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.is_configured():
            logger.warning("Brevo not configured, skipping password reset email")
            return False
        
        try:
            reset_url = f"{self.frontend_url}/reset-password?token={reset_token}"
            subject = "Reset Your Password - QuickMaps"
            
            html_content = f"""
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
                        <p>Hi {user_name},</p>
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
            
            # Plain text version
            text_content = f"""
            QuickMaps - Password Reset
            
            Hi {user_name},
            
            You requested a password reset for your QuickMaps account.
            
            Click this link to reset your password:
            {reset_url}
            
            This link will expire in 1 hour for security.
            
            If you did not request this reset, please ignore this email.
            
            Best regards,
            QuickMaps Team
            
            This is an automated message, please do not reply.
            """
            
            # Prepare email data
            email_data = {
                "sender": {
                    "name": self.sender_name,
                    "email": self.sender_email
                },
                "to": [
                    {
                        "email": user_email,
                        "name": user_name
                    }
                ],
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_content,
                "tags": ["password-reset", "security", "authentication"]
            }
            
            # Send email
            response = requests.post(
                f"{self.base_url}/smtp/email",
                headers=self._get_headers(),
                data=json.dumps(email_data)
            )
            
            if response.status_code == 201:
                logger.info(f"Password reset email sent successfully to {user_email}")
                return True
            else:
                logger.error(f"Failed to send password reset email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending password reset email: {str(e)}")
            return False

    def send_otp_verification_email(self, user_email: str, otp_code: str, user_name: str = "there", expiry_minutes: int = 10) -> bool:
        """
        Send OTP verification email via Brevo
        
        Args:
            user_email: User's email address
            otp_code: OTP verification code
            user_name: User's display name
            expiry_minutes: How long the OTP is valid for
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.is_configured():
            logger.warning("Brevo not configured, skipping OTP verification email")
            return False
        
        try:
            logger.info(f"🔧 Preparing OTP email for {user_email} with code {otp_code}")
            verification_url = f"{self.frontend_url}/verify-email?email={user_email}&code={otp_code}"
            subject = "✅ Verify your email - QuickMaps"
            current_year = datetime.now().year
            logger.info(f"🔧 Variables prepared: url={verification_url}, year={current_year}")
            
            html_template = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Verify your email - QuickMaps</title>
                <link rel="preconnect" href="https://fonts.googleapis.com">
                <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
                <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
                <style>
                    body {
                        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                        color: #111827;
                        line-height: 1.6;
                    }
                    .container {
                        max-width: 600px;
                        margin: 0 auto;
                        background: #ffffff;
                        border-radius: 16px;
                        overflow: hidden;
                        box-shadow: 0 10px 30px rgba(9, 0, 64, 0.12);
                    }
                    .header {
                        background: linear-gradient(135deg, #090040 0%, #1a0f5c 100%);
                        color: #ffffff;
                        text-align: center;
                        padding: 36px 30px;
                        position: relative;
                    }
                    .brand {
                        font-size: 28px;
                        font-weight: 800;
                        margin: 8px 0 0 0;
                        letter-spacing: 0.2px;
                        text-shadow: 0 2px 4px rgba(0,0,0,0.12);
                    }
                    .tagline {
                        font-size: 14px;
                        opacity: 0.95;
                        margin: 6px 0 0 0;
                    }
                    .content {
                        padding: 32px 30px;
                    }
                    .greeting {
                        font-size: 20px;
                        font-weight: 700;
                        color: #090040;
                        margin: 0 0 12px 0;
                    }
                    .subtitle {
                        color: #495057;
                        margin: 0 0 24px 0;
                    }
                    .code-box {
                        display: block;
                        font-size: 36px;
                        font-weight: 800;
                        letter-spacing: 8px;
                        background: #f8fafc;
                        color: #090040;
                        padding: 18px 22px;
                        border-radius: 12px;
                        text-align: center;
                        border: 2px dashed rgba(9, 0, 64, 0.25);
                        box-shadow: inset 0 1px 0 rgba(255,255,255,0.6);
                        margin: 20px 0;
                    }
                    .button-container {
                        text-align: center;
                        margin: 28px 0 8px 0;
                    }
                    .button {
                        display: inline-block;
                        background: linear-gradient(135deg, #090040 0%, #1a0f5c 100%);
                        color: #ffffff !important;
                        text-decoration: none !important;
                        padding: 14px 28px;
                        border-radius: 10px;
                        font-weight: 700;
                        font-size: 14px;
                        box-shadow: 0 6px 18px rgba(9, 0, 64, 0.25);
                        transition: all 0.25s ease;
                    }
                    .button:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 10px 24px rgba(9, 0, 64, 0.35);
                    }
                    .note {
                        font-size: 12px;
                        color: #6b7280;
                        text-align: center;
                        margin-top: 12px;
                    }
                    .divider {
                        height: 1px;
                        background: #e5e7eb;
                        margin: 28px 0;
                    }
                    .footer {
                        background: linear-gradient(135deg, #f9fafb 0%, #f1f5f9 100%);
                        padding: 22px 28px;
                        text-align: center;
                        color: #6b7280;
                        font-size: 12px;
                    }
                    .footer a {
                        color: #090040;
                        text-decoration: none;
                        font-weight: 600;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="brand">QuickMaps</div>
                        <p class="tagline">AI-powered visual notes and mind maps</p>
                    </div>
                    <div class="content">
                        <p class="greeting">Hi {user_name},</p>
                        <p class="subtitle">Welcome to QuickMaps! Please verify your email address to activate your account.</p>
                        <div class="code-box">{otp_code}</div>
                        <div class="button-container">
                            <a href="{verification_url}" class="button">Verify Email Address</a>
                        </div>
                        <p class="note">This verification code expires in {expiry_minutes} minutes.</p>
                        <div class="divider"></div>
                        <p class="note">If you didn't create an account with QuickMaps, you can safely ignore this email.</p>
                    </div>
                    <div class="footer">
                        <p>© {current_year} QuickMaps. All rights reserved. <a href="https://quickmaps.pro">https://quickmaps.pro</a></p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            html_content = html_template.format(
                user_name=user_name,
                otp_code=otp_code,
                verification_url=verification_url,
                expiry_minutes=expiry_minutes,
                current_year=current_year
            )

            text_template = """
            QuickMaps - Email Verification
            
            Hi {user_name},
            
            Welcome to QuickMaps! Please verify your email address to activate your account.
            
            Your verification code is: {otp_code}
            
            Click this link to verify your email:
            {verification_url}
            
            This code expires in {expiry_minutes} minutes.
            
            If you didn't create an account with QuickMaps, you can safely ignore this email.
            
            Best regards,
            The QuickMaps Team
            https://quickmaps.pro
            """
            
            text_content = text_template.format(
                user_name=user_name,
                otp_code=otp_code,
                verification_url=verification_url,
                expiry_minutes=expiry_minutes
            )

            # Prepare email data
            logger.info(f"🔧 Preparing email data structure...")
            email_data = {
                "sender": {
                    "name": self.sender_name,
                    "email": self.sender_email
                },
                "to": [
                    {
                        "email": user_email,
                        "name": user_name
                    }
                ],
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_content,
                "tags": ["email-verification", "otp", "authentication"]
            }
            logger.info(f"🔧 Email data prepared successfully")
            
            # Send email
            response = requests.post(
                f"{self.base_url}/smtp/email",
                headers=self._get_headers(),
                json=email_data
            )
            
            if response.status_code == 201:
                logger.info(f"OTP verification email sent successfully to {user_email}")
                return True
            else:
                logger.error(f"Failed to send OTP verification email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending OTP verification email: {str(e)}")
            return False

# Global instance
brevo_service = BrevoEmailService()