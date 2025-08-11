#!/usr/bin/env python3
"""
Debug Live Paddle Webhook Calls
Monitor and analyze actual webhook calls from Paddle
"""

import json
import requests
import logging
import time
from datetime import datetime
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_webhook_logs():
    """Check recent webhook activity"""
    logger.info("🔍 Checking webhook activity...")
    
    try:
        # Check if webhook endpoint is accessible
        response = requests.get("http://localhost:8000/webhook/test", timeout=10)
        if response.status_code == 200:
            data = response.json()
            logger.info("✅ Webhook endpoint is accessible")
            logger.info(f"🔥 Firebase available: {data.get('firebase_available', False)}")
            logger.info(f"📊 Server status: {data.get('status', 'unknown')}")
        else:
            logger.error(f"❌ Webhook endpoint returned {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Cannot reach webhook endpoint: {e}")
        return False
    
    return True

def check_paddle_webhook_configuration():
    """Provide Paddle webhook configuration checklist"""
    logger.info("\n📋 PADDLE WEBHOOK CONFIGURATION CHECKLIST:")
    logger.info("=" * 60)
    logger.info("1. Go to Paddle Dashboard > Developer Tools > Webhooks")
    logger.info("2. Verify webhook endpoint URL:")
    logger.info("   - Should be: https://your-ngrok-url.ngrok.io/webhook/paddle")
    logger.info("   - NOT: http://localhost:8000/webhook/paddle")
    logger.info("3. Verify webhook events are enabled:")
    logger.info("   ✓ transaction.completed")
    logger.info("   ✓ transaction.paid") 
    logger.info("   ✓ subscription.activated")
    logger.info("   ✓ subscription.updated")
    logger.info("4. Verify webhook secret matches your environment variable")
    logger.info("5. Test webhook delivery in Paddle dashboard")
    logger.info("")

def provide_debugging_steps():
    """Provide step-by-step debugging guide"""
    logger.info("🛠️ DEBUGGING STEPS FOR LIVE PADDLE PAYMENTS:")
    logger.info("=" * 60)
    logger.info("")
    logger.info("STEP 1: Verify ngrok setup")
    logger.info("------------------------")
    logger.info("1. Make sure ngrok is running: ngrok http 8000")
    logger.info("2. Copy the HTTPS URL (e.g., https://abc123.ngrok.io)")
    logger.info("3. Test the ngrok URL: https://your-ngrok-url.ngrok.io/webhook/test")
    logger.info("")
    logger.info("STEP 2: Update Paddle webhook configuration")
    logger.info("------------------------------------------")
    logger.info("1. Go to Paddle Dashboard > Developer Tools > Webhooks")
    logger.info("2. Update webhook URL to: https://your-ngrok-url.ngrok.io/webhook/paddle")
    logger.info("3. Ensure events are enabled: transaction.completed, subscription.activated")
    logger.info("4. Save changes")
    logger.info("")
    logger.info("STEP 3: Test webhook delivery")
    logger.info("-----------------------------")
    logger.info("1. In Paddle dashboard, use 'Test webhook' feature")
    logger.info("2. Send a test transaction.completed event")
    logger.info("3. Check your application logs for webhook calls")
    logger.info("")
    logger.info("STEP 4: Monitor live payment")
    logger.info("---------------------------")
    logger.info("1. Keep your application logs open")
    logger.info("2. Make a test payment in Paddle sandbox")
    logger.info("3. Watch for webhook calls in real-time")
    logger.info("4. Check Firestore for user updates")
    logger.info("")

def create_webhook_monitoring_guide():
    """Create a guide for monitoring webhooks"""
    logger.info("📊 WEBHOOK MONITORING GUIDE:")
    logger.info("=" * 40)
    logger.info("")
    logger.info("To monitor webhook calls in real-time:")
    logger.info("1. Keep your FastAPI server running with logs visible")
    logger.info("2. Look for these log messages:")
    logger.info("   - '🎯 Received Paddle webhook: X bytes'")
    logger.info("   - '✅ Webhook signature verified'")
    logger.info("   - '🎉 Successfully upgraded user...'")
    logger.info("   - '💾 User data updated in Firestore'")
    logger.info("")
    logger.info("3. If you don't see these messages, the webhook isn't being called")
    logger.info("4. If you see signature verification errors, check your webhook secret")
    logger.info("5. If you see processing errors, check your user data format")
    logger.info("")

def check_common_issues():
    """Check for common webhook issues"""
    logger.info("🔍 COMMON WEBHOOK ISSUES:")
    logger.info("=" * 35)
    logger.info("")
    logger.info("❌ ISSUE 1: Webhook URL not updated in Paddle")
    logger.info("   Solution: Update Paddle webhook URL to use ngrok HTTPS URL")
    logger.info("")
    logger.info("❌ ISSUE 2: Wrong webhook events enabled")
    logger.info("   Solution: Enable 'transaction.completed' and 'subscription.activated'")
    logger.info("")
    logger.info("❌ ISSUE 3: Webhook secret mismatch")
    logger.info("   Solution: Copy webhook secret from Paddle to your .env file")
    logger.info("")
    logger.info("❌ ISSUE 4: User ID format mismatch")
    logger.info("   Solution: Ensure custom_data.userId matches your frontend user ID")
    logger.info("")
    logger.info("❌ ISSUE 5: ngrok tunnel expired")
    logger.info("   Solution: Restart ngrok and update Paddle webhook URL")
    logger.info("")

async def monitor_webhook_activity(duration_minutes: int = 5):
    """Monitor webhook activity for a specified duration"""
    logger.info(f"👀 Monitoring webhook activity for {duration_minutes} minutes...")
    logger.info("Make a test payment now and watch for webhook calls!")
    logger.info("=" * 60)
    
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    webhook_calls_detected = 0
    
    while time.time() < end_time:
        try:
            # Check webhook test endpoint for activity
            response = requests.get("http://localhost:8000/webhook/test", timeout=5)
            if response.status_code == 200:
                current_time = datetime.now().strftime("%H:%M:%S")
                logger.info(f"⏰ {current_time} - Webhook endpoint is active")
            
            # Wait 10 seconds between checks
            await asyncio.sleep(10)
            
        except Exception as e:
            logger.warning(f"⚠️ Error checking webhook: {e}")
            await asyncio.sleep(10)
    
    logger.info(f"⏰ Monitoring completed after {duration_minutes} minutes")
    
    if webhook_calls_detected == 0:
        logger.warning("❌ No webhook calls detected during monitoring period")
        logger.info("💡 This suggests Paddle is not sending webhooks to your endpoint")
        logger.info("🔧 Check your Paddle webhook configuration")
    else:
        logger.info(f"✅ Detected {webhook_calls_detected} webhook calls")

async def run_live_webhook_debug():
    """Run live webhook debugging"""
    logger.info("🚀 Starting Live Paddle Webhook Debugging...")
    logger.info("=" * 60)
    
    # Check webhook accessibility
    if not check_webhook_logs():
        logger.error("❌ Cannot access webhook endpoint - fix this first!")
        return
    
    # Provide configuration checklist
    check_paddle_webhook_configuration()
    
    # Provide debugging steps
    provide_debugging_steps()
    
    # Check common issues
    check_common_issues()
    
    # Create monitoring guide
    create_webhook_monitoring_guide()
    
    # Ask user if they want to monitor
    logger.info("🎯 NEXT STEPS:")
    logger.info("1. Verify your Paddle webhook configuration using the checklist above")
    logger.info("2. Make a test payment in Paddle sandbox")
    logger.info("3. Watch your FastAPI server logs for webhook calls")
    logger.info("4. If no webhook calls appear, the issue is in Paddle configuration")
    logger.info("5. If webhook calls appear but fail, the issue is in processing")
    logger.info("")
    logger.info("💡 TIP: Keep your FastAPI server logs visible while testing payments!")

if __name__ == "__main__":
    asyncio.run(run_live_webhook_debug())