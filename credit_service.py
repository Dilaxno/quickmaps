"""
Credit Management Service for handling user credits and usage tracking
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import firebase_admin
from firebase_admin import firestore
from fastapi import HTTPException

# Configure logging
logger = logging.getLogger(__name__)

class CreditAction(Enum):
    VIDEO_UPLOAD = "video_upload"
    YOUTUBE_DOWNLOAD = "youtube_download"
    PDF_UPLOAD = "pdf_upload"
    QUIZ_GENERATION = "quiz_generation"

@dataclass
class CreditCost:
    """Credit costs for different actions"""
    VIDEO_UPLOAD = 1
    YOUTUBE_DOWNLOAD = 1
    PDF_UPLOAD = 1
    QUIZ_GENERATION = 1

@dataclass
class CreditCheckResult:
    """Result of credit check"""
    has_credits: bool
    current_credits: int
    credits_needed: int
    message: str

class CreditService:
    """Service for managing user credits and usage tracking"""
    
    def __init__(self, db_client=None):
        self.db = db_client
        self.credit_costs = {
            CreditAction.VIDEO_UPLOAD: CreditCost.VIDEO_UPLOAD,
            CreditAction.YOUTUBE_DOWNLOAD: CreditCost.YOUTUBE_DOWNLOAD,
            CreditAction.PDF_UPLOAD: CreditCost.PDF_UPLOAD,
            CreditAction.QUIZ_GENERATION: CreditCost.QUIZ_GENERATION,
        }
    
    async def check_credits(self, user_id: str, action: CreditAction) -> CreditCheckResult:
        """Check if user has enough credits without deducting them"""
        if not user_id or not self.db:
            # For anonymous users or when DB is not available, allow free usage
            return CreditCheckResult(
                has_credits=True,
                current_credits=999,
                credits_needed=0,
                message="Free usage (anonymous)"
            )
        
        credits_needed = self.credit_costs.get(action, 1)
        
        try:
            # Get user document
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if not user_doc.exists:
                # New user would get free trial credits, so they have credits
                return CreditCheckResult(
                    has_credits=True,
                    current_credits=10,  # Default trial credits
                    credits_needed=credits_needed,
                    message="New user with trial credits"
                )
            
            user_data = user_doc.to_dict()
            
            # Handle backward compatibility - check for both 'credits' and 'current_credits' fields
            current_credits = user_data.get('current_credits', 0)
            if current_credits == 0 and 'credits' in user_data:
                # Use the 'credits' field if 'current_credits' is 0 or missing
                current_credits = user_data.get('credits', 0)
                logger.info(f"🔄 Using legacy 'credits' field for check, user {user_id}: {current_credits}")
            
            # Check if user has enough credits
            if current_credits < credits_needed:
                return CreditCheckResult(
                    has_credits=False,
                    current_credits=current_credits,
                    credits_needed=credits_needed,
                    message=f"Insufficient credits. You have {current_credits} credits but need {credits_needed}."
                )
            
            return CreditCheckResult(
                has_credits=True,
                current_credits=current_credits,
                credits_needed=credits_needed,
                message=f"Sufficient credits available ({current_credits} credits)"
            )
            
        except Exception as e:
            logger.error(f"Error checking credits for user {user_id}: {e}")
            # On error, allow usage to avoid blocking users
            return CreditCheckResult(
                has_credits=True,
                current_credits=0,
                credits_needed=credits_needed,
                message="Credit check failed, allowing usage"
            )

    async def check_and_deduct_credits(self, user_id: str, action: CreditAction, user_email: str = None, user_name: str = None) -> CreditCheckResult:
        """Check if user has enough credits and deduct them if available"""
        if not user_id or not self.db:
            # For anonymous users or when DB is not available, allow free usage
            return CreditCheckResult(
                has_credits=True,
                current_credits=999,
                credits_needed=0,
                message="Free usage (anonymous)"
            )
        
        credits_needed = self.credit_costs.get(action, 1)
        
        try:
            # Get user document
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if not user_doc.exists:
                # New user - give them free trial credits
                await self._initialize_new_user(user_id, user_email, user_name)
                user_doc = user_ref.get()
            
            user_data = user_doc.to_dict()
            
            # Handle backward compatibility - check for both 'credits' and 'current_credits' fields
            current_credits = user_data.get('current_credits', 0)
            using_legacy_field = False
            if current_credits == 0 and 'credits' in user_data:
                # Use the 'credits' field if 'current_credits' is 0 or missing
                current_credits = user_data.get('credits', 0)
                using_legacy_field = True
                logger.info(f"🔄 Using legacy 'credits' field for deduction, user {user_id}: {current_credits}")
            
            # Check if user has enough credits
            if current_credits < credits_needed:
                return CreditCheckResult(
                    has_credits=False,
                    current_credits=current_credits,
                    credits_needed=credits_needed,
                    message=f"Insufficient credits. You have {current_credits} credits but need {credits_needed}."
                )
            
            # Deduct credits
            new_credits = current_credits - credits_needed
            credits_used = user_data.get('credits_used', 0) + credits_needed
            
            # Update user document - update both fields to standardize
            update_data = {
                'current_credits': new_credits,
                'credits_used': credits_used,
                'last_activity': datetime.now(),
                'last_action': action.value
            }
            
            # If using legacy field, also update the legacy field and migrate to new field
            if using_legacy_field:
                update_data['credits'] = new_credits  # Keep legacy field updated
                logger.info(f"🔄 Migrating user {user_id} to standardized credit fields")
            
            user_ref.update(update_data)
            
            # Log credit usage
            await self._log_credit_usage(user_id, action, credits_needed, new_credits)
            
            logger.info(f"💳 Credits deducted for user {user_id}: -{credits_needed} credits (remaining: {new_credits})")
            
            return CreditCheckResult(
                has_credits=True,
                current_credits=new_credits,
                credits_needed=credits_needed,
                message=f"Credits deducted successfully. Remaining: {new_credits}"
            )
            
        except Exception as e:
            logger.error(f"❌ Error checking/deducting credits for user {user_id}: {e}")
            # In case of error, allow the action to proceed
            return CreditCheckResult(
                has_credits=True,
                current_credits=999,
                credits_needed=0,
                message="Credit check failed - allowing action"
            )
    
    async def _initialize_new_user(self, user_id: str, user_email: str = None, user_name: str = None):
        """Initialize new user with free trial credits and send welcome email"""
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_data = {
                'user_id': user_id,
                'plan': 'free',
                'current_credits': 10,  # Free trial credits
                'credits_used': 0,
                'total_mindmaps': 0,
                'created_at': datetime.now(),
                'last_activity': datetime.now(),
                'account_status': 'active'
            }
            
            # Add email and name if provided
            if user_email:
                user_data['email'] = user_email
            if user_name:
                user_data['name'] = user_name
            
            user_ref.set(user_data)
            logger.info(f"🆕 Initialized new user {user_id} with 10 free credits")
            
            # Send welcome email if email is available
            if user_email and user_name:
                try:
                    from brevo_service import brevo_service
                    welcome_sent = brevo_service.send_welcome_email(
                        user_email=user_email,
                        user_name=user_name,
                        welcome_credits=10
                    )
                    if welcome_sent:
                        logger.info(f"📧 Welcome email sent to new user {user_email}")
                    else:
                        logger.warning(f"📧 Failed to send welcome email to {user_email}")
                except Exception as email_error:
                    logger.error(f"📧 Error sending welcome email to {user_email}: {email_error}")
            
        except Exception as e:
            logger.error(f"❌ Error initializing new user {user_id}: {e}")
    
    async def _log_credit_usage(self, user_id: str, action: CreditAction, credits_used: int, remaining_credits: int):
        """Log credit usage for analytics"""
        try:
            usage_ref = self.db.collection('credit_usage').document()
            usage_data = {
                'user_id': user_id,
                'action': action.value,
                'credits_used': credits_used,
                'remaining_credits': remaining_credits,
                'timestamp': datetime.now()
            }
            usage_ref.set(usage_data)
            
        except Exception as e:
            logger.error(f"❌ Error logging credit usage: {e}")
    
    async def get_user_credits(self, user_id: str, user_email: str = None, user_name: str = None) -> Dict:
        """Get user's current credit information"""
        if not user_id or not self.db:
            return {'current_credits': 999, 'plan': 'anonymous'}
        
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if not user_doc.exists:
                await self._initialize_new_user(user_id, user_email, user_name)
                user_doc = user_ref.get()
            
            user_data = user_doc.to_dict()
            
            # Handle backward compatibility - check for both 'credits' and 'current_credits' fields
            current_credits = user_data.get('current_credits', 0)
            if current_credits == 0 and 'credits' in user_data:
                # Use the 'credits' field if 'current_credits' is 0 or missing
                current_credits = user_data.get('credits', 0)
                logger.info(f"🔄 Using legacy 'credits' field for user {user_id}: {current_credits}")
            
            return {
                'current_credits': current_credits,
                'credits_used': user_data.get('credits_used', 0),
                'plan': user_data.get('plan', user_data.get('currentPlan', 'free')),  # Also handle 'currentPlan'
                'total_mindmaps': user_data.get('total_mindmaps', 0)
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting user credits: {e}")
            return {'current_credits': 0, 'plan': 'free'}
    
    async def add_credits(self, user_id: str, credits_to_add: int, reason: str = "manual_addition", user_email: str = None, user_name: str = None) -> bool:
        """Add credits to user account"""
        if not user_id or not self.db:
            return False
        
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if not user_doc.exists:
                await self._initialize_new_user(user_id, user_email, user_name)
                user_doc = user_ref.get()
            
            user_data = user_doc.to_dict()
            
            # Handle backward compatibility - check for both 'credits' and 'current_credits' fields
            current_credits = user_data.get('current_credits', 0)
            using_legacy_field = False
            if current_credits == 0 and 'credits' in user_data:
                # Use the 'credits' field if 'current_credits' is 0 or missing
                current_credits = user_data.get('credits', 0)
                using_legacy_field = True
                logger.info(f"🔄 Using legacy 'credits' field for addition, user {user_id}: {current_credits}")
            
            new_credits = current_credits + credits_to_add
            
            # Update user document - update both fields to standardize
            update_data = {
                'current_credits': new_credits,
                'last_activity': datetime.now()
            }
            
            # If using legacy field, also update the legacy field and migrate to new field
            if using_legacy_field:
                update_data['credits'] = new_credits  # Keep legacy field updated
                logger.info(f"🔄 Migrating user {user_id} to standardized credit fields during addition")
            
            user_ref.update(update_data)
            
            # Log credit addition
            credit_log_ref = self.db.collection('credit_additions').document()
            credit_log_ref.set({
                'user_id': user_id,
                'credits_added': credits_to_add,
                'reason': reason,
                'timestamp': datetime.now(),
                'new_total': new_credits
            })
            
            logger.info(f"💰 Added {credits_to_add} credits to user {user_id} (reason: {reason}). New total: {new_credits}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error adding credits to user {user_id}: {e}")
            return False

# Global credit service instance
credit_service = CreditService()