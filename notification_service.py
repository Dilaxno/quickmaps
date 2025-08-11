"""
Notification Service for handling user notifications after successful payments
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class NotificationType(Enum):
    PAYMENT_SUCCESS = "payment_success"
    PLAN_UPGRADE = "plan_upgrade"
    SUBSCRIPTION_ACTIVATED = "subscription_activated"
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    CREDITS_ALLOCATED = "credits_allocated"
    WELCOME = "welcome"

@dataclass
class Notification:
    """Notification data structure"""
    id: str
    user_id: str
    type: NotificationType
    title: str
    message: str
    data: Dict[str, Any]
    created_at: str
    read: bool = False
    priority: str = "normal"  # low, normal, high, urgent

class NotificationService:
    """Service for handling user notifications"""
    
    def __init__(self, db_client=None):
        self.db = db_client
    
    async def create_payment_success_notification(self, user_id: str, plan_name: str, 
                                                billing_cycle: str, credits: int, 
                                                transaction_id: str) -> bool:
        """Create notification for successful payment"""
        try:
            title = "🎉 Payment Successful!"
            message = f"Successfully subscribed to {plan_name} {billing_cycle} plan! You now have {credits} credits available."
            
            notification_data = {
                'plan_name': plan_name,
                'billing_cycle': billing_cycle,
                'credits': credits,
                'transaction_id': transaction_id,
                'celebration': True
            }
            
            return await self.create_notification(
                user_id=user_id,
                notification_type=NotificationType.PAYMENT_SUCCESS,
                title=title,
                message=message,
                data=notification_data,
                priority="high"
            )
            
        except Exception as e:
            logger.error(f"❌ Error creating payment success notification: {e}")
            return False
    
    async def create_plan_upgrade_notification(self, user_id: str, old_plan: str, 
                                             new_plan: str, credits: int) -> bool:
        """Create notification for plan upgrade"""
        try:
            title = "🚀 Plan Upgraded!"
            message = f"Your plan has been upgraded from {old_plan} to {new_plan}. You now have {credits} credits."
            
            notification_data = {
                'old_plan': old_plan,
                'new_plan': new_plan,
                'credits': credits
            }
            
            return await self.create_notification(
                user_id=user_id,
                notification_type=NotificationType.PLAN_UPGRADE,
                title=title,
                message=message,
                data=notification_data,
                priority="high"
            )
            
        except Exception as e:
            logger.error(f"❌ Error creating plan upgrade notification: {e}")
            return False
    
    async def create_subscription_activated_notification(self, user_id: str, 
                                                       subscription_id: str) -> bool:
        """Create notification for subscription activation"""
        try:
            title = "✅ Subscription Activated"
            message = "Your subscription has been activated successfully. Enjoy your premium features!"
            
            notification_data = {
                'subscription_id': subscription_id
            }
            
            return await self.create_notification(
                user_id=user_id,
                notification_type=NotificationType.SUBSCRIPTION_ACTIVATED,
                title=title,
                message=message,
                data=notification_data,
                priority="normal"
            )
            
        except Exception as e:
            logger.error(f"❌ Error creating subscription activated notification: {e}")
            return False
    
    async def create_subscription_canceled_notification(self, user_id: str, 
                                                      subscription_id: str) -> bool:
        """Create notification for subscription cancellation"""
        try:
            title = "⚠️ Subscription Canceled"
            message = "Your subscription has been canceled. You can continue using your current plan until the end of your billing period."
            
            notification_data = {
                'subscription_id': subscription_id
            }
            
            return await self.create_notification(
                user_id=user_id,
                notification_type=NotificationType.SUBSCRIPTION_CANCELED,
                title=title,
                message=message,
                data=notification_data,
                priority="high"
            )
            
        except Exception as e:
            logger.error(f"❌ Error creating subscription canceled notification: {e}")
            return False
    
    async def create_credits_allocated_notification(self, user_id: str, credits: int, 
                                                  reason: str = "plan_upgrade") -> bool:
        """Create notification for credits allocation"""
        try:
            title = "💎 Credits Added!"
            message = f"{credits} credits have been added to your account."
            
            notification_data = {
                'credits': credits,
                'reason': reason
            }
            
            return await self.create_notification(
                user_id=user_id,
                notification_type=NotificationType.CREDITS_ALLOCATED,
                title=title,
                message=message,
                data=notification_data,
                priority="normal"
            )
            
        except Exception as e:
            logger.error(f"❌ Error creating credits allocated notification: {e}")
            return False
    
    async def create_welcome_notification(self, user_id: str, plan_name: str) -> bool:
        """Create welcome notification for new users"""
        try:
            title = "🎊 Welcome to QuickMind!"
            message = f"Welcome to QuickMind! You're now on the {plan_name} plan. Start creating amazing mind maps!"
            
            notification_data = {
                'plan_name': plan_name,
                'is_welcome': True
            }
            
            return await self.create_notification(
                user_id=user_id,
                notification_type=NotificationType.WELCOME,
                title=title,
                message=message,
                data=notification_data,
                priority="normal"
            )
            
        except Exception as e:
            logger.error(f"❌ Error creating welcome notification: {e}")
            return False
    
    async def create_notification(self, user_id: str, notification_type: NotificationType,
                                title: str, message: str, data: Dict[str, Any],
                                priority: str = "normal") -> bool:
        """Create a notification in Firestore"""
        try:
            if not self.db:
                logger.warning("⚠️ Database not available for notifications")
                return False
            
            notification_id = f"{user_id}_{notification_type.value}_{int(datetime.now().timestamp())}"
            
            notification_doc = {
                'id': notification_id,
                'user_id': user_id,
                'type': notification_type.value,
                'title': title,
                'message': message,
                'data': data,
                'created_at': datetime.now().isoformat(),
                'read': False,
                'priority': priority
            }
            
            # Store in user's notifications subcollection
            user_ref = self.db.collection('users').document(user_id)
            notifications_ref = user_ref.collection('notifications')
            notifications_ref.document(notification_id).set(notification_doc)
            
            # Also store in global notifications collection for admin purposes
            self.db.collection('notifications').document(notification_id).set(notification_doc)
            
            logger.info(f"✅ Created notification {notification_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating notification: {e}")
            return False
    
    async def get_user_notifications(self, user_id: str, limit: int = 50, 
                                   unread_only: bool = False) -> List[Dict[str, Any]]:
        """Get notifications for a user"""
        try:
            if not self.db:
                return []
            
            user_ref = self.db.collection('users').document(user_id)
            notifications_ref = user_ref.collection('notifications')
            
            query = notifications_ref.order_by('created_at', direction='DESCENDING').limit(limit)
            
            if unread_only:
                query = query.where('read', '==', False)
            
            docs = query.stream()
            notifications = []
            
            for doc in docs:
                notification_data = doc.to_dict()
                notifications.append(notification_data)
            
            logger.info(f"✅ Retrieved {len(notifications)} notifications for user {user_id}")
            return notifications
            
        except Exception as e:
            logger.error(f"❌ Error getting user notifications: {e}")
            return []
    
    async def mark_notification_read(self, user_id: str, notification_id: str) -> bool:
        """Mark a notification as read"""
        try:
            if not self.db:
                return False
            
            user_ref = self.db.collection('users').document(user_id)
            notification_ref = user_ref.collection('notifications').document(notification_id)
            
            notification_ref.update({
                'read': True,
                'read_at': datetime.now().isoformat()
            })
            
            # Also update in global collection
            self.db.collection('notifications').document(notification_id).update({
                'read': True,
                'read_at': datetime.now().isoformat()
            })
            
            logger.info(f"✅ Marked notification {notification_id} as read for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error marking notification as read: {e}")
            return False
    
    async def mark_all_notifications_read(self, user_id: str) -> bool:
        """Mark all notifications as read for a user"""
        try:
            if not self.db:
                return False
            
            user_ref = self.db.collection('users').document(user_id)
            notifications_ref = user_ref.collection('notifications')
            
            # Get all unread notifications
            unread_query = notifications_ref.where('read', '==', False)
            unread_docs = unread_query.stream()
            
            batch = self.db.batch()
            count = 0
            
            for doc in unread_docs:
                batch.update(doc.reference, {
                    'read': True,
                    'read_at': datetime.now().isoformat()
                })
                
                # Also update in global collection
                global_ref = self.db.collection('notifications').document(doc.id)
                batch.update(global_ref, {
                    'read': True,
                    'read_at': datetime.now().isoformat()
                })
                
                count += 1
            
            if count > 0:
                batch.commit()
                logger.info(f"✅ Marked {count} notifications as read for user {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error marking all notifications as read: {e}")
            return False
    
    async def delete_notification(self, user_id: str, notification_id: str) -> bool:
        """Delete a notification"""
        try:
            if not self.db:
                return False
            
            user_ref = self.db.collection('users').document(user_id)
            notification_ref = user_ref.collection('notifications').document(notification_id)
            
            notification_ref.delete()
            
            # Also delete from global collection
            self.db.collection('notifications').document(notification_id).delete()
            
            logger.info(f"✅ Deleted notification {notification_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deleting notification: {e}")
            return False
    
    async def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications for a user"""
        try:
            if not self.db:
                return 0
            
            user_ref = self.db.collection('users').document(user_id)
            notifications_ref = user_ref.collection('notifications')
            
            unread_query = notifications_ref.where('read', '==', False)
            unread_docs = list(unread_query.stream())
            
            count = len(unread_docs)
            logger.info(f"✅ User {user_id} has {count} unread notifications")
            return count
            
        except Exception as e:
            logger.error(f"❌ Error getting unread count: {e}")
            return 0