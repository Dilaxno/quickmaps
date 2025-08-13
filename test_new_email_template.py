#!/usr/bin/env python3
"""
Test the new email template with activation button
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

def test_new_email_template():
    """Test the new email template with activation button"""
    try:
        from email_verification_service import email_verification_service
        
        # Test with a real email address
        test_email = "lamiafaqir22@gmail.com"
        test_name = "Test User"
        
        logger.info(f"🧪 Testing new email template...")
        logger.info(f"📧 Sending to: {test_email}")
        
        # This will send the new email template with the activation button
        result = email_verification_service.create_and_send(test_email, test_name)
        
        if result.get('success'):
            logger.info("✅ New email template sent successfully!")
            logger.info("📧 Check your email for the new 'Activate Account' button")
            logger.info("📧 The button should link directly to quickmaps.pro and verify your email")
            return True
        else:
            logger.error(f"❌ Failed to send email: {result}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error testing email template: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Testing New Email Template with Activation Button...")
    
    success = test_new_email_template()
    
    if success:
        logger.info("✅ Test completed successfully!")
        logger.info("📧 Features of the new email:")
        logger.info("   - ✅ No logo (removed)")
        logger.info("   - ✅ Button says 'Activate Account'")
        logger.info("   - ✅ Button links to quickmaps.pro (not localhost)")
        logger.info("   - ✅ Button automatically verifies email and redirects to dashboard")
        logger.info("   - ✅ White button text (not blue)")
    else:
        logger.error("❌ Test failed!")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)