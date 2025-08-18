"""
Enhanced Payment Service for handling Paddle payments and credit management
"""

import os
import json
import hmac
import hashlib
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

import firebase_admin
from firebase_admin import firestore
from fastapi import HTTPException

# Configure logging
logger = logging.getLogger(__name__)

class PlanType(Enum):
    FREE = "free"
    STUDENT = "student"
    RESEARCHER = "researcher"
    EXPERT = "expert"

class BillingCycle(Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"

@dataclass
class PlanConfig:
    """Plan configuration with credits and pricing"""
    plan_id: str
    name: str
    monthly_credits: int
    yearly_credits: int
    monthly_price: float
    yearly_price: float
    features: list

@dataclass
class PaymentResult:
    """Result of payment processing"""
    success: bool
    message: str
    user_id: Optional[str] = None
    plan_id: Optional[str] = None
    credits_allocated: Optional[int] = None
    transaction_id: Optional[str] = None

class PaymentService:
    """Enhanced payment service for handling Paddle payments and credit management"""
    
    def __init__(self, db_client=None):
        self.db = db_client
        self.webhook_secret = os.getenv("PADDLE_WEBHOOK_SECRET")
        
        # Paddle API configuration
        self.paddle_api_key = os.getenv("PADDLE_API_KEY")
        self.paddle_environment = os.getenv("PADDLE_ENVIRONMENT", "live")  # live or sandbox
        self.paddle_base_url = "https://api.paddle.com" if self.paddle_environment in ["live", "production"] else "https://sandbox-api.paddle.com"
        
        # Plan configurations matching the frontend
        self.plan_configs = {
            PlanType.FREE.value: PlanConfig(
                plan_id="free",
                name="Free",
                monthly_credits=30,
                yearly_credits=30,
                monthly_price=0.0,
                yearly_price=0.0,
                features=["Up to 10 mind maps per month", "Basic mind map generation", "JSON and PDF exports", "Community support"]
            ),
            PlanType.STUDENT.value: PlanConfig(
                plan_id="student",
                name="Student",
                monthly_credits=1000,
                yearly_credits=12000,
                monthly_price=12.0,
                yearly_price=65.0,
                features=["Up to 1000 mind maps per month", "Videos up to 60 minutes", "Simple Mindmaps", "JSON and PDF exports", "Priority support"]
            ),
            PlanType.RESEARCHER.value: PlanConfig(
                plan_id="researcher",
                name="Researcher",
                monthly_credits=2000,
                yearly_credits=24000,
                monthly_price=19.0,
                yearly_price=137.0,
                features=["Up to 2000 mind maps per month", "Videos up to 120 minutes", "Advanced Mindmaps", "Interactive Quizzes", "All export formats", "Priority support", "API access"]
            ),
            PlanType.EXPERT.value: PlanConfig(
                plan_id="expert",
                name="Expert",
                monthly_credits=5000,
                yearly_credits=60000,
                monthly_price=29.0,
                yearly_price=209.0,
                features=["Up to 5000 mind maps per month", "Videos up to 300 minutes", "Advanced Mindmaps", "Interactive Quizzes", "All export formats", "Dedicated support", "Full API access", "Team management"]
            )
        }
    
    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verify Paddle webhook signature"""
        if not self.webhook_secret or not signature:
            logger.warning("⚠️ Webhook secret or signature missing")
            return False
        
        try:
            # Parse signature
            sig_parts = {}
            for part in signature.split(';'):
                if '=' in part:
                    key, value = part.split('=', 1)
                    sig_parts[key] = value
            
            # Verify timestamp (prevent replay attacks)
            timestamp = sig_parts.get('ts')
            if timestamp:
                current_time = int(datetime.now().timestamp())
                webhook_time = int(timestamp)
                if abs(current_time - webhook_time) > 300:  # 5 minutes tolerance
                    logger.warning("⚠️ Webhook timestamp too old")
                    return False
            
            # Verify signature
            expected_signature = hmac.new(
                self.webhook_secret.encode(),
                f"{timestamp}:{body.decode()}".encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_signature, sig_parts.get('h1', ''))
            
        except Exception as e:
            logger.error(f"❌ Error verifying webhook signature: {e}")
            return False
    
    def get_plan_config(self, plan_id: str) -> Optional[PlanConfig]:
        """Get plan configuration by ID"""
        return self.plan_configs.get(plan_id)
    
    def get_plan_name(self, plan_id: str) -> str:
        """Get plan display name by ID"""
        plan_config = self.get_plan_config(plan_id)
        return plan_config.name if plan_config else plan_id.title()
    
    def calculate_credits(self, plan_id: str, billing_cycle: str) -> int:
        """Calculate credits based on plan and billing cycle"""
        plan_config = self.get_plan_config(plan_id)
        if not plan_config:
            logger.error(f"❌ Unknown plan ID: {plan_id}")
            return 0
        
        if billing_cycle == BillingCycle.YEARLY.value:
            return plan_config.yearly_credits
        else:
            return plan_config.monthly_credits
    
    def calculate_price(self, plan_id: str, billing_cycle: str) -> float:
        """Calculate price based on plan and billing cycle"""
        plan_config = self.get_plan_config(plan_id)
        if not plan_config:
            logger.error(f"❌ Unknown plan ID: {plan_id}")
            return 0.0
        
        if billing_cycle == BillingCycle.YEARLY.value:
            return plan_config.yearly_price
        else:
            return plan_config.monthly_price
    
    def determine_billing_cycle(self, payment_data: Dict[str, Any], custom_data: Dict[str, Any]) -> str:
        """Determine billing cycle from payment data and custom data"""
        # Priority 1: Check custom data from frontend
        billing_cycle = custom_data.get("billingPeriod") or custom_data.get("billing_period")
        if billing_cycle:
            logger.info(f"🔍 Billing cycle from custom data: {billing_cycle}")
            return billing_cycle
        
        # Priority 2: Check subscription data if available
        subscription = payment_data.get("subscription")
        if subscription:
            subscription_id = subscription.get("id")
            billing_cycle_from_sub = subscription.get("billing_cycle")
            if billing_cycle_from_sub:
                logger.info(f"🔍 Billing cycle from subscription {subscription_id}: {billing_cycle_from_sub}")
                return billing_cycle_from_sub
        
        # Priority 3: Check items array for price IDs
        items = payment_data.get("items", [])
        if items:
            for item in items:
                price_id = item.get("price_id") or item.get("priceId")
                if price_id:
                    billing_cycle_from_price = self.get_billing_cycle_from_price_id(price_id)
                    if billing_cycle_from_price:
                        logger.info(f"🔍 Billing cycle from price ID {price_id}: {billing_cycle_from_price}")
                        return billing_cycle_from_price
        
        # Priority 4: Check direct price_id field
        price_id = payment_data.get("price_id")
        if price_id:
            billing_cycle_from_price = self.get_billing_cycle_from_price_id(price_id)
            if billing_cycle_from_price:
                logger.info(f"🔍 Billing cycle from direct price ID {price_id}: {billing_cycle_from_price}")
                return billing_cycle_from_price
        
        # Priority 5: Check subscription plan ID pattern
        subscription_plan_id = payment_data.get("subscription_plan_id")
        if subscription_plan_id:
            if "yearly" in subscription_plan_id.lower() or "annual" in subscription_plan_id.lower():
                logger.info(f"🔍 Billing cycle from subscription plan ID pattern: yearly")
                return "yearly"
            elif "monthly" in subscription_plan_id.lower():
                logger.info(f"🔍 Billing cycle from subscription plan ID pattern: monthly")
                return "monthly"
        
        # Priority 6: Check plan name patterns in custom data
        plan_name = custom_data.get("planName") or custom_data.get("plan_name")
        if plan_name:
            plan_name_lower = plan_name.lower()
            if "yearly" in plan_name_lower or "annual" in plan_name_lower:
                logger.info(f"🔍 Billing cycle from plan name pattern '{plan_name}': yearly")
                return "yearly"
            elif "monthly" in plan_name_lower:
                logger.info(f"🔍 Billing cycle from plan name pattern '{plan_name}': monthly")
                return "monthly"
        
        # Priority 7: Check product/item names in payment data
        items = payment_data.get("items", [])
        for item in items:
            item_name = item.get("name") or item.get("product_name")
            if item_name:
                item_name_lower = item_name.lower()
                if "yearly" in item_name_lower or "annual" in item_name_lower:
                    logger.info(f"🔍 Billing cycle from item name pattern '{item_name}': yearly")
                    return "yearly"
                elif "monthly" in item_name_lower:
                    logger.info(f"🔍 Billing cycle from item name pattern '{item_name}': monthly")
                    return "monthly"
        
        # Priority 8: Check product name in payment data
        product_name = payment_data.get("product_name") or payment_data.get("name")
        if product_name:
            product_name_lower = product_name.lower()
            if "yearly" in product_name_lower or "annual" in product_name_lower:
                logger.info(f"🔍 Billing cycle from product name pattern '{product_name}': yearly")
                return "yearly"
            elif "monthly" in product_name_lower:
                logger.info(f"🔍 Billing cycle from product name pattern '{product_name}': monthly")
                return "monthly"
        
        # Default fallback
        logger.warning("⚠️ Could not determine billing cycle, defaulting to monthly")
        return "monthly"
    
    def get_billing_cycle_from_price_id(self, price_id: str) -> Optional[str]:
        """Determine billing cycle from Paddle price ID"""
        # Map of known price IDs to billing cycles (from plans.js)
        price_id_mapping = {
            # Student plan (production)
            'pri_01k2ad2b99sd168ahwst4dsgsm': 'monthly',
            'pri_01k2ada78rxk3x2wbe4xbz5n92': 'yearly',
            # Researcher plan (production)
            'pri_01k2ad4jq1615arg3wm88pf1t0': 'monthly',
            'pri_01k2adc42dwrsmg09zg4y2rxjz': 'yearly',
            # Expert plan (production)
            'pri_01k2ad68ttbkx581anqh57wm4s': 'monthly',
            'pri_01k2ade8nh1tta3g336vzwa59x': 'yearly'
        }

        
        billing_cycle = price_id_mapping.get(price_id)
        if billing_cycle:
            logger.info(f"✅ Mapped price ID {price_id} to {billing_cycle} billing")
        else:
            logger.warning(f"⚠️ Unknown price ID: {price_id}")
        
        return billing_cycle
    
    def get_price_id(self, plan_id: str, billing_cycle: str) -> Optional[str]:
        """Map plan_id and billing_cycle to a Paddle price_id (live)."""
        price_ids = {
            'student': {
                'monthly': 'pri_01k2ad2b99sd168ahwst4dsgsm',
                'yearly': 'pri_01k2ada78rxk3x2wbe4xbz5n92',
            },
            'researcher': {
                'monthly': 'pri_01k2ad4jq1615arg3wm88pf1t0',
                'yearly': 'pri_01k2adc42dwrsmg09zg4y2rxjz',
            },
            'expert': {
                'monthly': 'pri_01k2ad68ttbkx581anqh57wm4s',
                'yearly': 'pri_01k2ade8nh1tta3g336vzwa59x',
            }
        }
        pid = price_ids.get(plan_id, {}).get(billing_cycle)
        if not pid:
            logger.warning(f"⚠️ No price_id found for plan_id={plan_id}, billing_cycle={billing_cycle}")
        return pid

    def create_checkout_session(
        self,
        plan_id: str,
        billing_cycle: str,
        user_id: str,
        customer_email: Optional[str] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
        price_id: Optional[str] = None,
        quantity: int = 1
    ) -> Dict[str, Any]:
        """Create a Paddle Checkout Session. Uses https://api.paddle.com in live mode."""
        try:
            if not self.paddle_api_key:
                logger.warning("⚠️ Paddle API key not configured")
                return {"success": False, "error": "Paddle API key not configured"}

            headers = {
                "Authorization": f"Bearer {self.paddle_api_key}",
                "Content-Type": "application/json"
            }

            # Determine price_id if not provided
            if not price_id:
                price_id = self.get_price_id(plan_id, billing_cycle)
            if not price_id:
                return {"success": False, "error": "Unknown plan/billing_cycle mapping to price_id"}

            url = f"{self.paddle_base_url}/checkout/sessions"

            payload: Dict[str, Any] = {
                "items": [{"price_id": price_id, "quantity": quantity}],
                "custom_data": {
                    "userId": user_id,
                    "planId": plan_id,
                    "billingPeriod": billing_cycle
                }
            }

            if customer_email:
                payload["customer"] = {"email": customer_email}

            if success_url is None:
                success_url = os.getenv("PADDLE_SUCCESS_URL")
            if cancel_url is None:
                cancel_url = os.getenv("PADDLE_CANCEL_URL")
            if success_url:
                payload["success_url"] = success_url
            if cancel_url:
                payload["cancel_url"] = cancel_url

            logger.info(f"🧾 Creating Paddle checkout session for user {user_id}, plan {plan_id} ({billing_cycle}) at {url}")
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code in (200, 201):
                data = response.json()
                session = data.get("data", data)
                checkout_url = session.get("checkout_url") or session.get("redirect_url") or session.get("url")
                logger.info("✅ Created Paddle checkout session")
                return {"success": True, "data": session, "checkout_url": checkout_url}
            else:
                error_msg = f"Failed to create checkout session: {response.status_code} - {response.text}"
                logger.error(f"❌ {error_msg}")
                return {"success": False, "error": error_msg}
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error creating checkout session: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Error creating checkout session: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}

    async def handle_successful_payment(self, payment_data: Dict[str, Any]) -> PaymentResult:
        """Handle successful payment and update user credits/plan"""
        try:
            # Extract payment information
            transaction_id = payment_data.get("id")
            customer_id = payment_data.get("customer_id")
            custom_data = payment_data.get("custom_data", {})
            
            # Extract user and plan information
            user_id = custom_data.get("userId") or custom_data.get("user_id")
            plan_id = custom_data.get("planId") or custom_data.get("plan_id")
            
            # Determine billing cycle from multiple sources
            billing_cycle = self.determine_billing_cycle(payment_data, custom_data)
            
            logger.info(f"💳 Processing successful payment: {transaction_id}")
            logger.info(f"👤 User: {user_id}, Plan: {plan_id}, Billing: {billing_cycle}")
            logger.debug(f"Payment data structure: {json.dumps(payment_data, indent=2, default=str)}")
            
            if not user_id or not plan_id:
                error_msg = f"Missing user_id or plan_id in payment {transaction_id}"
                logger.warning(f"⚠️ {error_msg}")
                return PaymentResult(success=False, message=error_msg)
            
            # Get plan configuration
            plan_config = self.get_plan_config(plan_id)
            if not plan_config:
                error_msg = f"Unknown plan ID: {plan_id}"
                logger.error(f"❌ {error_msg}")
                return PaymentResult(success=False, message=error_msg)
            
            # Calculate credits and price
            new_credits = self.calculate_credits(plan_id, billing_cycle)
            price = self.calculate_price(plan_id, billing_cycle)
            
            logger.info(f"🚀 Upgrading user {user_id} to {plan_id} plan ({billing_cycle}) with {new_credits} credits")
            
            # Update user data in Firestore
            if self.db:
                result = await self.update_user_data(
                    user_id=user_id,
                    plan_id=plan_id,
                    billing_cycle=billing_cycle,
                    credits=new_credits,
                    price=price,
                    transaction_id=transaction_id,
                    customer_id=customer_id
                )
                
                if result:
                    success_msg = f"Successfully upgraded user {user_id} to {plan_config.name} plan with {new_credits} credits"
                    logger.info(f"✅ {success_msg}")
                    return PaymentResult(
                        success=True,
                        message=success_msg,
                        user_id=user_id,
                        plan_id=plan_id,
                        credits_allocated=new_credits,
                        transaction_id=transaction_id
                    )
                else:
                    error_msg = "Failed to update user data in database"
                    logger.error(f"❌ {error_msg}")
                    return PaymentResult(success=False, message=error_msg)
            else:
                error_msg = "Database not available"
                logger.warning(f"⚠️ {error_msg}")
                return PaymentResult(success=False, message=error_msg)
                
        except Exception as e:
            error_msg = f"Error processing successful payment: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return PaymentResult(success=False, message=error_msg)
    
    async def update_user_data(self, user_id: str, plan_id: str, billing_cycle: str, 
                             credits: int, price: float, transaction_id: str, 
                             customer_id: str = None) -> bool:
        """Update user data in Firestore after successful payment"""
        try:
            user_ref = self.db.collection('users').document(user_id)
            
            # Calculate plan dates
            now = datetime.now()
            if billing_cycle == BillingCycle.YEARLY.value:
                plan_end_date = now + timedelta(days=365)
                next_billing_date = plan_end_date
            else:
                plan_end_date = now + timedelta(days=30)
                next_billing_date = plan_end_date
            
            # Prepare update data
            update_data = {
                'plan': plan_id,
                'currentPlan': plan_id,
                'planId': plan_id,
                'credits': credits,
                'billingCycle': billing_cycle,
                'billingPeriod': billing_cycle,
                'price': price,
                'subscriptionStatus': 'active',
                'lastPaymentDate': now.isoformat(),
                'subscriptionDate': now.isoformat(),
                'planStartDate': now.isoformat(),
                'planEndDate': plan_end_date.isoformat(),
                'nextBillingDate': next_billing_date.isoformat(),
                'lastUpdated': now.isoformat(),
                'lastPlanUpdate': now.isoformat(),
                'lastCreditUpdate': now.isoformat(),
                'autoRenew': True
            }
            
            # Add customer and transaction info if available
            if customer_id:
                update_data['customerId'] = customer_id
            if transaction_id:
                update_data['lastTransactionId'] = transaction_id
            
            # Check if user document exists
            user_doc = user_ref.get()
            if user_doc.exists:
                # Update existing user
                user_ref.update(update_data)
                logger.info(f"✅ Updated existing user {user_id}")
            else:
                # Create new user document
                update_data['createdAt'] = now.isoformat()
                user_ref.set(update_data)
                logger.info(f"✅ Created new user document for {user_id}")
            
            # Add plan history entry
            await self.add_plan_history_entry(
                user_id=user_id,
                plan_id=plan_id,
                billing_cycle=billing_cycle,
                credits=credits,
                price=price,
                transaction_id=transaction_id,
                reason='subscription_created'
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error updating user data in Firestore: {e}")
            return False
    
    async def add_plan_history_entry(self, user_id: str, plan_id: str, billing_cycle: str,
                                   credits: int, price: float, transaction_id: str, reason: str):
        """Add entry to user's plan history"""
        try:
            user_ref = self.db.collection('users').document(user_id)
            plan_history_ref = user_ref.collection('planHistory')
            
            history_entry = {
                'date': datetime.now().isoformat(),
                'planId': plan_id,
                'billingCycle': billing_cycle,
                'billingPeriod': billing_cycle,
                'creditsAllocated': credits,
                'amount': price,
                'transactionId': transaction_id,
                'reason': reason,
                'timestamp': datetime.now().isoformat()
            }
            
            plan_history_ref.add(history_entry)
            logger.info(f"✅ Added plan history entry for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Error adding plan history entry: {e}")
    
    async def handle_subscription_activated(self, subscription_data: Dict[str, Any]) -> PaymentResult:
        """Handle subscription activation"""
        try:
            subscription_id = subscription_data.get("id")
            customer_id = subscription_data.get("customer_id")
            custom_data = subscription_data.get("custom_data", {})
            
            logger.info(f"🔄 Processing subscription activation: {subscription_id}")
            
            user_id = custom_data.get("userId") or custom_data.get("user_id")
            plan_id = custom_data.get("planId") or custom_data.get("plan_id")
            
            if not user_id or not plan_id:
                error_msg = f"Missing user_id or plan_id in subscription {subscription_id}"
                logger.warning(f"⚠️ {error_msg}")
                return PaymentResult(success=False, message=error_msg)
            
            # Update subscription status in Firestore
            if self.db:
                user_ref = self.db.collection('users').document(user_id)
                user_ref.update({
                    'subscriptionId': subscription_id,
                    'subscriptionStatus': 'active',
                    'lastSubscriptionUpdate': datetime.now().isoformat()
                })
                
                success_msg = f"Subscription activated for user {user_id}"
                logger.info(f"✅ {success_msg}")
                return PaymentResult(success=True, message=success_msg, user_id=user_id)
            else:
                error_msg = "Database not available"
                logger.warning(f"⚠️ {error_msg}")
                return PaymentResult(success=False, message=error_msg)
                
        except Exception as e:
            error_msg = f"Error handling subscription activation: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return PaymentResult(success=False, message=error_msg)
    
    async def handle_subscription_updated(self, subscription_data: Dict[str, Any]) -> PaymentResult:
        """Handle subscription updates"""
        try:
            subscription_id = subscription_data.get("id")
            status = subscription_data.get("status")
            
            logger.info(f"🔄 Processing subscription update: {subscription_id} -> {status}")
            
            if self.db:
                # Find user by subscription ID
                users_ref = self.db.collection('users')
                query = users_ref.where('subscriptionId', '==', subscription_id)
                docs = query.stream()
                
                updated_users = []
                for doc in docs:
                    doc.reference.update({
                        'subscriptionStatus': status,
                        'lastSubscriptionUpdate': datetime.now().isoformat()
                    })
                    updated_users.append(doc.id)
                    logger.info(f"✅ Updated subscription status for user {doc.id}")
                
                if updated_users:
                    success_msg = f"Updated subscription status for {len(updated_users)} users"
                    return PaymentResult(success=True, message=success_msg)
                else:
                    error_msg = f"No users found with subscription ID {subscription_id}"
                    logger.warning(f"⚠️ {error_msg}")
                    return PaymentResult(success=False, message=error_msg)
            else:
                error_msg = "Database not available"
                logger.warning(f"⚠️ {error_msg}")
                return PaymentResult(success=False, message=error_msg)
                
        except Exception as e:
            error_msg = f"Error handling subscription update: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return PaymentResult(success=False, message=error_msg)
    
    async def handle_subscription_canceled(self, subscription_data: Dict[str, Any]) -> PaymentResult:
        """Handle subscription cancellation and downgrade users to free plan"""
        try:
            subscription_id = subscription_data.get("id")
            
            logger.info(f"❌ Processing subscription cancellation: {subscription_id}")
            
            if self.db:
                # Find user by subscription ID
                users_ref = self.db.collection('users')
                query = users_ref.where('subscriptionId', '==', subscription_id)
                docs = query.stream()
                
                canceled_users = []
                for doc in docs:
                    user_id = doc.id
                    user_data = doc.to_dict()
                    
                    # Downgrade user to free plan
                    await self._downgrade_to_free_plan(user_id, user_data, subscription_id)
                    canceled_users.append(user_id)
                    logger.info(f"✅ Downgraded user {user_id} to free plan after subscription cancellation")
                
                if canceled_users:
                    success_msg = f"Downgraded {len(canceled_users)} users to free plan after subscription cancellation"
                    return PaymentResult(
                        success=True, 
                        message=success_msg,
                        user_id=canceled_users[0] if len(canceled_users) == 1 else None,
                        plan_id='free',
                        credits_allocated=self.get_plan_config('free').monthly_credits if self.get_plan_config('free') else 10
                    )
                else:
                    error_msg = f"No users found with subscription ID {subscription_id}"
                    logger.warning(f"⚠️ {error_msg}")
                    return PaymentResult(success=False, message=error_msg)
            else:
                error_msg = "Database not available"
                logger.warning(f"⚠️ {error_msg}")
                return PaymentResult(success=False, message=error_msg)
                
        except Exception as e:
            error_msg = f"Error handling subscription cancellation: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return PaymentResult(success=False, message=error_msg)

    async def _downgrade_to_free_plan(self, user_id: str, user_data: Dict[str, Any], subscription_id: str):
        """Downgrade user to free plan after subscription cancellation"""
        try:
            now = datetime.now().isoformat()
            free_plan_config = self.get_plan_config('free')
            
            if not free_plan_config:
                logger.error(f"❌ Free plan configuration not found")
                return
            
            # Update plan history - end current plan and add free plan
            plan_history = user_data.get('planHistory', [])
            
            # End current plan if it exists
            if plan_history:
                current_plan_entry = plan_history[-1]
                if not current_plan_entry.get('endDate'):
                    current_plan_entry['endDate'] = now
                    current_plan_entry['reason'] = 'subscription_canceled'
            
            # Add free plan to history
            plan_history.append({
                'planId': 'free',
                'startDate': now,
                'endDate': None,  # Free plan doesn't expire
                'creditsAllocated': free_plan_config.monthly_credits,
                'subscriptionId': None,
                'billingPeriod': 'monthly',
                'amount': 0,
                'reason': 'subscription_canceled_downgrade'
            })
            
            # Update user document
            update_data = {
                'currentPlan': 'free',
                'planHistory': plan_history,
                'subscriptionStatus': 'canceled',
                'subscriptionId': None,  # Clear subscription ID
                'planStartDate': now,
                'planEndDate': None,  # Free plan doesn't expire
                'autoRenew': False,
                'credits': free_plan_config.monthly_credits,  # Reset to free plan credits
                'lastCreditUpdate': now,
                'lastPlanUpdate': now,
                'lastSubscriptionUpdate': now,
                'subscriptionMetadata': {
                    'previousSubscriptionId': subscription_id,
                    'downgradedAt': now,
                    'reason': 'subscription_canceled'
                }
            }
            
            # Update user document in Firestore
            user_ref = self.db.collection('users').document(user_id)
            user_ref.update(update_data)
            
            logger.info(f"✅ Successfully downgraded user {user_id} to free plan")
            
        except Exception as e:
            logger.error(f"❌ Error downgrading user {user_id} to free plan: {str(e)}")
            raise
    
    async def refresh_user_data(self, user_id: str) -> Dict[str, Any]:
        """Refresh and return user data from Firestore"""
        try:
            if not self.db:
                raise Exception("Database not available")
            
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                logger.info(f"✅ Refreshed user data for {user_id}")
                return user_data
            else:
                logger.warning(f"⚠️ User document not found: {user_id}")
                return {}
                
        except Exception as e:
            logger.error(f"❌ Error refreshing user data: {e}")
            return {}
    
    def get_plan_name(self, plan_id: str) -> str:
        """Get human-readable plan name"""
        plan_config = self.get_plan_config(plan_id)
        return plan_config.name if plan_config else plan_id.title()

    async def cancel_paddle_subscription(self, subscription_id: str, effective_from: str = "next_billing_period") -> Dict[str, Any]:
        """Cancel a Paddle subscription via API"""
        try:
            if not self.paddle_api_key:
                logger.warning("⚠️ Paddle API key not configured")
                return {"success": False, "error": "Paddle API key not configured"}
            
            headers = {
                "Authorization": f"Bearer {self.paddle_api_key}",
                "Content-Type": "application/json"
            }
            
            # Paddle API endpoint for canceling subscriptions
            url = f"{self.paddle_base_url}/subscriptions/{subscription_id}/cancel"
            
            payload = {
                "effective_from": effective_from  # "immediately" or "next_billing_period"
            }
            
            logger.info(f"🔄 Canceling Paddle subscription {subscription_id} via API")
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Successfully canceled Paddle subscription {subscription_id}")
                return {"success": True, "data": result}
            else:
                error_msg = f"Failed to cancel subscription: {response.status_code} - {response.text}"
                logger.error(f"❌ {error_msg}")
                return {"success": False, "error": error_msg}
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error canceling subscription: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Error canceling subscription: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}

    async def get_paddle_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Get subscription details from Paddle API"""
        try:
            if not self.paddle_api_key:
                logger.warning("⚠️ Paddle API key not configured")
                return {"success": False, "error": "Paddle API key not configured"}
            
            headers = {
                "Authorization": f"Bearer {self.paddle_api_key}",
                "Content-Type": "application/json"
            }
            
            url = f"{self.paddle_base_url}/subscriptions/{subscription_id}"
            
            logger.info(f"🔄 Fetching Paddle subscription {subscription_id} details")
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Successfully fetched Paddle subscription {subscription_id}")
                return {"success": True, "data": result}
            else:
                error_msg = f"Failed to fetch subscription: {response.status_code} - {response.text}"
                logger.error(f"❌ {error_msg}")
                return {"success": False, "error": error_msg}
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error fetching subscription: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Error fetching subscription: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}