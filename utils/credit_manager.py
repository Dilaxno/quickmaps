"""
Credit Management System
Handles credit validation and deduction for QuickMind operations
"""

import os
import firebase_admin
from firebase_admin import firestore
from typing import Dict, Any, Optional
import logging
import asyncio

logger = logging.getLogger(__name__)

class CreditManager:
    def __init__(self):
        """Initialize the credit manager with Firestore connection"""
        try:
            # Try to get existing Firebase app
            self.db = firestore.client()
        except ValueError:
            # If no app exists, initialize Firebase
            import firebase_admin
            from firebase_admin import credentials
            
            # Initialize Firebase Admin SDK
            if not firebase_admin._apps:
                # Use default credentials (service account key should be in environment)
                cred = credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred, {
                    'projectId': 'quickmind-58aff'
                })
            
            self.db = firestore.client()
        
        self.CREDITS_PER_GENERATION = 10
        self.DEFAULT_NEW_USER_CREDITS = 10

    async def get_user_credits(self, user_id: str) -> int:
        """Get current credit balance for a user"""
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if not user_doc.exists:
                logger.warning(f"User document not found for user_id: {user_id}")
                return 0
            
            user_data = user_doc.to_dict()
            return user_data.get('credits', 0)
        
        except Exception as e:
            logger.error(f"Error getting credits for user {user_id}: {str(e)}")
            return 0

    async def check_sufficient_credits(self, user_id: str, required_credits: int = None) -> Dict[str, Any]:
        """Check if user has sufficient credits for an operation"""
        if required_credits is None:
            required_credits = self.CREDITS_PER_GENERATION
        
        try:
            current_credits = await self.get_user_credits(user_id)
            has_sufficient = current_credits >= required_credits
            
            return {
                'sufficient': has_sufficient,
                'current_credits': current_credits,
                'required_credits': required_credits,
                'deficit': max(0, required_credits - current_credits)
            }
        
        except Exception as e:
            logger.error(f"Error checking credits for user {user_id}: {str(e)}")
            return {
                'sufficient': False,
                'current_credits': 0,
                'required_credits': required_credits,
                'deficit': required_credits,
                'error': str(e)
            }

    async def deduct_credits(self, user_id: str, amount: int = None) -> Dict[str, Any]:
        """Deduct credits from user account"""
        if amount is None:
            amount = self.CREDITS_PER_GENERATION
        
        try:
            user_ref = self.db.collection('users').document(user_id)
            
            # Use a transaction to ensure atomic operation
            @firestore.transactional
            def update_credits(transaction, user_ref):
                user_doc = user_ref.get(transaction=transaction)
                
                if not user_doc.exists:
                    raise Exception(f"User document not found for user_id: {user_id}")
                
                user_data = user_doc.to_dict()
                current_credits = user_data.get('credits', 0)
                
                if current_credits < amount:
                    raise Exception(f"Insufficient credits. Required: {amount}, Available: {current_credits}")
                
                new_credits = current_credits - amount
                
                transaction.update(user_ref, {
                    'credits': new_credits,
                    'lastCreditUpdate': firestore.SERVER_TIMESTAMP,
                    'lastDeduction': {
                        'amount': amount,
                        'timestamp': firestore.SERVER_TIMESTAMP,
                        'operation': 'mindmap_generation'
                    }
                })
                
                return new_credits
            
            transaction = self.db.transaction()
            new_balance = update_credits(transaction, user_ref)
            
            logger.info(f"Credits deducted for user {user_id}: {amount} credits. New balance: {new_balance}")
            
            return {
                'success': True,
                'credits_deducted': amount,
                'new_balance': new_balance,
                'transaction_time': firestore.SERVER_TIMESTAMP
            }
        
        except Exception as e:
            logger.error(f"Error deducting credits for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'credits_deducted': 0
            }

    async def refund_credits(self, user_id: str, amount: int = None) -> Dict[str, Any]:
        """Refund credits to user account (for failed operations)"""
        if amount is None:
            amount = self.CREDITS_PER_GENERATION
        
        try:
            user_ref = self.db.collection('users').document(user_id)
            
            # Use a transaction to ensure atomic operation
            @firestore.transactional
            def refund_credits_transaction(transaction, user_ref):
                user_doc = user_ref.get(transaction=transaction)
                
                if not user_doc.exists:
                    raise Exception(f"User document not found for user_id: {user_id}")
                
                user_data = user_doc.to_dict()
                current_credits = user_data.get('credits', 0)
                new_credits = current_credits + amount
                
                transaction.update(user_ref, {
                    'credits': new_credits,
                    'lastCreditUpdate': firestore.SERVER_TIMESTAMP,
                    'lastRefund': {
                        'amount': amount,
                        'timestamp': firestore.SERVER_TIMESTAMP,
                        'reason': 'operation_failed'
                    }
                })
                
                return new_credits
            
            transaction = self.db.transaction()
            new_balance = refund_credits_transaction(transaction, user_ref)
            
            logger.info(f"Credits refunded for user {user_id}: {amount} credits. New balance: {new_balance}")
            
            return {
                'success': True,
                'credits_refunded': amount,
                'new_balance': new_balance,
                'transaction_time': firestore.SERVER_TIMESTAMP
            }
        
        except Exception as e:
            logger.error(f"Error refunding credits for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'credits_refunded': 0
            }

    async def add_credits(self, user_id: str, amount: int, reason: str = "admin_grant") -> Dict[str, Any]:
        """Add credits to user account (for purchases or admin grants)"""
        try:
            user_ref = self.db.collection('users').document(user_id)
            
            # Use a transaction to ensure atomic operation
            @firestore.transactional
            def add_credits_transaction(transaction, user_ref):
                user_doc = user_ref.get(transaction=transaction)
                
                if not user_doc.exists:
                    raise Exception(f"User document not found for user_id: {user_id}")
                
                user_data = user_doc.to_dict()
                current_credits = user_data.get('credits', 0)
                new_credits = current_credits + amount
                
                transaction.update(user_ref, {
                    'credits': new_credits,
                    'lastCreditUpdate': firestore.SERVER_TIMESTAMP,
                    'lastCreditGrant': {
                        'amount': amount,
                        'timestamp': firestore.SERVER_TIMESTAMP,
                        'reason': reason
                    }
                })
                
                return new_credits
            
            transaction = self.db.transaction()
            new_balance = add_credits_transaction(transaction, user_ref)
            
            logger.info(f"Credits added for user {user_id}: {amount} credits. Reason: {reason}. New balance: {new_balance}")
            
            return {
                'success': True,
                'credits_added': amount,
                'new_balance': new_balance,
                'reason': reason,
                'transaction_time': firestore.SERVER_TIMESTAMP
            }
        
        except Exception as e:
            logger.error(f"Error adding credits for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'credits_added': 0
            }

    async def initialize_user_credits(self, user_id: str) -> Dict[str, Any]:
        """Initialize credits for a new user (called during user creation)"""
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                if 'credits' in user_data:
                    # User already has credits initialized
                    return {
                        'success': True,
                        'already_initialized': True,
                        'current_credits': user_data.get('credits', 0)
                    }
            
            # Initialize credits for new user
            user_ref.update({
                'credits': self.DEFAULT_NEW_USER_CREDITS,
                'lastCreditUpdate': firestore.SERVER_TIMESTAMP,
                'creditHistory': [{
                    'type': 'initial_grant',
                    'amount': self.DEFAULT_NEW_USER_CREDITS,
                    'timestamp': firestore.SERVER_TIMESTAMP,
                    'reason': 'new_user_signup'
                }]
            })
            
            logger.info(f"Credits initialized for new user {user_id}: {self.DEFAULT_NEW_USER_CREDITS} credits")
            
            return {
                'success': True,
                'credits_granted': self.DEFAULT_NEW_USER_CREDITS,
                'new_balance': self.DEFAULT_NEW_USER_CREDITS
            }
        
        except Exception as e:
            logger.error(f"Error initializing credits for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

# Global instance
credit_manager = None

def get_credit_manager() -> CreditManager:
    """Get or create the global credit manager instance"""
    global credit_manager
    if credit_manager is None:
        credit_manager = CreditManager()
    return credit_manager