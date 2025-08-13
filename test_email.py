#!/usr/bin/env python3
"""
Test script to verify email sending functionality
"""
import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_brevo_config():
    """Test Brevo configuration"""
    logger.info("🔧 Testing Brevo Configuration...")
    
    api_key = os.getenv('BREVO_API_KEY')
    sender_email = os.getenv('BREVO_SENDER_EMAIL')
    sender_name = os.getenv('BREVO_SENDER_NAME')
    frontend_url = os.getenv('FRONTEND_URL')
    
    logger.info(f"BREVO_API_KEY: {'✅ Set' if api_key else '❌ Missing'}")
    logger.info(f"BREVO_SENDER_EMAIL: {sender_email if sender_email else '❌ Missing'}")
    logger.info(f"BREVO_SENDER_NAME: {sender_name if sender_name else '❌ Missing'}")
    logger.info(f"FRONTEND_URL: {frontend_url if frontend_url else '❌ Missing'}")
    
    if api_key:
        logger.info(f"API Key starts with: {api_key[:10]}...")
    
    return bool(api_key and sender_email)

def test_brevo_service():
    """Test Brevo service initialization"""
    logger.info("🔧 Testing Brevo Service...")
    
    try:
        from brevo_service import brevo_service
        logger.info(f"Brevo service configured: {brevo_service.is_configured()}")
        return brevo_service.is_configured()
    except Exception as e:
        logger.error(f"Error importing brevo_service: {e}")
        return False

def test_email_verification_service():
    """Test email verification service"""
    logger.info("🔧 Testing Email Verification Service...")
    
    try:
        from email_verification_service import email_verification_service
        
        # Test with a safe email address
        test_email = "test@example.com"
        logger.info(f"Testing OTP generation and send to: {test_email}")
        
        # This will attempt to send but won't actually deliver to test@example.com
        result = email_verification_service.create_and_send(test_email, "Test User")
        logger.info(f"Result: {result}")
        
        return result.get('success', False)
    except Exception as e:
        logger.error(f"Error testing email verification service: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Starting Email Service Tests...")
    
    # Test 1: Environment variables
    config_ok = test_brevo_config()
    if not config_ok:
        logger.error("❌ Brevo configuration is missing!")
        return False
    
    # Test 2: Brevo service
    service_ok = test_brevo_service()
    if not service_ok:
        logger.error("❌ Brevo service is not properly configured!")
        return False
    
    # Test 3: Email verification service
    email_ok = test_email_verification_service()
    if not email_ok:
        logger.error("❌ Email verification service failed!")
        return False
    
    logger.info("✅ All email service tests passed!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)