#!/usr/bin/env python3
"""
Debug Firestore Updates
Comprehensive test to verify webhook is updating Firestore correctly
"""

import json
import asyncio
import hmac
import hashlib
from datetime import datetime
import uuid
import requests
import logging
import time
import os
from typing import Dict, Any

# Firebase Admin SDK for direct Firestore checking
import firebase_admin
from firebase_admin import credentials, firestore

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
WEBHOOK_URL = "http://localhost:8000/webhook/paddle"
WEBHOOK_SECRET = "pdl_ntfset_01k20v0kskye1ywj0rkd8cwkj8_WK7aCD9pEhUWBgS0XfkGKro9vU9PUIXA"

def initialize_firebase():
    """Initialize Firebase Admin SDK for direct database access"""
    try:
        if not firebase_admin._apps:
            credentials_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
            if credentials_json:
                cred_dict = json.loads(credentials_json)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred, {
                    'projectId': os.getenv('FIREBASE_PROJECT_ID', 'mindquick-7b9e2')
                })
                logger.info("✅ Firebase initialized for direct database access")
                return firestore.client()
            else:
                logger.error("❌ No Firebase credentials found")
                return None
    except Exception as e:
        logger.error(f"❌ Firebase initialization failed: {e}")
        return None

def generate_webhook_signature(payload: str, secret: str, timestamp: int) -> str:
    """Generate a valid Paddle webhook signature"""
    try:
        message = f"{timestamp}:{payload}"
        signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return f"ts={timestamp};h1={signature}"
    except Exception as e:
        logger.error(f"Error generating signature: {e}")
        return ""

def create_test_payment_payload(user_id: str, plan_id: str = "student", billing_period: str = "monthly") -> Dict[str, Any]:
    """Create a test payment payload"""
    
    plan_configs = {
        "student": {
            "monthly": {"credits": 1000, "price": 9},
            "yearly": {"credits": 12000, "price": 65}
        },
        "researcher": {
            "monthly": {"credits": 2000, "price": 19},
            "yearly": {"credits": 24000, "price": 137}
        },
        "expert": {
            "monthly": {"credits": 5000, "price": 29},
            "yearly": {"credits": 60000, "price": 209}
        }
    }
    
    config = plan_configs[plan_id][billing_period]
    transaction_id = f"txn_debug_{uuid.uuid4().hex[:8]}"
    customer_id = f"ctm_debug_{uuid.uuid4().hex[:8]}"
    
    return {
        "event_id": f"evt_debug_{uuid.uuid4().hex[:8]}",
        "event_type": "transaction.completed",
        "occurred_at": datetime.now().isoformat() + "Z",
        "data": {
            "id": transaction_id,
            "status": "completed",
            "customer_id": customer_id,
            "created_at": datetime.now().isoformat() + "Z",
            "updated_at": datetime.now().isoformat() + "Z",
            "billed_at": datetime.now().isoformat() + "Z",
            "details": {
                "totals": {
                    "subtotal": str(config["price"] * 100),
                    "tax": "0",
                    "total": str(config["price"] * 100),
                    "credit": "0",
                    "balance": "0",
                    "grand_total": str(config["price"] * 100)
                }
            },
            "custom_data": {
                "userId": user_id,
                "user_id": user_id,
                "planId": plan_id,
                "plan_id": plan_id,
                "planName": plan_id.capitalize(),
                "billingPeriod": billing_period,
                "billing_period": billing_period,
                "credits": config["credits"],
                "amount": config["price"]
            }
        }
    }

async def check_firestore_before_webhook(db, user_id: str):
    """Check Firestore state before webhook"""
    try:
        logger.info(f"🔍 Checking Firestore BEFORE webhook for user: {user_id}")
        
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            data = user_doc.to_dict()
            logger.info(f"📊 BEFORE - User exists:")
            logger.info(f"   Plan: {data.get('plan', 'N/A')} / {data.get('planId', 'N/A')} / {data.get('currentPlan', 'N/A')}")
            logger.info(f"   Credits: {data.get('credits', 'N/A')}")
            logger.info(f"   Billing: {data.get('billingPeriod', 'N/A')} / {data.get('billingCycle', 'N/A')}")
            return data
        else:
            logger.info(f"📊 BEFORE - User {user_id} does not exist in Firestore")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error checking Firestore before webhook: {e}")
        return None

async def check_firestore_after_webhook(db, user_id: str, expected_plan: str, expected_credits: int, max_retries: int = 10):
    """Check Firestore state after webhook with retries"""
    try:
        logger.info(f"🔍 Checking Firestore AFTER webhook for user: {user_id}")
        logger.info(f"📋 Expected: Plan={expected_plan}, Credits={expected_credits}")
        
        for attempt in range(max_retries):
            try:
                user_ref = db.collection('users').document(user_id)
                user_doc = user_ref.get()
                
                if user_doc.exists:
                    data = user_doc.to_dict()
                    current_plan = data.get('plan') or data.get('planId') or data.get('currentPlan')
                    current_credits = data.get('credits')
                    
                    logger.info(f"📊 AFTER (Attempt {attempt + 1}):")
                    logger.info(f"   Plan: {current_plan}")
                    logger.info(f"   Credits: {current_credits}")
                    logger.info(f"   Billing: {data.get('billingPeriod', 'N/A')} / {data.get('billingCycle', 'N/A')}")
                    logger.info(f"   Last Updated: {data.get('lastUpdated', 'N/A')}")
                    logger.info(f"   Last Plan Update: {data.get('lastPlanUpdate', 'N/A')}")
                    logger.info(f"   Customer ID: {data.get('customerId', 'N/A')}")
                    
                    if current_plan == expected_plan and current_credits == expected_credits:
                        logger.info("✅ Firestore update verified successfully!")
                        return True, data
                    elif attempt < max_retries - 1:
                        logger.info(f"⏳ Data not yet updated, retrying in 2 seconds...")
                        await asyncio.sleep(2)
                    else:
                        logger.warning(f"⚠️ Firestore data doesn't match expected values after {max_retries} attempts")
                        return False, data
                else:
                    logger.warning(f"⚠️ User {user_id} still doesn't exist in Firestore (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                    else:
                        logger.error(f"❌ User {user_id} was not created in Firestore after webhook")
                        return False, None
                        
            except Exception as e:
                logger.warning(f"⚠️ Error checking Firestore (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
        
        return False, None
        
    except Exception as e:
        logger.error(f"❌ Error checking Firestore after webhook: {e}")
        return False, None

async def send_webhook_and_verify(user_id: str, plan_id: str, billing_period: str):
    """Send webhook and verify Firestore updates"""
    
    # Initialize Firebase for direct database access
    db = initialize_firebase()
    if not db:
        logger.error("❌ Cannot access Firestore directly - skipping database verification")
        return False
    
    logger.info(f"🚀 Testing webhook for user: {user_id}, plan: {plan_id}, billing: {billing_period}")
    
    # Check Firestore state before webhook
    before_data = await check_firestore_before_webhook(db, user_id)
    
    # Create and send webhook
    payload = create_test_payment_payload(user_id, plan_id, billing_period)
    payload_json = json.dumps(payload, separators=(',', ':'))
    
    timestamp = int(datetime.now().timestamp())
    signature = generate_webhook_signature(payload_json, WEBHOOK_SECRET, timestamp)
    
    headers = {
        "Content-Type": "application/json",
        "paddle-signature": signature
    }
    
    logger.info("📤 Sending webhook request...")
    
    try:
        response = requests.post(WEBHOOK_URL, data=payload_json, headers=headers, timeout=30)
        
        logger.info(f"📊 Webhook Response Status: {response.status_code}")
        logger.info(f"📄 Webhook Response: {response.text}")
        
        if response.status_code == 200:
            webhook_data = response.json()
            webhook_success = webhook_data.get("status") == "success"
            
            if webhook_success:
                logger.info("✅ Webhook processed successfully")
                
                # Calculate expected values
                plan_configs = {
                    "student": {"monthly": 1000, "yearly": 12000},
                    "researcher": {"monthly": 2000, "yearly": 24000},
                    "expert": {"monthly": 5000, "yearly": 60000}
                }
                expected_credits = plan_configs[plan_id][billing_period]
                
                # Check Firestore updates
                success, after_data = await check_firestore_after_webhook(db, user_id, plan_id, expected_credits)
                
                if success:
                    logger.info("🎉 COMPLETE SUCCESS! Webhook updated Firestore correctly!")
                    return True
                else:
                    logger.error("❌ FAILURE! Webhook succeeded but Firestore was not updated correctly!")
                    
                    # Debug information
                    logger.info("\n🔍 DEBUGGING INFORMATION:")
                    logger.info(f"Webhook response data: {webhook_data}")
                    if after_data:
                        logger.info(f"Actual Firestore data: {after_data}")
                    
                    return False
            else:
                logger.error(f"❌ Webhook processing failed: {webhook_data}")
                return False
        else:
            logger.error(f"❌ Webhook request failed with status {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error sending webhook: {e}")
        return False

async def run_comprehensive_firestore_debug():
    """Run comprehensive Firestore debugging"""
    logger.info("🚀 Starting comprehensive Firestore update debugging...")
    logger.info("=" * 70)
    
    # Generate test user ID
    test_user_id = f"firestore_debug_user_{uuid.uuid4().hex[:8]}"
    logger.info(f"👤 Test User ID: {test_user_id}")
    
    # Test different scenarios
    test_cases = [
        ("student", "monthly", 1000),
        ("researcher", "yearly", 24000),
        ("expert", "monthly", 5000)
    ]
    
    results = []
    
    for plan_id, billing_period, expected_credits in test_cases:
        logger.info(f"\n{'='*50}")
        logger.info(f"TEST: {plan_id.upper()} {billing_period.upper()} PLAN")
        logger.info(f"{'='*50}")
        
        # Use different user ID for each test
        user_id = f"{test_user_id}_{plan_id}_{billing_period}"
        
        success = await send_webhook_and_verify(user_id, plan_id, billing_period)
        results.append((f"{plan_id} {billing_period}", success))
        
        # Wait between tests
        await asyncio.sleep(3)
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("COMPREHENSIVE TEST SUMMARY")
    logger.info(f"{'='*50}")
    
    passed = sum(1 for _, success in results if success)
    failed = len(results) - passed
    
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\nTotal Tests: {len(results)}")
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")
    
    if passed == len(results):
        logger.info("\n🎉 ALL TESTS PASSED!")
        logger.info("✅ Webhook is correctly updating Firestore with user plans and credits!")
    else:
        logger.warning(f"\n⚠️ {failed} test(s) failed.")
        logger.warning("❌ Webhook is NOT correctly updating Firestore!")
        logger.info("\n🔍 POSSIBLE ISSUES:")
        logger.info("1. Check if the webhook is receiving the requests")
        logger.info("2. Check if Firebase credentials are correct")
        logger.info("3. Check if the user ID format matches your frontend")
        logger.info("4. Check server logs for detailed error messages")

if __name__ == "__main__":
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    # Run the comprehensive test
    asyncio.run(run_comprehensive_firestore_debug())