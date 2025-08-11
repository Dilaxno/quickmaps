"""
Cloud Storage Service for Dropbox integration
"""
import os
import tempfile
import logging
import json
import time
from typing import Optional, Dict, Any
import requests
from pathlib import Path

# Google Drive functionality removed

# Dropbox imports
import dropbox
from dropbox.oauth import DropboxOAuth2Flow

logger = logging.getLogger(__name__)

class CloudStorageService:
    def __init__(self):
        # Dropbox configuration
        self.dropbox_app_key = os.getenv('DROPBOX_APP_KEY')
        self.dropbox_app_secret = os.getenv('DROPBOX_APP_SECRET')
        self.dropbox_redirect_uri = os.getenv('DROPBOX_REDIRECT_URI', 'http://localhost:5173/auth/dropbox/callback')
        
        # Token storage directory
        self.token_storage_dir = os.path.join(tempfile.gettempdir(), 'cloud_tokens')
        os.makedirs(self.token_storage_dir, exist_ok=True)
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate that required configuration is available"""
        missing_config = []
        
        if not self.dropbox_app_key:
            missing_config.append('DROPBOX_APP_KEY')
        if not self.dropbox_app_secret:
            missing_config.append('DROPBOX_APP_SECRET')
            
        if missing_config:
            logger.warning(f"Missing cloud storage configuration: {', '.join(missing_config)}")
            logger.warning("Cloud storage features will be limited")
        else:
            logger.info("✅ Cloud storage service initialized successfully")
            logger.info(f"Dropbox redirect URI: {self.dropbox_redirect_uri}")
    
    def is_dropbox_configured(self) -> bool:
        """Check if Dropbox is properly configured"""
        return bool(self.dropbox_app_key and self.dropbox_app_secret)
    
    def _store_tokens(self, service: str, user_id: str, tokens: Dict[str, Any]):
        """Store tokens securely for a user"""
        try:
            token_file = os.path.join(self.token_storage_dir, f"{service}_{user_id}.json")
            with open(token_file, 'w') as f:
                json.dump(tokens, f)
            logger.info(f"Stored {service} tokens for user {user_id}")
        except Exception as e:
            logger.error(f"Error storing {service} tokens: {e}")
    
    def _load_tokens(self, service: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Load stored tokens for a user"""
        try:
            token_file = os.path.join(self.token_storage_dir, f"{service}_{user_id}.json")
            if os.path.exists(token_file):
                with open(token_file, 'r') as f:
                    tokens = json.load(f)
                logger.info(f"Loaded {service} tokens for user {user_id}")
                return tokens
        except Exception as e:
            logger.error(f"Error loading {service} tokens: {e}")
        return None
    

    
    def _refresh_dropbox_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh Dropbox access token"""
        try:
            # Dropbox doesn't use refresh tokens in the same way
            # Access tokens are long-lived, but if we need to refresh:
            logger.warning("Dropbox tokens are long-lived and don't typically need refresh")
            return None
        except Exception as e:
            logger.error(f"Error refreshing Dropbox token: {e}")
            return None
        

    
    def get_dropbox_auth_url(self, state: str = None) -> str:
        """Generate Dropbox OAuth authorization URL using PKCE"""
        try:
            # Use the newer PKCE flow for Dropbox OAuth
            import secrets
            import base64
            import hashlib
            
            # Generate code verifier and challenge for PKCE
            code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
            code_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode('utf-8')).digest()
            ).decode('utf-8').rstrip('=')
            
            # Store code verifier for later use (in a real app, store this securely)
            # For now, we'll use a simple approach
            import tempfile
            import json
            
            verifier_file = tempfile.gettempdir() + f"/dropbox_verifier_{state or 'default'}.json"
            with open(verifier_file, 'w') as f:
                json.dump({'code_verifier': code_verifier}, f)
            
            # Build authorization URL manually
            auth_url = (
                f"https://www.dropbox.com/oauth2/authorize?"
                f"client_id={self.dropbox_app_key}&"
                f"response_type=code&"
                f"redirect_uri={self.dropbox_redirect_uri}&"
                f"code_challenge={code_challenge}&"
                f"code_challenge_method=S256"
            )
            
            if state:
                auth_url += f"&state={state}"
            
            return auth_url
        except Exception as e:
            logger.error(f"Error generating Dropbox auth URL: {e}")
            raise
    

    
    def exchange_dropbox_code(self, code: str, state: str = None, user_id: str = "default") -> Dict[str, Any]:
        """Exchange Dropbox authorization code for access token using PKCE and store tokens"""
        try:
            import tempfile
            import json
            import requests
            
            # Retrieve code verifier
            verifier_file = tempfile.gettempdir() + f"/dropbox_verifier_{state or 'default'}.json"
            try:
                with open(verifier_file, 'r') as f:
                    verifier_data = json.load(f)
                    code_verifier = verifier_data['code_verifier']
                
                # Clean up the temporary file
                os.remove(verifier_file)
            except FileNotFoundError:
                raise Exception("Code verifier not found. Please restart the authorization process.")
            
            # Exchange code for token
            token_url = "https://api.dropboxapi.com/oauth2/token"
            data = {
                'code': code,
                'grant_type': 'authorization_code',
                'client_id': self.dropbox_app_key,
                'redirect_uri': self.dropbox_redirect_uri,
                'code_verifier': code_verifier
            }
            
            response = requests.post(token_url, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            
            # Store tokens for future use
            stored_data = {
                'access_token': token_data['access_token'],
                'token_type': token_data.get('token_type', 'bearer'),
                'account_id': token_data.get('account_id'),
                'uid': token_data.get('uid'),
                'refresh_token': token_data.get('refresh_token'),  # Dropbox may provide this
                'app_key': self.dropbox_app_key,
                'app_secret': self.dropbox_app_secret
            }
            self._store_tokens('dropbox', user_id, stored_data)
            
            return {
                'access_token': token_data['access_token'],
                'token_type': token_data.get('token_type', 'bearer'),
                'account_id': token_data.get('account_id'),
                'uid': token_data.get('uid')
            }
        except Exception as e:
            logger.error(f"Error exchanging Dropbox code: {e}")
            raise
    

    
    def download_dropbox_file(self, file_path: str, access_token: str) -> str:
        """Download file from Dropbox and return local path"""
        try:
            # Create Dropbox client
            dbx = dropbox.Dropbox(access_token)
            
            # Get file metadata
            metadata = dbx.files_get_metadata(file_path)
            file_name = Path(file_path).name
            
            # Create temporary file
            temp_dir = tempfile.mkdtemp()
            temp_file_path = os.path.join(temp_dir, file_name)
            
            # Download file
            with open(temp_file_path, 'wb') as f:
                metadata, response = dbx.files_download(file_path)
                f.write(response.content)
            
            logger.info(f"Downloaded Dropbox file: {file_name} to {temp_file_path}")
            return temp_file_path
            
        except Exception as e:
            logger.error(f"Error downloading Dropbox file: {e}")
            raise
    

    
    def list_dropbox_files(self, access_token: str, folder_path: str = "", user_id: str = "default") -> list:
        """List files from Dropbox with better error handling"""
        try:
            dbx = dropbox.Dropbox(access_token)
            
            # List files in folder
            result = dbx.files_list_folder(folder_path)
            files = []
            
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    # Check if it's a video file
                    if any(entry.name.lower().endswith(ext) for ext in ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']):
                        files.append({
                            'id': entry.path_lower,
                            'name': entry.name,
                            'size': entry.size,
                            'modified_time': entry.client_modified.isoformat() if entry.client_modified else None
                        })
            
            return files
            
        except dropbox.exceptions.AuthError as e:
            logger.error(f"Dropbox authentication error: {e}")
            if "expired_access_token" in str(e):
                raise Exception("Dropbox access token has expired. Please re-authenticate.")
            else:
                raise Exception(f"Dropbox authentication failed: {str(e)}")
        except dropbox.exceptions.BadInputError as e:
            if "files.metadata.read" in str(e):
                logger.error("Dropbox app permissions insufficient. Need 'files.metadata.read' scope.")
                raise Exception("Dropbox app needs additional permissions. Please contact the app administrator to enable 'files.metadata.read' scope in the Dropbox App Console.")
            else:
                logger.error(f"Dropbox API error: {e}")
                raise Exception(f"Dropbox API error: {str(e)}")
        except Exception as e:
            logger.error(f"Error listing Dropbox files: {e}")
            raise Exception(f"Failed to list Dropbox files: {str(e)}")

# Global instance
cloud_storage_service = CloudStorageService()