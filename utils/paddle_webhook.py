import json
import hmac
import hashlib
from datetime import datetime, timedelta
from firebase_admin import firestore

# Paddle webhook signature verification
def verify_paddle_webhook(webhook_data, signature, webhook_secret):
    """
    Verify that the webhook data came from Paddle by checking the signature
    """
    try:
        # Create HMAC signature
        expected_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            webhook_data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures (constant time comparison)
        return hmac.compare_digest(signature, expected_signature)
    except Exception as e:
        print(f"Error verifying webhook signature: {e}")
        return False

def process_subscription_created(webhook_data):
    """
    Process subscription.created webhook from Paddle
    """
    try:
        # Extract relevant data
        subscription_id = webhook_data.get('subscription_id')
        user_id = webhook_data.get('passthrough', {}).get('userId')
        plan_id = webhook_data.get('passthrough', {}).get('planId')
        billing_period = webhook_data.get('passthrough', {}).get('billingPeriod', 'monthly')
        amount = float(webhook_data.get('subscription_plan_id', 0))
        
        if not user_id or not plan_id:
            print("Missing user_id or plan_id in webhook data")
            return False
            
        # Get plan configuration
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config.plans import PLANS
        if plan_id not in PLANS:
            print(f"Invalid plan ID: {plan_id}")
            return False
            
        plan_config = PLANS[plan_id]
        
        # Calculate plan end date
        now = datetime.utcnow()
        if billing_period == 'yearly':
            end_date = now + timedelta(days=365)
        else:
            end_date = now + timedelta(days=30)
            
        # Update user in Firestore
        db = firestore.client()
        user_ref = db.collection('users').document(user_id)
        
        # Get current user data
        user_doc = user_ref.get()
        if not user_doc.exists:
            print(f"User {user_id} not found")
            return False
            
        current_data = user_doc.to_dict()
        
        # Update plan history
        plan_history = current_data.get('planHistory', [])
        
        # End current plan if it exists
        if plan_history:
            current_plan_entry = plan_history[-1]
            if not current_plan_entry.get('endDate'):
                current_plan_entry['endDate'] = now.isoformat()
        
        # Calculate credits based on billing period
        credits_to_allocate = plan_config['yearlyCredits'] if billing_period == 'yearly' else plan_config['monthlyCredits']
        
        print(f"💳 Plan upgrade: {plan_id} ({billing_period})")
        print(f"💰 Credits to allocate: {credits_to_allocate}")
        print(f"👤 User: {user_id}")
        
        # Add new plan to history
        plan_history.append({
            'planId': plan_id,
            'startDate': now.isoformat(),
            'endDate': end_date.isoformat(),
            'creditsAllocated': credits_to_allocate,
            'subscriptionId': subscription_id,
            'billingPeriod': billing_period,
            'amount': amount,
            'reason': 'subscription_created'
        })
        
        # Prepare update data
        update_data = {
            'currentPlan': plan_id,
            'planHistory': plan_history,
            'subscriptionStatus': 'active',
            'subscriptionId': subscription_id,
            'planStartDate': now.isoformat(),
            'planEndDate': end_date.isoformat(),
            'autoRenew': True,
            'credits': (current_data.get('credits', 0) + credits_to_allocate),
            'lastCreditUpdate': now.isoformat(),
            'lastPlanUpdate': now.isoformat(),
            'subscriptionMetadata': {
                'billingPeriod': billing_period,
                'amount': amount,
                'currency': 'USD',
                'paymentMethod': 'paddle',
                'updatedAt': now.isoformat()
            }
        }
        
        # Update user document
        user_ref.update(update_data)
        
        final_credits = current_data.get('credits', 0) + credits_to_allocate
        print(f"✅ Successfully upgraded user {user_id} to {plan_id} plan")
        print(f"💰 Final credit balance: {final_credits}")
        return True
        
    except Exception as e:
        print(f"Error processing subscription created webhook: {e}")
        return False
        
def process_subscription_updated(webhook_data):
    """
    Process subscription.updated webhook from Paddle
    """
    try:
        subscription_id = webhook_data.get('subscription_id')
        user_id = webhook_data.get('passthrough', {}).get('userId')
        new_plan_id = webhook_data.get('passthrough', {}).get('planId')
        status = webhook_data.get('status')
        
        if not user_id or not subscription_id:
            print("Missing user_id or subscription_id in webhook data")
            return False
            
        db = firestore.client()
        user_ref = db.collection('users').document(user_id)
        
        # Get current user data
        user_doc = user_ref.get()
        if not user_doc.exists:
            print(f"User {user_id} not found")
            return False
            
        # Update subscription status
        update_data = {
            'subscriptionStatus': status,
            'lastPlanUpdate': datetime.utcnow().isoformat()
        }
        
        # If plan changed, update plan details
        if new_plan_id and new_plan_id != user_doc.to_dict().get('currentPlan'):
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from config.plans import PLANS
            if new_plan_id in PLANS:
                plan_config = PLANS[new_plan_id]
                update_data.update({
                    'currentPlan': new_plan_id,
                    'credits': user_doc.to_dict().get('credits', 0) + plan_config['credits'],
                    'lastCreditUpdate': datetime.utcnow().isoformat()
                })
        
        user_ref.update(update_data)
        print(f"Successfully updated subscription {subscription_id} for user {user_id}")
        return True
        
    except Exception as e:
        print(f"Error processing subscription updated webhook: {e}")
        return False

def process_subscription_cancelled(webhook_data):
    """
    Process subscription.cancelled webhook from Paddle
    """
    try:
        subscription_id = webhook_data.get('subscription_id')
        user_id = webhook_data.get('passthrough', {}).get('userId')
        
        if not user_id or not subscription_id:
            print("Missing user_id or subscription_id in webhook data")
            return False
            
        db = firestore.client()
        user_ref = db.collection('users').document(user_id)
        
        # Update subscription status
        update_data = {
            'subscriptionStatus': 'cancelled',
            'autoRenew': False,
            'lastPlanUpdate': datetime.utcnow().isoformat()
        }
        
        user_ref.update(update_data)
        print(f"Successfully cancelled subscription {subscription_id} for user {user_id}")
        return True
        
    except Exception as e:
        print(f"Error processing subscription cancelled webhook: {e}")
        return False

def process_payment_completed(webhook_data):
    """
    Process transaction.completed webhook from Paddle (for successful payments)
    """
    try:
        print("💳 Processing payment completed webhook")
        
        # Extract data from Paddle v2 webhook structure
        data = webhook_data.get('data', {})
        
        # Get transaction details
        transaction_id = data.get('id')
        status = data.get('status')
        
        # Get custom data (this is where we store user info)
        custom_data = data.get('custom_data', {})
        user_id = custom_data.get('userId')
        plan_id = custom_data.get('planId')
        billing_period = custom_data.get('billingPeriod', 'monthly')
        
        # Alternative: check items for price ID to determine plan
        items = data.get('details', {}).get('line_items', [])
        if not plan_id and items:
            price_id = items[0].get('price_id')
            plan_id, billing_period = get_plan_from_price_id(price_id)
        
        print(f"💰 Payment details: user={user_id}, plan={plan_id}, period={billing_period}")
        
        if not user_id or not plan_id:
            print("❌ Missing user_id or plan_id in payment webhook")
            return False
        
        # Get plan configuration
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config.plans import PLANS
        
        if plan_id not in PLANS:
            print(f"❌ Invalid plan ID: {plan_id}")
            return False
        
        plan_config = PLANS[plan_id]
        
        # Get Firestore client
        db = firestore.client()
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            print(f"❌ User {user_id} not found in Firestore")
            return False
        
        current_data = user_doc.to_dict()
        now = datetime.utcnow()
        
        # Calculate end date based on billing period
        if billing_period == 'yearly':
            end_date = now + timedelta(days=365)
        else:
            end_date = now + timedelta(days=30)
        
        # Get plan history
        plan_history = current_data.get('planHistory', [])
        
        # End current plan if it exists
        if plan_history:
            current_plan_entry = plan_history[-1]
            if not current_plan_entry.get('endDate'):
                current_plan_entry['endDate'] = now.isoformat()
        
        # Calculate credits based on billing period
        credits_to_allocate = plan_config['yearlyCredits'] if billing_period == 'yearly' else plan_config['monthlyCredits']
        
        print(f"💳 Plan upgrade: {plan_id} ({billing_period})")
        print(f"💰 Credits to allocate: {credits_to_allocate}")
        print(f"👤 User: {user_id}")
        
        # Add new plan to history
        plan_history.append({
            'planId': plan_id,
            'startDate': now.isoformat(),
            'endDate': end_date.isoformat(),
            'creditsAllocated': credits_to_allocate,
            'transactionId': transaction_id,
            'billingPeriod': billing_period,
            'reason': 'payment_completed'
        })
        
        # Prepare update data
        update_data = {
            'currentPlan': plan_id,
            'planHistory': plan_history,
            'subscriptionStatus': 'active',
            'planStartDate': now.isoformat(),
            'planEndDate': end_date.isoformat(),
            'autoRenew': True,
            'credits': (current_data.get('credits', 0) + credits_to_allocate),
            'lastCreditUpdate': now.isoformat(),
            'lastPlanUpdate': now.isoformat(),
            'paymentMetadata': {
                'billingPeriod': billing_period,
                'transactionId': transaction_id,
                'paymentMethod': 'paddle',
                'updatedAt': now.isoformat()
            }
        }
        
        # Update user document
        user_ref.update(update_data)
        
        final_credits = current_data.get('credits', 0) + credits_to_allocate
        print(f"✅ Successfully processed payment for user {user_id} - {plan_id} plan")
        print(f"💰 Final credit balance: {final_credits}")
        return True
        
    except Exception as e:
        print(f"❌ Error processing payment completed webhook: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_plan_from_price_id(price_id):
    """
    Get plan ID and billing period from Paddle price ID
    """
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config.plans import PLANS
    
    for plan_id, plan_config in PLANS.items():
        if plan_id == 'free':
            continue
        paddle_ids = plan_config.get('paddle_price_ids', {})
        if price_id == paddle_ids.get('monthly'):
            return plan_id, 'monthly'
        elif price_id == paddle_ids.get('yearly'):
            return plan_id, 'yearly'
    
    return None, None

def handle_paddle_webhook(webhook_data, signature, webhook_secret):
    """
    Main webhook handler that routes to appropriate processor based on event type
    """
    try:
        print(f"🔔 Received webhook data: {json.dumps(webhook_data, indent=2)}")
        
        # Verify webhook signature
        if not verify_paddle_webhook(json.dumps(webhook_data), signature, webhook_secret):
            print("❌ Invalid webhook signature")
            return False
            
        # Paddle v2 uses 'event_type' instead of 'alert_name'
        event_type = webhook_data.get('event_type') or webhook_data.get('alert_name')
        
        print(f"📋 Processing event type: {event_type}")
        
        # Route to appropriate handler - Paddle v2 event names
        if event_type in ['subscription.created', 'subscription_created']:
            return process_subscription_created(webhook_data)
        elif event_type in ['subscription.updated', 'subscription_updated']:
            return process_subscription_updated(webhook_data)
        elif event_type in ['subscription.canceled', 'subscription_cancelled']:
            return process_subscription_cancelled(webhook_data)
        elif event_type in ['transaction.completed', 'payment_succeeded']:
            # Handle successful payment - this might be what we need
            return process_payment_completed(webhook_data)
        else:
            print(f"⚠️ Unhandled webhook event type: {event_type}")
            print(f"📄 Available keys in webhook: {list(webhook_data.keys())}")
            return True  # Return True for unhandled events to avoid retries
            
    except Exception as e:
        print(f"❌ Error handling paddle webhook: {e}")
        import traceback
        traceback.print_exc()
        return False