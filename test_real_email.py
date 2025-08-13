#!/usr/bin/env python3
"""
Test script to send a real OTP email
"""
import os
import sys
import logging
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_brevo_api_directly():
    """Test Brevo API directly without Firebase"""
    import requests
    
    api_key = os.getenv('BREVO_API_KEY')
    sender_email = os.getenv('BREVO_SENDER_EMAIL')
    sender_name = os.getenv('BREVO_SENDER_NAME', 'QuickMaps')
    frontend_url = os.getenv('FRONTEND_URL', 'https://quickmaps.pro')
    
    if not api_key or not sender_email:
        logger.error("Missing Brevo configuration")
        return False
    
    # Test email data
    test_email = "your-test-email@gmail.com"  # Replace with your actual email
    test_code = "123456"
    test_name = "Test User"
    
    # Create email template
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verify your email - QuickMaps</title>
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
            .brand-title { 
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
            }
            .button-container { 
                text-align: center; 
                margin: 28px 0 8px 0; 
            }
            .button {
                display: inline-block;
                background: #090040;
                color: #ffffff !important;
                text-decoration: none !important;
                padding: 14px 28px;
                border-radius: 10px;
                font-weight: 700;
                font-size: 14px;
                box-shadow: 0 6px 18px rgba(9, 0, 64, 0.25);
                transition: all 0.25s ease;
                border: 1px solid rgba(255,255,255,0.3);
            }
            .button * {
                color: #ffffff !important;
                text-decoration: none !important;
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
                <div class="brand-title">QuickMaps</div>
                <p class="tagline">AI-powered visual notes and mind maps</p>
            </div>
            <div class="content">
                <p class="greeting">Hi {name},</p>
                <p class="subtitle">Use this one-time verification code to complete your sign up. It expires in 10 minutes.</p>
                <span class="code-box">{code}</span>
                <div class="button-container">
                    <a href="{frontend_url}" class="button">Open QuickMaps</a>
                </div>
                <div class="divider"></div>
                <p class="note">If you didn't request this, you can safely ignore this email.</p>
            </div>
            <div class="footer">
                <p>© 2025 QuickMaps. All rights reserved. <a href="{frontend_url}">{frontend_url}</a></p>
            </div>
        </div>
    </body>
    </html>
    """
    
    html_content = html_template.format(
        name=test_name,
        code=test_code,
        frontend_url=frontend_url
    )
    
    text_content = f"Your QuickMaps verification code is: {test_code}\nThis code expires in 10 minutes. If you didn't request it, ignore this email."
    
    email_data = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": test_email, "name": test_name}],
        "subject": "✅ Verify your email - QuickMaps",
        "htmlContent": html_content,
        "textContent": text_content,
        "tags": ["email-verification", "otp", "test"]
    }
    
    headers = {
        'accept': 'application/json',
        'api-key': api_key,
        'content-type': 'application/json'
    }
    
    logger.info(f"📧 Sending test email to: {test_email}")
    logger.info(f"📧 Using sender: {sender_name} <{sender_email}>")
    logger.info(f"📧 Frontend URL: {frontend_url}")
    
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers=headers,
            json=email_data,
            timeout=30
        )
        
        logger.info(f"📧 Response status: {response.status_code}")
        logger.info(f"📧 Response headers: {dict(response.headers)}")
        
        if response.status_code == 201:
            logger.info("✅ Email sent successfully!")
            logger.info(f"📧 Response: {response.json()}")
            return True
        else:
            logger.error(f"❌ Email failed: {response.status_code}")
            logger.error(f"❌ Response: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Exception: {e}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Testing direct Brevo API call...")
    
    # IMPORTANT: Replace with your actual email address
    logger.warning("⚠️  Make sure to replace 'your-test-email@gmail.com' with your actual email!")
    
    success = test_brevo_api_directly()
    
    if success:
        logger.info("✅ Test completed successfully! Check your email.")
    else:
        logger.error("❌ Test failed!")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)