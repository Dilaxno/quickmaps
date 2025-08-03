#!/usr/bin/env python3
"""
Test script for Gmail SMTP email functionality
"""

import asyncio
import os
from dotenv import load_dotenv
from utils.email_service import email_service

# Load environment variables
load_dotenv()

async def test_email_service():
    """Test the email service configuration and sending capability"""
    
    print("🧪 Testing Gmail SMTP Email Service")
    print("=" * 50)
    
    # Check configuration
    print(f"📧 SMTP Server: {email_service.smtp_server}:{email_service.smtp_port}")
    print(f"📧 Sender Email: {email_service.sender_email}")
    print(f"📧 Sender Name: {email_service.sender_name}")
    print(f"📧 Service Enabled: {email_service.enabled}")
    
    if not email_service.enabled:
        print("\n❌ Email service is not enabled!")
        print("Please check your Gmail SMTP configuration in .env file:")
        print("- GMAIL_SENDER_EMAIL")
        print("- GMAIL_APP_PASSWORD")
        print("- GMAIL_SENDER_NAME")
        return False
    
    print("\n📝 Gmail SMTP Configuration Instructions:")
    print("1. Enable 2-Factor Authentication on your Gmail account")
    print("2. Generate an App Password:")
    print("   - Go to Google Account settings")
    print("   - Security > 2-Step Verification > App passwords")
    print("   - Generate password for 'Mail' application")
    print("3. Update .env file with your Gmail address and App Password")
    
    # Ask user for test email
    test_email = input("\n📬 Enter test email address (or press Enter to skip): ").strip()
    
    if test_email:
        test_name = input("👤 Enter test name (optional): ").strip() or "Test User"
        
        print(f"\n📤 Sending welcome email to {test_email}...")
        
        try:
            success = await email_service.send_welcome_email(test_email, test_name)
            
            if success:
                print("✅ Welcome email sent successfully!")
                print("📧 Check your inbox (and spam folder)")
                return True
            else:
                print("❌ Failed to send welcome email")
                print("Check the logs above for error details")
                return False
                
        except Exception as e:
            print(f"❌ Exception occurred: {e}")
            return False
    else:
        print("⏭️  Skipping email test")
        return True

async def test_custom_email():
    """Test custom email sending"""
    
    if not email_service.enabled:
        print("❌ Email service not enabled, skipping custom email test")
        return False
    
    test_email = input("\n📬 Enter email for custom email test (or press Enter to skip): ").strip()
    
    if test_email:
        print(f"\n📤 Sending custom test email to {test_email}...")
        
        html_content = """
        <html>
        <body style="font-family: Arial, sans-serif; background-color: #090040; color: white; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #090040 0%, #1a0f5c 100%); padding: 30px; border-radius: 16px;">
                <h1 style="color: white; text-align: center;">🧪 Email Service Test</h1>
                <p>This is a test email from QuickMind's email service.</p>
                <p>If you received this, the Gmail SMTP integration is working correctly!</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="#" style="background: white; color: #090040; padding: 15px 30px; text-decoration: none; border-radius: 50px; font-weight: bold;">Test Button</a>
                </div>
                <p style="text-align: center; opacity: 0.8; font-size: 14px;">© 2024 QuickMind</p>
            </div>
        </body>
        </html>
        """
        
        try:
            success = await email_service.send_custom_email(
                recipient_email=test_email,
                subject="🧪 QuickMind Email Service Test",
                html_content=html_content
            )
            
            if success:
                print("✅ Custom email sent successfully!")
                return True
            else:
                print("❌ Failed to send custom email")
                return False
                
        except Exception as e:
            print(f"❌ Exception occurred: {e}")
            return False
    else:
        print("⏭️  Skipping custom email test")
        return True

async def main():
    """Main test function"""
    print("🚀 QuickMind Email Service Test Suite")
    print("=====================================\n")
    
    # Test basic service
    service_ok = await test_email_service()
    
    if service_ok:
        # Test custom email
        await test_custom_email()
    
    print("\n🏁 Email service testing completed!")
    print("\nNext Steps:")
    print("1. Update your .env file with correct Gmail credentials")
    print("2. Test the signup process to verify welcome emails")
    print("3. Check email logs in the backend console")

if __name__ == "__main__":
    asyncio.run(main())