"""
Collaboration Service

Handles workspace management, user invitations, and role-based access control
for collaborative note generation and viewing.
"""

import os
import logging
import uuid
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from firebase_admin import firestore
from resend_service import resend_service

logger = logging.getLogger(__name__)

class CollaborationService:
    def __init__(self, db_client=None):
        self.db = db_client
        
    def set_db(self, db_client):
        """Set the Firestore database client"""
        self.db = db_client
        
    async def create_workspace(self, owner_id: str, name: str, description: str = None) -> Dict:
        """Create a new workspace"""
        try:
            if not self.db:
                raise Exception("Database not initialized")
                
            workspace_id = str(uuid.uuid4())
            workspace_data = {
                'id': workspace_id,
                'name': name,
                'description': description or '',
                'owner_id': owner_id,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'members': {
                    owner_id: {
                        'role': 'owner',
                        'joined_at': datetime.utcnow(),
                        'status': 'active'
                    }
                },
                'settings': {
                    'allow_view_role': True,
                    'allow_generate_role': True,
                    'require_approval': False
                }
            }
            
            # Save to Firestore
            self.db.collection('workspaces').document(workspace_id).set(workspace_data)
            
            logger.info(f"✅ Created workspace {workspace_id} for user {owner_id}")
            return {
                'success': True,
                'workspace_id': workspace_id,
                'workspace': workspace_data
            }
            
        except Exception as e:
            logger.error(f"❌ Error creating workspace: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_user_workspaces(self, user_id: str) -> Dict:
        """Get all workspaces where user is a member"""
        try:
            logger.info(f"🔍 Getting workspaces for user: {user_id}")
            
            if not self.db:
                logger.error("❌ Database not initialized in collaboration service")
                raise Exception("Database not initialized")
                
            # Query workspaces where user is a member
            workspaces_ref = self.db.collection('workspaces')
            logger.info(f"🔍 Querying workspaces collection...")
            
            query = workspaces_ref.where(f'members.{user_id}', '!=', None)
            logger.info(f"🔍 Created query for user: {user_id}")
            
            workspaces = []
            doc_count = 0
            for doc in query.stream():
                doc_count += 1
                logger.info(f"🔍 Processing workspace document {doc_count}: {doc.id}")
                workspace_data = doc.to_dict()
                workspace_data['id'] = doc.id
                
                # Get user's role in this workspace
                user_role = workspace_data.get('members', {}).get(user_id, {}).get('role', 'view')
                workspace_data['user_role'] = user_role
                
                workspaces.append(workspace_data)
            
            logger.info(f"✅ Found {len(workspaces)} workspaces for user {user_id}")
            return {
                'success': True,
                'workspaces': workspaces
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting user workspaces: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return {'success': False, 'error': str(e)}
    
    async def invite_collaborator(self, workspace_id: str, inviter_id: str, email: str, role: str, workspace_name: str = None) -> Dict:
        """Invite a collaborator to a workspace"""
        try:
            if not self.db:
                raise Exception("Database not initialized")
                
            # Validate role
            if role not in ['view', 'generate']:
                raise Exception("Invalid role. Must be 'view' or 'generate'")
                
            # Check if inviter has permission to invite
            workspace_ref = self.db.collection('workspaces').document(workspace_id)
            workspace_doc = workspace_ref.get()
            
            if not workspace_doc.exists:
                raise Exception("Workspace not found")
                
            workspace_data = workspace_doc.to_dict()
            inviter_role = workspace_data.get('members', {}).get(inviter_id, {}).get('role')
            
            if inviter_role not in ['owner', 'admin']:
                raise Exception("You don't have permission to invite collaborators")
            
            # Generate invitation token
            invitation_token = secrets.token_urlsafe(32)
            invitation_id = str(uuid.uuid4())
            
            # Create invitation record
            invitation_data = {
                'id': invitation_id,
                'workspace_id': workspace_id,
                'workspace_name': workspace_name or workspace_data.get('name', 'Untitled Workspace'),
                'inviter_id': inviter_id,
                'invitee_email': email,
                'role': role,
                'token': invitation_token,
                'status': 'pending',
                'created_at': datetime.utcnow(),
                'expires_at': datetime.utcnow() + timedelta(days=7)  # 7 days expiry
            }
            
            # Save invitation
            self.db.collection('invitations').document(invitation_id).set(invitation_data)
            
            # Send invitation email
            await self._send_invitation_email(
                email=email,
                workspace_name=workspace_name or workspace_data.get('name', 'Untitled Workspace'),
                inviter_name=workspace_data.get('members', {}).get(inviter_id, {}).get('name', 'Someone'),
                role=role,
                invitation_token=invitation_token
            )
            
            logger.info(f"✅ Sent invitation to {email} for workspace {workspace_id}")
            return {
                'success': True,
                'invitation_id': invitation_id,
                'message': f'Invitation sent to {email}'
            }
            
        except Exception as e:
            logger.error(f"❌ Error inviting collaborator: {e}")
            return {'success': False, 'error': str(e)}
    
    async def accept_invitation(self, user_id: str, user_email: str, invitation_token: str) -> Dict:
        """Accept a collaboration invitation"""
        try:
            if not self.db:
                raise Exception("Database not initialized")
                
            # Find invitation by token
            invitations_ref = self.db.collection('invitations')
            query = invitations_ref.where('token', '==', invitation_token).where('status', '==', 'pending')
            
            invitation_doc = None
            for doc in query.stream():
                invitation_doc = doc
                break
                
            if not invitation_doc:
                raise Exception("Invalid or expired invitation")
                
            invitation_data = invitation_doc.to_dict()
            
            # Check if invitation is expired
            if datetime.utcnow() > invitation_data['expires_at']:
                raise Exception("Invitation has expired")
                
            # Check if email matches
            if user_email != invitation_data['invitee_email']:
                raise Exception("This invitation is for a different email address")
                
            # Add user to workspace
            workspace_id = invitation_data['workspace_id']
            workspace_ref = self.db.collection('workspaces').document(workspace_id)
            
            # Update workspace members
            workspace_ref.update({
                f'members.{user_id}': {
                    'role': invitation_data['role'],
                    'joined_at': datetime.utcnow(),
                    'status': 'active',
                    'email': user_email
                }
            })
            
            # Mark invitation as accepted
            invitation_doc.reference.update({
                'status': 'accepted',
                'accepted_at': datetime.utcnow(),
                'accepted_by': user_id
            })
            
            logger.info(f"✅ User {user_id} accepted invitation to workspace {workspace_id}")
            return {
                'success': True,
                'workspace_id': workspace_id,
                'role': invitation_data['role'],
                'message': 'Successfully joined workspace'
            }
            
        except Exception as e:
            logger.error(f"❌ Error accepting invitation: {e}")
            return {'success': False, 'error': str(e)}
    
    async def update_collaborator_role(self, workspace_id: str, updater_id: str, collaborator_id: str, new_role: str) -> Dict:
        """Update a collaborator's role in a workspace"""
        try:
            if not self.db:
                raise Exception("Database not initialized")
                
            # Validate role
            if new_role not in ['view', 'generate', 'admin']:
                raise Exception("Invalid role. Must be 'view', 'generate', or 'admin'")
                
            workspace_ref = self.db.collection('workspaces').document(workspace_id)
            workspace_doc = workspace_ref.get()
            
            if not workspace_doc.exists:
                raise Exception("Workspace not found")
                
            workspace_data = workspace_doc.to_dict()
            updater_role = workspace_data.get('members', {}).get(updater_id, {}).get('role')
            
            # Check permissions
            if updater_role not in ['owner', 'admin']:
                raise Exception("You don't have permission to update roles")
                
            # Can't change owner role
            collaborator_role = workspace_data.get('members', {}).get(collaborator_id, {}).get('role')
            if collaborator_role == 'owner':
                raise Exception("Cannot change owner role")
                
            # Update role
            workspace_ref.update({
                f'members.{collaborator_id}.role': new_role,
                f'members.{collaborator_id}.updated_at': datetime.utcnow()
            })
            
            logger.info(f"✅ Updated role for {collaborator_id} to {new_role} in workspace {workspace_id}")
            return {
                'success': True,
                'message': f'Role updated to {new_role}'
            }
            
        except Exception as e:
            logger.error(f"❌ Error updating collaborator role: {e}")
            return {'success': False, 'error': str(e)}
    
    async def remove_collaborator(self, workspace_id: str, remover_id: str, collaborator_id: str) -> Dict:
        """Remove a collaborator from a workspace"""
        try:
            if not self.db:
                raise Exception("Database not initialized")
                
            workspace_ref = self.db.collection('workspaces').document(workspace_id)
            workspace_doc = workspace_ref.get()
            
            if not workspace_doc.exists:
                raise Exception("Workspace not found")
                
            workspace_data = workspace_doc.to_dict()
            remover_role = workspace_data.get('members', {}).get(remover_id, {}).get('role')
            collaborator_role = workspace_data.get('members', {}).get(collaborator_id, {}).get('role')
            
            # Check permissions
            if remover_role not in ['owner', 'admin'] and remover_id != collaborator_id:
                raise Exception("You don't have permission to remove this collaborator")
                
            # Can't remove owner
            if collaborator_role == 'owner':
                raise Exception("Cannot remove workspace owner")
                
            # Remove collaborator
            workspace_ref.update({
                f'members.{collaborator_id}': firestore.DELETE_FIELD
            })
            
            logger.info(f"✅ Removed collaborator {collaborator_id} from workspace {workspace_id}")
            return {
                'success': True,
                'message': 'Collaborator removed successfully'
            }
            
        except Exception as e:
            logger.error(f"❌ Error removing collaborator: {e}")
            return {'success': False, 'error': str(e)}

    async def ban_collaborator(self, workspace_id: str, updater_id: str, collaborator_id: str) -> Dict:
        """Ban a collaborator from a workspace (cannot view or generate)"""
        try:
            if not self.db:
                raise Exception("Database not initialized")

            workspace_ref = self.db.collection('workspaces').document(workspace_id)
            workspace_doc = workspace_ref.get()
            if not workspace_doc.exists:
                raise Exception("Workspace not found")

            workspace_data = workspace_doc.to_dict()
            updater_role = workspace_data.get('members', {}).get(updater_id, {}).get('role')
            collaborator_role = workspace_data.get('members', {}).get(collaborator_id, {}).get('role')

            if updater_role not in ['owner', 'admin']:
                raise Exception("You don't have permission to ban collaborators")
            if collaborator_role == 'owner':
                raise Exception("Cannot ban workspace owner")

            workspace_ref.update({
                f'members.{collaborator_id}.status': 'banned',
                f'members.{collaborator_id}.banned_at': datetime.utcnow()
            })
            logger.info(f"🚫 Banned collaborator {collaborator_id} in workspace {workspace_id}")
            return { 'success': True, 'message': 'Collaborator banned' }
        except Exception as e:
            logger.error(f"❌ Error banning collaborator: {e}")
            return { 'success': False, 'error': str(e) }

    async def unban_collaborator(self, workspace_id: str, updater_id: str, collaborator_id: str) -> Dict:
        """Unban a collaborator (restore to active)"""
        try:
            if not self.db:
                raise Exception("Database not initialized")

            workspace_ref = self.db.collection('workspaces').document(workspace_id)
            workspace_doc = workspace_ref.get()
            if not workspace_doc.exists:
                raise Exception("Workspace not found")

            workspace_data = workspace_doc.to_dict()
            updater_role = workspace_data.get('members', {}).get(updater_id, {}).get('role')
            if updater_role not in ['owner', 'admin']:
                raise Exception("You don't have permission to unban collaborators")

            workspace_ref.update({
                f'members.{collaborator_id}.status': 'active',
                f'members.{collaborator_id}.updated_at': datetime.utcnow()
            })
            logger.info(f"✅ Unbanned collaborator {collaborator_id} in workspace {workspace_id}")
            return { 'success': True, 'message': 'Collaborator unbanned' }
        except Exception as e:
            logger.error(f"❌ Error unbanning collaborator: {e}")
            return { 'success': False, 'error': str(e) }
    
    async def get_workspace_details(self, workspace_id: str, user_id: str) -> Dict:
        """Get detailed information about a workspace"""
        try:
            if not self.db:
                raise Exception("Database not initialized")
                
            workspace_ref = self.db.collection('workspaces').document(workspace_id)
            workspace_doc = workspace_ref.get()
            
            if not workspace_doc.exists:
                raise Exception("Workspace not found")
                
            workspace_data = workspace_doc.to_dict()
            
            # Check if user is a member
            if user_id not in workspace_data.get('members', {}):
                raise Exception("You don't have access to this workspace")
                
            # Get user's role and status
            member_info = workspace_data.get('members', {}).get(user_id, {})
            user_role = member_info.get('role', 'view')
            user_status = member_info.get('status', 'active')
            workspace_data['user_role'] = user_role
            workspace_data['user_status'] = user_status
            
            # Get invitations (only for owners/admins)
            if user_role in ['owner', 'admin']:
                invitations_ref = self.db.collection('invitations')
                # Pending invitations
                pending_query = invitations_ref.where('workspace_id', '==', workspace_id).where('status', '==', 'pending')
                pending_invitations = []
                for doc in pending_query.stream():
                    invitation_data = doc.to_dict()
                    invitation_data['id'] = doc.id
                    pending_invitations.append(invitation_data)
                workspace_data['pending_invitations'] = pending_invitations

                # All invitations for tracking status in dashboard
                all_query = invitations_ref.where('workspace_id', '==', workspace_id)
                invitations = []
                for doc in all_query.stream():
                    inv = doc.to_dict()
                    inv['id'] = doc.id
                    invitations.append(inv)
                # Sort by created_at desc if available
                try:
                    invitations.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
                except Exception:
                    pass
                workspace_data['invitations'] = invitations
            
            return {
                'success': True,
                'workspace': workspace_data
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting workspace details: {e}")
            return {'success': False, 'error': str(e)}
    
    async def check_user_permission(self, workspace_id: str, user_id: str, required_permission: str) -> bool:
        """Check if user has required permission in workspace"""
        try:
            if not self.db:
                return False
                
            workspace_ref = self.db.collection('workspaces').document(workspace_id)
            workspace_doc = workspace_ref.get()
            
            if not workspace_doc.exists:
                return False
                
            workspace_data = workspace_doc.to_dict()
            member = workspace_data.get('members', {}).get(user_id, {})
            user_role = member.get('role')
            user_status = member.get('status', 'active')
            
            if not user_role or user_status == 'banned':
                return False
                
            # Permission mapping
            permissions = {
                'view': ['view'],
                'generate': ['view', 'generate'],
                'admin': ['view', 'generate', 'admin'],
                'owner': ['view', 'generate', 'admin', 'owner']
            }
            
            return required_permission in permissions.get(user_role, [])
            
        except Exception as e:
            logger.error(f"❌ Error checking user permission: {e}")
            return False
    
    async def _send_invitation_email(self, email: str, workspace_name: str, inviter_name: str, role: str, invitation_token: str):
        """Send invitation email to collaborator"""
        try:
            subject = f"You've been invited to collaborate on {workspace_name}"
            
            # Create invitation link
            invitation_link = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/accept-invitation?token={invitation_token}"
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #333;">Collaboration Invitation</h2>
                <p>Hi there!</p>
                <p><strong>{inviter_name}</strong> has invited you to collaborate on the workspace <strong>"{workspace_name}"</strong>.</p>
                <p>You've been given <strong>{role}</strong> access, which means you can:</p>
                <ul>
                    <li>View generated notes and diagrams</li>
                    {f'<li>Generate new notes from videos</li>' if role == 'generate' else ''}
                </ul>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{invitation_link}" 
                       style="background-color: #4F46E5; color: white; padding: 12px 24px; 
                              text-decoration: none; border-radius: 6px; display: inline-block;">
                        Accept Invitation
                    </a>
                </div>
                <p style="color: #666; font-size: 14px;">
                    This invitation will expire in 7 days. If you don't have an account, 
                    you'll be prompted to create one when you click the link.
                </p>
                <p style="color: #666; font-size: 12px;">
                    If the button doesn't work, copy and paste this link into your browser:<br>
                    {invitation_link}
                </p>
            </div>
            """
            
            # Send email using Resend service
            await resend_service.send_email(
                to_email=email,
                subject=subject,
                html_content=html_content
            )
            
            logger.info(f"✅ Sent invitation email to {email}")
            
        except Exception as e:
            logger.error(f"❌ Error sending invitation email: {e}")
            raise

# Create global instance
collaboration_service = CollaborationService()