"""
Fresh Collaboration Service

Provides clean workspace management, invitations, and role-based access
controls used by the API endpoints in main.py. This is a full rewrite
with a simpler structure while maintaining the same public method names
and return shapes expected by the application.
"""

from __future__ import annotations

import os
import uuid
import secrets
import random
import string
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

from firebase_admin import firestore, auth
from resend_service import resend_service
from google.cloud.firestore_v1 import FieldFilter

logger = logging.getLogger(__name__)

# ---- Constants ----
VALID_ROLES = {"view", "generate", "admin", "owner"}
INVITE_VALID_ROLES = {"view", "generate"}
SESSION_TTL_HOURS = 24
INVITE_TTL_DAYS = 7


def _now() -> datetime:
    return datetime.utcnow()


def _normalize_dt(dt: Any) -> datetime:
    """Return a naive UTC datetime for Firestore Timestamp or datetime."""
    if hasattr(dt, "timestamp") and not isinstance(dt, datetime):
        # Firestore Timestamp
        return datetime.fromtimestamp(dt.timestamp())
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=None)
    return dt  # best effort


class CollaborationService:
    def __init__(self, db_client=None):
        self.db = db_client

    def set_db(self, db_client):
        self.db = db_client

    # --------------- Core: Workspaces ---------------
    async def create_workspace(self, owner_id: str, name: str, description: str | None = None) -> Dict:
        try:
            self._ensure_db()
            workspace_id = str(uuid.uuid4())
            now = _now()
            data = {
                "id": workspace_id,
                "name": name or "Untitled Workspace",
                "description": description or "",
                "owner_id": owner_id,
                "created_at": now,
                "updated_at": now,
                "members": {
                    owner_id: {
                        "role": "owner",
                        "status": "active",
                        "joined_at": now,
                    }
                },
                "settings": {
                    "allow_view_role": True,
                    "allow_generate_role": True,
                    "require_approval": False,
                },
            }
            self.db.collection("workspaces").document(workspace_id).set(data)
            return {"success": True, "workspace_id": workspace_id, "workspace": data}
        except Exception as e:
            logger.error(f"create_workspace failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_user_workspaces(self, user_id: str) -> Dict:
        try:
            self._ensure_db()
            q = self.db.collection("workspaces").where(filter=FieldFilter(f"members.{user_id}", "!=", None))
            workspaces = []
            for doc in q.stream():
                w = doc.to_dict()
                w["id"] = doc.id
                w["user_role"] = w.get("members", {}).get(user_id, {}).get("role", "view")
                workspaces.append(w)
            return {"success": True, "workspaces": workspaces}
        except Exception as e:
            logger.error(f"get_user_workspaces failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_workspace_details(self, workspace_id: str, user_id: str) -> Dict:
        try:
            self._ensure_db()
            doc = self.db.collection("workspaces").document(workspace_id).get()
            if not doc.exists:
                return {"success": False, "error": "Workspace not found"}
            w = doc.to_dict()
            if user_id not in w.get("members", {}):
                return {"success": False, "error": "You don't have access to this workspace"}
            member = w.get("members", {}).get(user_id, {})
            w["user_role"] = member.get("role", "view")
            w["user_status"] = member.get("status", "active")

            # Include invitation info for admins/owners
            if w["user_role"] in {"owner", "admin"}:
                invs = []
                all_q = self.db.collection("invitations").where(filter=FieldFilter("workspace_id", "==", workspace_id))
                for inv_doc in all_q.stream():
                    inv = inv_doc.to_dict()
                    inv["id"] = inv_doc.id
                    invs.append(inv)
                try:
                    invs.sort(key=lambda x: x.get("created_at") or datetime.min, reverse=True)
                except Exception:
                    pass
                w["invitations"] = invs
                pending = [i for i in invs if i.get("status") == "pending"]
                w["pending_invitations"] = pending

            return {"success": True, "workspace": w}
        except Exception as e:
            logger.error(f"get_workspace_details failed: {e}")
            return {"success": False, "error": str(e)}

    # --------------- Invitations ---------------
    async def invite_collaborator(self, workspace_id: str, inviter_id: str, email: str, role: str, workspace_name: Optional[str] = None) -> Dict:
        try:
            self._ensure_db()
            if role not in INVITE_VALID_ROLES:
                return {"success": False, "error": "Invalid role. Must be 'view' or 'generate'"}

            w_doc = self.db.collection("workspaces").document(workspace_id).get()
            if not w_doc.exists:
                return {"success": False, "error": "Workspace not found"}
            w = w_doc.to_dict()

            inviter_role = w.get("members", {}).get(inviter_id, {}).get("role")
            if inviter_role not in {"owner", "admin"}:
                return {"success": False, "error": "You don't have permission to invite collaborators"}

            invitation_id = str(uuid.uuid4())
            token = secrets.token_urlsafe(32)
            now = _now()
            expires_at = now + timedelta(days=INVITE_TTL_DAYS)
            invited_password = self._generate_invited_member_password()

            inv = {
                "id": invitation_id,
                "workspace_id": workspace_id,
                "workspace_name": workspace_name or w.get("name", "Untitled Workspace"),
                "inviter_id": inviter_id,
                "invitee_email": email,
                "role": role,
                "token": token,
                "status": "pending",
                "created_at": now,
                "expires_at": expires_at,
            }
            self.db.collection("invitations").document(invitation_id).set(inv)

            invited_member = {
                "id": invitation_id,  # same id for easy lookup
                "email": email,
                "password": invited_password,  # NOTE: hash in production
                "workspace_id": workspace_id,
                "workspace_name": inv["workspace_name"],
                "role": role,
                "inviter_id": inviter_id,
                "status": "pending",
                "created_at": now,
                "expires_at": expires_at,
            }
            self.db.collection("invited_members").document(invitation_id).set(invited_member)

            # Provision Firebase Auth user with the generated password
            firebase_uid = None
            try:
                try:
                    user = auth.get_user_by_email(email)
                    # Update password to the invited one so the user can sign in with provided credentials
                    auth.update_user(user.uid, password=invited_password)
                    firebase_uid = user.uid
                except auth.UserNotFoundError:
                    user = auth.create_user(email=email, password=invited_password)
                    firebase_uid = user.uid
            except Exception as fae:
                logger.warning(f"Firebase Auth provisioning failed for {email}: {fae}")
                firebase_uid = None

            # Mirror credentials in 'invitedmembers' collection for Firebase-based auth flows
            invitedmembers_doc = {
                "id": invitation_id,
                "email": email,
                "password": invited_password,  # NOTE: consider hashing in production
                "firebase_uid": firebase_uid,
                "workspace_id": workspace_id,
                "workspace_name": inv["workspace_name"],
                "role": role,
                "inviter_id": inviter_id,
                "status": "pending",
                "created_at": now,
                "expires_at": expires_at,
            }
            self.db.collection("invitedmembers").document(invitation_id).set(invitedmembers_doc)

            # Best-effort email
            try:
                await self._send_invitation_email(
                    email=email,
                    workspace_name=inv["workspace_name"],
                    inviter_name=w.get("members", {}).get(inviter_id, {}).get("name", "Someone"),
                    role=role,
                    invitation_token=token,
                    invited_member_password=invited_password,
                )
            except Exception as email_err:
                logger.warning(f"Failed to send invitation email to {email}: {email_err}")

            return {
                "success": True,
                "invitation_id": invitation_id,
                "message": f"Invitation created for {email}.",
            }
        except Exception as e:
            logger.error(f"invite_collaborator failed: {e}")
            return {"success": False, "error": str(e)}

    async def accept_invitation(self, user_id: str, user_email: str, invitation_token: str) -> Dict:
        try:
            self._ensure_db()
            q = (self.db.collection("invitations")
                 .where(filter=FieldFilter("token", "==", invitation_token))
                 .where(filter=FieldFilter("status", "==", "pending")))
            inv_doc = next(iter(q.stream()), None)
            if not inv_doc:
                return {"success": False, "error": "Invalid or expired invitation"}
            inv = inv_doc.to_dict()

            if user_email != inv.get("invitee_email"):
                return {"success": False, "error": "This invitation is for a different email address"}

            if _now() > _normalize_dt(inv["expires_at"]):
                return {"success": False, "error": "Invitation has expired"}

            ws_id = inv["workspace_id"]
            ws_ref = self.db.collection("workspaces").document(ws_id)
            ws_ref.update({
                f"members.{user_id}": {
                    "role": inv.get("role", "view"),
                    "joined_at": _now(),
                    "status": "active",
                    "email": user_email,
                }
            })

            inv_doc.reference.update({
                "status": "accepted",
                "accepted_at": _now(),
                "accepted_by": user_id,
            })

            return {
                "success": True,
                "workspace_id": ws_id,
                "role": inv.get("role", "view"),
                "message": "Successfully joined workspace",
            }
        except Exception as e:
            logger.error(f"accept_invitation failed: {e}")
            return {"success": False, "error": str(e)}

    # --------------- Membership Management ---------------
    async def update_collaborator_role(self, workspace_id: str, updater_id: str, collaborator_id: str, new_role: str) -> Dict:
        try:
            self._ensure_db()
            if new_role not in VALID_ROLES - {"owner"}:  # cannot set owner via this path
                return {"success": False, "error": "Invalid role. Must be 'view', 'generate', or 'admin'"}

            w_doc = self.db.collection("workspaces").document(workspace_id).get()
            if not w_doc.exists:
                return {"success": False, "error": "Workspace not found"}
            w = w_doc.to_dict()

            updater_role = w.get("members", {}).get(updater_id, {}).get("role")
            target_role = w.get("members", {}).get(collaborator_id, {}).get("role")
            if updater_role not in {"owner", "admin"}:
                return {"success": False, "error": "You don't have permission to update roles"}
            if target_role == "owner":
                return {"success": False, "error": "Cannot change owner role"}

            self.db.collection("workspaces").document(workspace_id).update({
                f"members.{collaborator_id}.role": new_role,
                f"members.{collaborator_id}.updated_at": _now(),
            })
            return {"success": True, "message": f"Role updated to {new_role}"}
        except Exception as e:
            logger.error(f"update_collaborator_role failed: {e}")
            return {"success": False, "error": str(e)}

    async def remove_collaborator(self, workspace_id: str, remover_id: str, collaborator_id: str) -> Dict:
        try:
            self._ensure_db()
            w_doc = self.db.collection("workspaces").document(workspace_id).get()
            if not w_doc.exists:
                return {"success": False, "error": "Workspace not found"}
            w = w_doc.to_dict()

            remover_role = w.get("members", {}).get(remover_id, {}).get("role")
            target_role = w.get("members", {}).get(collaborator_id, {}).get("role")

            if remover_role not in {"owner", "admin"} and remover_id != collaborator_id:
                return {"success": False, "error": "You don't have permission to remove this collaborator"}
            if target_role == "owner":
                return {"success": False, "error": "Cannot remove workspace owner"}

            self.db.collection("workspaces").document(workspace_id).update({
                f"members.{collaborator_id}": firestore.DELETE_FIELD
            })
            return {"success": True, "message": "Collaborator removed successfully"}
        except Exception as e:
            logger.error(f"remove_collaborator failed: {e}")
            return {"success": False, "error": str(e)}

    async def ban_collaborator(self, workspace_id: str, updater_id: str, collaborator_id: str) -> Dict:
        try:
            self._ensure_db()
            w_doc = self.db.collection("workspaces").document(workspace_id).get()
            if not w_doc.exists:
                return {"success": False, "error": "Workspace not found"}
            w = w_doc.to_dict()
            updater_role = w.get("members", {}).get(updater_id, {}).get("role")
            target_role = w.get("members", {}).get(collaborator_id, {}).get("role")
            if updater_role not in {"owner", "admin"}:
                return {"success": False, "error": "You don't have permission to ban collaborators"}
            if target_role == "owner":
                return {"success": False, "error": "Cannot ban workspace owner"}

            self.db.collection("workspaces").document(workspace_id).update({
                f"members.{collaborator_id}.status": "banned",
                f"members.{collaborator_id}.banned_at": _now(),
            })
            return {"success": True, "message": "Collaborator banned"}
        except Exception as e:
            logger.error(f"ban_collaborator failed: {e}")
            return {"success": False, "error": str(e)}

    async def unban_collaborator(self, workspace_id: str, updater_id: str, collaborator_id: str) -> Dict:
        try:
            self._ensure_db()
            w_doc = self.db.collection("workspaces").document(workspace_id).get()
            if not w_doc.exists:
                return {"success": False, "error": "Workspace not found"}
            w = w_doc.to_dict()
            updater_role = w.get("members", {}).get(updater_id, {}).get("role")
            if updater_role not in {"owner", "admin"}:
                return {"success": False, "error": "You don't have permission to unban collaborators"}

            self.db.collection("workspaces").document(workspace_id).update({
                f"members.{collaborator_id}.status": "active",
                f"members.{collaborator_id}.updated_at": _now(),
            })
            return {"success": True, "message": "Collaborator unbanned"}
        except Exception as e:
            logger.error(f"unban_collaborator failed: {e}")
            return {"success": False, "error": str(e)}

    # --------------- Invited Member Auth ---------------
    async def authenticate_invited_member(self, email: str, password: str) -> Dict:
        try:
            self._ensure_db()
            # Normalize inputs
            email_raw = str(email or "").strip()
            pw_input = str(password or "").strip()

            def fetch_docs_for_email(e: str):
                return list(
                    (self.db.collection("invitedmembers")
                        .where(filter=FieldFilter("email", "==", e))
                        .where(filter=FieldFilter("status", "==", "pending"))
                    ).stream()
                )

            docs = fetch_docs_for_email(email_raw)
            if not docs and email_raw.lower() != email_raw:
                # Try lowercase variant if nothing found (common normalization)
                docs = fetch_docs_for_email(email_raw.lower())

            if not docs:
                # Legacy fallback to old collection name
                def fetch_docs_legacy(e: str):
                    return list(
                        (self.db.collection("invited_members")
                            .where(filter=FieldFilter("email", "==", e))
                            .where(filter=FieldFilter("status", "==", "pending"))
                        ).stream()
                    )
                docs = fetch_docs_legacy(email_raw)
                if not docs and email_raw.lower() != email_raw:
                    docs = fetch_docs_legacy(email_raw.lower())

            if not docs:
                return {"success": False, "error": "Invalid email or invitation not found"}

            # Collect and filter non-expired invitations
            now = _now()
            invited_list = []
            for d in docs:
                inv = d.to_dict()
                inv["__id"] = d.id
                try:
                    exp = _normalize_dt(inv.get("expires_at"))
                except Exception:
                    exp = None
                if exp is None or now <= exp:
                    invited_list.append(inv)

            if not invited_list:
                return {"success": False, "error": "Invitation has expired"}

            # Prefer most recent by created_at
            def created_at_dt(inv):
                try:
                    return _normalize_dt(inv.get("created_at")) or now
                except Exception:
                    return now

            invited_list.sort(key=created_at_dt, reverse=True)

            # Match password against any valid pending invite for this email
            matched = None
            for inv in invited_list:
                stored_pw = str(inv.get("password", "")).strip()
                if stored_pw and stored_pw == pw_input:
                    matched = inv
                    break

            if not matched:
                return {"success": False, "error": "Invalid password"}

            session_id = str(uuid.uuid4())
            session = {
                "id": session_id,
                "email": email_raw,
                "workspace_id": matched["workspace_id"],
                "workspace_name": matched["workspace_name"],
                "role": matched["role"],
                "inviter_id": matched.get("inviter_id"),
                "created_at": now,
                "expires_at": now + timedelta(hours=SESSION_TTL_HOURS),
            }
            self.db.collection("invited_member_sessions").document(session_id).set(session)
            return {
                "success": True,
                "session_id": session_id,
                "workspace_id": matched["workspace_id"],
                "workspace_name": matched["workspace_name"],
                "role": matched["role"],
                "message": "Successfully authenticated as invited member",
            }
        except Exception as e:
            logger.error(f"authenticate_invited_member failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_invited_member_session(self, session_id: str) -> Dict:
        try:
            self._ensure_db()
            doc = self.db.collection("invited_member_sessions").document(session_id).get()
            if not doc.exists:
                return {"success": False, "error": "Session not found"}
            session = doc.to_dict()
            if _now() > _normalize_dt(session["expires_at"]):
                return {"success": False, "error": "Session has expired"}
            return {"success": True, "session": session}
        except Exception as e:
            logger.error(f"get_invited_member_session failed: {e}")
            return {"success": False, "error": str(e)}

    # --------------- Permissions ---------------
    async def check_user_permission(self, workspace_id: str, user_id: str, required_permission: str) -> bool:
        try:
            self._ensure_db()
            doc = self.db.collection("workspaces").document(workspace_id).get()
            if not doc.exists:
                return False
            w = doc.to_dict()
            member = w.get("members", {}).get(user_id, {})
            if member.get("status", "active") == "banned":
                return False
            role = member.get("role")
            if not role:
                return False
            perm_map = {
                "view": {"view"},
                "generate": {"view", "generate"},
                "admin": {"view", "generate", "admin"},
                "owner": {"view", "generate", "admin", "owner"},
            }
            return required_permission in perm_map.get(role, set())
        except Exception as e:
            logger.error(f"check_user_permission failed: {e}")
            return False

    # --------------- Helpers ---------------
    def _ensure_db(self):
        if not self.db:
            raise Exception("Database not initialized")

    def _generate_invited_member_password(self) -> str:
        return "".join(random.choices(string.digits, k=6))

    async def _send_invitation_email(self, email: str, workspace_name: str, inviter_name: str, role: str, invitation_token: str, invited_member_password: str) -> bool:
        try:
            subject = f"You've been invited to collaborate on {workspace_name}"
            invitation_link = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/accept-invitation?token={invitation_token}"
            html = f"""
            <div style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;'>
              <h2>Collaboration Invitation</h2>
              <p><strong>{inviter_name}</strong> invited you to the workspace <strong>{workspace_name}</strong>.</p>
              <p>Your access level: <strong>{role}</strong></p>
              <div style='background:#f8f9fa; border:1px solid #dee2e6; border-radius:8px; padding:16px; margin:16px 0;'>
                <p>Temporary invited member credentials:</p>
                <p><strong>Email:</strong> {email}<br/>
                   <strong>Password:</strong> <span style='font-family: monospace;'>{invited_member_password}</span></p>
              </div>
              <p><a href='{invitation_link}' style='background:#4F46E5; color:#fff; padding:10px 16px; border-radius:6px; text-decoration:none;'>Accept Invitation</a></p>
              <p style='color:#666; font-size:12px;'>If the button doesn't work, copy this link into your browser:<br/>{invitation_link}</p>
            </div>
            """
            await resend_service.send_email(to_email=email, subject=subject, html_content=html)
            return True
        except Exception as e:
            logger.warning(f"send_invitation_email failed: {e}")
            return False


# Global instance
collaboration_service = CollaborationService()
