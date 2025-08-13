#!/usr/bin/env python3
"""
Simple email test to verify Brevo API works
"""
import os
import sys
import logging
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def send_simple_test_email():
    """Send a very simple test email"""
    
    api_key = os.getenv('BREVO_API_KEY')
    sender_email = os.getenv('BREVO_SENDER_EMAIL')
    sender_name = os.getenv('BREVO_SENDER_NAME', 'QuickMaps')
    
    if not api_key or not sender_email:
        logger.error("❌ Missing Brevo configuration")
        return False
    
    # Replace with your actual email for testing
    test_email = "lamiafaqir22@gmail.com"  # CHANGE THIS!
    
    # Very simple email
    email_data = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": test_email, "name": "Test User"}],
        "subject": "Test Email from QuickMaps",
        "htmlContent": """
        <html>
        <body>
            <h1>Test Email</h1>
            <p>This is a simple test email from QuickMaps.</p>
            <p>Your OTP code would be: <strong>123456</strong></p>
            <p>Visit: <a href="https://quickmaps.pro">https://quickmaps.pro</a></p>
        </body>
        </html>
        """,
        "textContent": "Test Email\n\nThis is a simple test email from QuickMaps.\nYour OTP code would be: 123456\nVisit: https://quickmaps.pro"
    }
    
    headers = {
        'accept': 'application/json',
        'api-key': api_key,
        'content-type': 'application/json'
    }
    
    logger.info(f"📧 Sending simple test email...")
    logger.info(f"📧 From: {sender_name} <{sender_email}>")
    logger.info(f"📧 To: {test_email}")
    logger.info(f"📧 API Key: {api_key[:10]}...")
    
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers=headers,
            json=email_data,
            timeout=30
        )
        
        logger.info(f"📧 Status Code: {response.status_code}")
        
        if response.status_code == 201:
            result = response.json()
            logger.info(f"✅ Email sent successfully!")
            logger.info(f"📧 Message ID: {result.get('messageId', 'N/A')}")
            return True
        else:
            logger.error(f"❌ Failed to send email")
            logger.error(f"❌ Status: {response.status_code}")
            logger.error(f"❌ Response: {response.text}")
            
            # Try to parse error details
            try:
                error_data = response.json()
                logger.error(f"❌ Error details: {error_data}")
            except:
                pass
            
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ Request timed out")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Request error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False

def check_brevo_account():
    """Check Brevo account status"""
    api_key = os.getenv('BREVO_API_KEY')
    
    if not api_key:
        logger.error("❌ No API key found")
        return False
    
    headers = {
        'accept': 'application/json',
        'api-key': api_key
    }
    
    try:
        # Check account info
        response = requests.get(
            "https://api.brevo.com/v3/account",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            account_info = response.json()
            logger.info(f"✅ Brevo account active")
            logger.info(f"📧 Email: {account_info.get('email', 'N/A')}")
            
            # Handle plan info safely
            plan_info = account_info.get('plan', {})
            if isinstance(plan_info, dict):
                logger.info(f"📧 Plan: {plan_info.get('type', 'N/A')}")
                logger.info(f"📧 Credits remaining: {plan_info.get('creditsRemaining', 'N/A')}")
            else:
                logger.info(f"📧 Plan info: {plan_info}")
            
            return True
        else:
            logger.error(f"❌ Account check failed: {response.status_code}")
            logger.error(f"❌ Response: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Account check error: {e}")
        return False

def main():
    """Main function"""
    logger.info("🚀 Starting Brevo Email Test...")
    
    # Step 1: Check account
    logger.info("\n📋 Step 1: Checking Brevo account...")
    account_ok = check_brevo_account()
    
    if not account_ok:
        logger.error("❌ Account check failed. Cannot proceed.")
        return False
    
    # Step 2: Send test email
    logger.info("\n📧 Step 2: Sending test email...")
    logger.warning("⚠️  IMPORTANT: Update 'test_email' variable with your actual email address!")
    
    email_sent = send_simple_test_email()
    
    if email_sent:
        logger.info("\n✅ Test completed successfully!")
        logger.info("📧 Check your email inbox (and spam folder)")
        logger.info("📧 If you don't receive it, check:")
        logger.info("   - Email address is correct")
        logger.info("   - Brevo sender domain is verified")
        logger.info("   - Email isn't in spam/junk folder")
    else:
        logger.error("\n❌ Test failed!")
        logger.error("📧 Check the error messages above")
    
    return email_sent

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)