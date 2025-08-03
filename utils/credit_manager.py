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
        self.db = None
        self.CREDITS_PER_GENERATION = 10
        self.DEFAULT_NEW_USER_CREDITS = 10
        
        try:
            # Try to get existing Firebase app
            self.db = firestore.client()
            logger.info("CreditManager initialized successfully with existing Firebase app")
        except ValueError:
            # If no app exists, try to initialize Firebase
            try:
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
                logger.info("CreditManager initialized successfully with new Firebase app")
            except Exception as e:
                logger.error(f"Failed to initialize Firebase: {e}")
                logger.warning("CreditManager will operate in offline mode")
        except Exception as e:
            logger.error(f"Failed to initialize Firestore client: {e}")
            logger.warning("CreditManager will operate in offline mode")
    
    def _check_db_available(self):
        """Check if database is available, raise appropriate error if not"""
        if self.db is None:
            raise RuntimeError("CreditManager: Firebase/Firestore not initialized. Please set up Firebase credentials.")

    async def get_user_credits(self, user_id: str) -> int:
        """Get current credit balance for a user"""
        self._check_db_available()
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
        self._check_db_available()
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

    async def reserve_credits(self, user_id: str, amount: int = None, operation_id: str = None) -> Dict[str, Any]:
        """Reserve credits for an operation (two-phase commit approach)"""
        self._check_db_available()
        if amount is None:
            amount = self.CREDITS_PER_GENERATION
        
        if operation_id is None:
            import uuid
            operation_id = str(uuid.uuid4())
        
        try:
            user_ref = self.db.collection('users').document(user_id)
            
            # Use a transaction to ensure atomic operation
            @firestore.transactional
            def reserve_credits_transaction(transaction, user_ref):
                user_doc = user_ref.get(transaction=transaction)
                
                if not user_doc.exists:
                    raise Exception(f"User document not found for user_id: {user_id}")
                
                user_data = user_doc.to_dict()
                current_credits = user_data.get('credits', 0)
                reserved_credits = user_data.get('reservedCredits', {})
                
                # Calculate total reserved credits
                total_reserved = sum(reserved_credits.values()) if reserved_credits else 0
                available_credits = current_credits - total_reserved
                
                if available_credits < amount:
                    raise Exception(f"Insufficient credits. Required: {amount}, Available: {available_credits} (Total: {current_credits}, Reserved: {total_reserved})")
                
                # Add to reserved credits
                reserved_credits[operation_id] = amount
                
                transaction.update(user_ref, {
                    'reservedCredits': reserved_credits,
                    'lastCreditUpdate': firestore.SERVER_TIMESTAMP,
                    'lastReservation': {
                        'operation_id': operation_id,
                        'amount': amount,
                        'timestamp': firestore.SERVER_TIMESTAMP,
                        'operation': 'mindmap_generation'
                    }
                })
                
                return current_credits, available_credits - amount
            
            transaction = self.db.transaction()
            total_credits, remaining_available = reserve_credits_transaction(transaction, user_ref)
            
            logger.info(f"Credits reserved for user {user_id}: {amount} credits (Operation: {operation_id}). Available: {remaining_available}")
            
            return {
                'success': True,
                'operation_id': operation_id,
                'credits_reserved': amount,
                'total_credits': total_credits,
                'available_credits': remaining_available
            }
        
        except Exception as e:
            logger.error(f"Error reserving credits for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'credits_reserved': 0
            }

    async def confirm_credit_deduction(self, user_id: str, operation_id: str) -> Dict[str, Any]:
        """Confirm credit deduction for a reserved operation"""
        self._check_db_available()
        try:
            user_ref = self.db.collection('users').document(user_id)
            
            # Use a transaction to ensure atomic operation
            @firestore.transactional
            def confirm_deduction_transaction(transaction, user_ref):
                user_doc = user_ref.get(transaction=transaction)
                
                if not user_doc.exists:
                    raise Exception(f"User document not found for user_id: {user_id}")
                
                user_data = user_doc.to_dict()
                current_credits = user_data.get('credits', 0)
                reserved_credits = user_data.get('reservedCredits', {})
                
                if operation_id not in reserved_credits:
                    raise Exception(f"No reservation found for operation_id: {operation_id}")
                
                amount = reserved_credits[operation_id]
                new_credits = current_credits - amount
                
                # Remove from reserved credits
                del reserved_credits[operation_id]
                
                transaction.update(user_ref, {
                    'credits': new_credits,
                    'reservedCredits': reserved_credits,
                    'lastCreditUpdate': firestore.SERVER_TIMESTAMP,
                    'lastDeduction': {
                        'operation_id': operation_id,
                        'amount': amount,
                        'timestamp': firestore.SERVER_TIMESTAMP,
                        'operation': 'mindmap_generation'
                    }
                })
                
                return new_credits, amount
            
            transaction = self.db.transaction()
            new_balance, deducted_amount = confirm_deduction_transaction(transaction, user_ref)
            
            logger.info(f"Credits deducted for user {user_id}: {deducted_amount} credits (Operation: {operation_id}). New balance: {new_balance}")
            
            return {
                'success': True,
                'operation_id': operation_id,
                'credits_deducted': deducted_amount,
                'new_balance': new_balance
            }
        
        except Exception as e:
            logger.error(f"Error confirming credit deduction for user {user_id}, operation {operation_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'credits_deducted': 0
            }

    async def release_reserved_credits(self, user_id: str, operation_id: str) -> Dict[str, Any]:
        """Release reserved credits (cancel the reservation)"""
        self._check_db_available()
        try:
            user_ref = self.db.collection('users').document(user_id)
            
            # Use a transaction to ensure atomic operation
            @firestore.transactional
            def release_reservation_transaction(transaction, user_ref):
                user_doc = user_ref.get(transaction=transaction)
                
                if not user_doc.exists:
                    raise Exception(f"User document not found for user_id: {user_id}")
                
                user_data = user_doc.to_dict()
                reserved_credits = user_data.get('reservedCredits', {})
                
                if operation_id not in reserved_credits:
                    # Already released or never existed
                    return 0
                
                amount = reserved_credits[operation_id]
                
                # Remove from reserved credits
                del reserved_credits[operation_id]
                
                transaction.update(user_ref, {
                    'reservedCredits': reserved_credits,
                    'lastCreditUpdate': firestore.SERVER_TIMESTAMP,
                    'lastReservationRelease': {
                        'operation_id': operation_id,
                        'amount': amount,
                        'timestamp': firestore.SERVER_TIMESTAMP,
                        'reason': 'operation_failed_or_cancelled'
                    }
                })
                
                return amount
            
            transaction = self.db.transaction()
            released_amount = release_reservation_transaction(transaction, user_ref)
            
            logger.info(f"Reserved credits released for user {user_id}: {released_amount} credits (Operation: {operation_id})")
            
            return {
                'success': True,
                'operation_id': operation_id,
                'credits_released': released_amount
            }
        
        except Exception as e:
            logger.error(f"Error releasing reserved credits for user {user_id}, operation {operation_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'credits_released': 0
            }

    async def deduct_credits(self, user_id: str, amount: int = None) -> Dict[str, Any]:
        """Deduct credits from user account (legacy method - use reserve/confirm pattern for new operations)"""
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
        self._check_db_available()
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

    async def cleanup_expired_reservations(self, user_id: str, max_age_minutes: int = 30) -> Dict[str, Any]:
        """Clean up expired credit reservations (older than max_age_minutes)"""
        try:
            user_ref = self.db.collection('users').document(user_id)
            
            # Use a transaction to ensure atomic operation
            @firestore.transactional
            def cleanup_transaction(transaction, user_ref):
                user_doc = user_ref.get(transaction=transaction)
                
                if not user_doc.exists:
                    return 0, []
                
                user_data = user_doc.to_dict()
                reserved_credits = user_data.get('reservedCredits', {})
                last_reservation = user_data.get('lastReservation', {})
                
                if not reserved_credits:
                    return 0, []
                
                # Calculate cutoff time
                from datetime import datetime, timedelta
                cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)
                
                expired_operations = []
                total_released = 0
                
                # Check each reservation (simplified - in production you'd store timestamps per reservation)
                # For now, we'll use the lastReservation timestamp as a proxy
                last_reservation_time = last_reservation.get('timestamp')
                if last_reservation_time and hasattr(last_reservation_time, 'timestamp'):
                    reservation_datetime = datetime.fromtimestamp(last_reservation_time.timestamp())
                    if reservation_datetime < cutoff_time:
                        # All reservations are considered expired
                        for operation_id, amount in reserved_credits.items():
                            expired_operations.append(operation_id)
                            total_released += amount
                        
                        # Clear all reservations
                        transaction.update(user_ref, {
                            'reservedCredits': {},
                            'lastCreditUpdate': firestore.SERVER_TIMESTAMP,
                            'lastCleanup': {
                                'expired_operations': expired_operations,
                                'credits_released': total_released,
                                'timestamp': firestore.SERVER_TIMESTAMP,
                                'reason': 'expired_reservations'
                            }
                        })
                
                return total_released, expired_operations
            
            transaction = self.db.transaction()
            released_amount, expired_ops = cleanup_transaction(transaction, user_ref)
            
            if released_amount > 0:
                logger.info(f"Cleaned up expired reservations for user {user_id}: {released_amount} credits from {len(expired_ops)} operations")
            
            return {
                'success': True,
                'credits_released': released_amount,
                'expired_operations': expired_ops,
                'operations_cleaned': len(expired_ops)
            }
        
        except Exception as e:
            logger.error(f"Error cleaning up expired reservations for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'credits_released': 0
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