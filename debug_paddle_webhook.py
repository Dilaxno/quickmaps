#!/usr/bin/env python3
"""
Paddle Webhook Debug Tool
Helps diagnose why webhooks aren't being triggered from Paddle sandbox
"""

import os
import json
import requests
import logging
from datetime import datetime
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
WEBHOOK_URL = "http://localhost:8000/webhook/paddle"
TEST_WEBHOOK_URL = "http://localhost:8000/webhook/test"

def check_environment_variables():
    """Check if all required environment variables are set"""
    logger.info("🔍 Checking environment variables...")
    
    required_vars = [
        "PADDLE_WEBHOOK_SECRET",
        "FIREBASE_PROJECT_ID",
        "GOOGLE_APPLICATION_CREDENTIALS_JSON"
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            logger.info(f"✅ {var}: {'*' * min(len(value), 20)}... (length: {len(value)})")
        else:
            logger.warning(f"❌ {var}: Not set")
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        return False
    else:
        logger.info("✅ All required environment variables are set")
        return True

def check_webhook_endpoint():
    """Check if webhook endpoint is accessible"""
    logger.info("🔍 Checking webhook endpoint accessibility...")
    
    try:
        # Test the test endpoint first
        response = requests.get(TEST_WEBHOOK_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            logger.info("✅ Webhook test endpoint is accessible")
            logger.info(f"🔥 Firebase available: {data.get('firebase_available', False)}")
            return True
        else:
            logger.error(f"❌ Webhook test endpoint returned {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Cannot reach webhook endpoint: {e}")
        return False

def check_public_accessibility():
    """Check if webhook is publicly accessible (for Paddle to reach it)"""
    logger.info("🔍 Checking public accessibility...")
    
    # Check if running on localhost
    if "localhost" in WEBHOOK_URL or "127.0.0.1" in WEBHOOK_URL:
        logger.warning("⚠️ CRITICAL ISSUE FOUND!")
        logger.warning("🚨 Your webhook URL is localhost/127.0.0.1")
        logger.warning("🚨 Paddle CANNOT reach localhost URLs from their servers!")
        logger.warning("")
        logger.warning("💡 SOLUTIONS:")
        logger.warning("1. Use ngrok to create a public tunnel:")
        logger.warning("   - Install ngrok: https://ngrok.com/")
        logger.warning("   - Run: ngrok http 8000")
        logger.warning("   - Use the ngrok URL in Paddle webhook settings")
        logger.warning("")
        logger.warning("2. Deploy to a public server (Heroku, Railway, etc.)")
        logger.warning("")
        logger.warning("3. Use a service like localtunnel:")
        logger.warning("   - npm install -g localtunnel")
        logger.warning("   - lt --port 8000")
        logger.warning("")
        return False
    else:
        logger.info("✅ Webhook URL appears to be publicly accessible")
        return True

def check_paddle_webhook_configuration():
    """Provide guidance on Paddle webhook configuration"""
    logger.info("🔍 Checking Paddle webhook configuration...")
    
    logger.info("")
    logger.info("📋 PADDLE WEBHOOK CONFIGURATION CHECKLIST:")
    logger.info("=" * 50)
    logger.info("1. Log into your Paddle Dashboard (sandbox)")
    logger.info("2. Go to Developer Tools > Webhooks")
    logger.info("3. Check if webhook endpoint is configured:")
    logger.info(f"   URL: {WEBHOOK_URL.replace('localhost', 'YOUR_PUBLIC_URL')}")
    logger.info("4. Ensure these events are enabled:")
    logger.info("   ✓ transaction.completed")
    logger.info("   ✓ transaction.paid")
    logger.info("   ✓ subscription.activated")
    logger.info("   ✓ subscription.updated")
    logger.info("   ✓ subscription.canceled")
    logger.info("5. Webhook secret should match your environment variable")
    logger.info("")

def check_firewall_and_ports():
    """Check firewall and port configuration"""
    logger.info("🔍 Checking firewall and port configuration...")
    
    logger.info("🔥 FIREWALL & PORT CHECKLIST:")
    logger.info("=" * 40)
    logger.info("1. Ensure port 8000 is open and accessible")
    logger.info("2. Check Windows Firewall settings")
    logger.info("3. Check router/network firewall")
    logger.info("4. If using cloud hosting, check security groups")
    logger.info("")

def provide_debugging_steps():
    """Provide step-by-step debugging guide"""
    logger.info("")
    logger.info("🛠️ DEBUGGING STEPS:")
    logger.info("=" * 50)
    logger.info("")
    logger.info("STEP 1: Make your webhook publicly accessible")
    logger.info("-----------------------------------------------")
    logger.info("Option A - Using ngrok (Recommended):")
    logger.info("1. Download ngrok from https://ngrok.com/")
    logger.info("2. Run: ngrok http 8000")
    logger.info("3. Copy the https URL (e.g., https://abc123.ngrok.io)")
    logger.info("4. Update Paddle webhook URL to: https://abc123.ngrok.io/webhook/paddle")
    logger.info("")
    logger.info("Option B - Using localtunnel:")
    logger.info("1. Install: npm install -g localtunnel")
    logger.info("2. Run: lt --port 8000")
    logger.info("3. Use the provided URL in Paddle")
    logger.info("")
    logger.info("STEP 2: Configure Paddle webhook")
    logger.info("--------------------------------")
    logger.info("1. Go to Paddle Dashboard > Developer Tools > Webhooks")
    logger.info("2. Add new webhook endpoint")
    logger.info("3. URL: https://your-public-url.com/webhook/paddle")
    logger.info("4. Select events: transaction.completed, subscription.activated")
    logger.info("5. Save the webhook secret to your environment variables")
    logger.info("")
    logger.info("STEP 3: Test the webhook")
    logger.info("------------------------")
    logger.info("1. Make a test payment in Paddle sandbox")
    logger.info("2. Check your application logs for webhook calls")
    logger.info("3. Use Paddle's webhook testing tool to send test events")
    logger.info("")

def create_ngrok_setup_script():
    """Create a script to help set up ngrok"""
    script_content = '''@echo off
echo Setting up ngrok for Paddle webhook testing...
echo.
echo 1. Make sure ngrok is installed from https://ngrok.com/
echo 2. Make sure your FastAPI server is running on port 8000
echo.
pause
echo Starting ngrok tunnel...
ngrok http 8000
'''
    
    try:
        with open("setup_ngrok.bat", "w") as f:
            f.write(script_content)
        logger.info("✅ Created setup_ngrok.bat script for easy ngrok setup")
    except Exception as e:
        logger.warning(f"⚠️ Could not create ngrok setup script: {e}")

async def run_comprehensive_debug():
    """Run comprehensive debugging"""
    logger.info("🚀 Starting Paddle Webhook Debug Analysis...")
    logger.info("=" * 60)
    
    issues_found = []
    
    # Check 1: Environment variables
    if not check_environment_variables():
        issues_found.append("Missing environment variables")
    
    # Check 2: Webhook endpoint
    if not check_webhook_endpoint():
        issues_found.append("Webhook endpoint not accessible")
    
    # Check 3: Public accessibility
    if not check_public_accessibility():
        issues_found.append("Webhook not publicly accessible")
    
    # Check 4: Paddle configuration
    check_paddle_webhook_configuration()
    
    # Check 5: Firewall and ports
    check_firewall_and_ports()
    
    # Provide debugging steps
    provide_debugging_steps()
    
    # Create helper script
    create_ngrok_setup_script()
    
    # Summary
    logger.info("")
    logger.info("🎯 DIAGNOSIS SUMMARY:")
    logger.info("=" * 30)
    
    if issues_found:
        logger.error(f"❌ Issues found: {len(issues_found)}")
        for i, issue in enumerate(issues_found, 1):
            logger.error(f"   {i}. {issue}")
        logger.info("")
        logger.info("🔧 MOST LIKELY CAUSE:")
        if "Webhook not publicly accessible" in issues_found:
            logger.warning("🚨 Your webhook is running on localhost - Paddle cannot reach it!")
            logger.warning("🚨 Use ngrok or deploy to a public server")
        else:
            logger.warning("🚨 Check the issues listed above")
    else:
        logger.info("✅ No obvious issues found")
        logger.info("💡 The problem might be in Paddle webhook configuration")
    
    logger.info("")
    logger.info("📞 NEXT STEPS:")
    logger.info("1. Fix any issues found above")
    logger.info("2. Set up ngrok or public hosting")
    logger.info("3. Update Paddle webhook URL")
    logger.info("4. Test with a sandbox payment")
    logger.info("5. Check application logs for webhook calls")

if __name__ == "__main__":
    asyncio.run(run_comprehensive_debug())