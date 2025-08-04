import os
import json
import boto3
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, List
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet
import base64
import logging

logger = logging.getLogger(__name__)

class R2Storage:
    def __init__(self):
        self.account_id = os.getenv("R2_ACCOUNT_ID")
        self.access_key_id = os.getenv("R2_ACCESS_KEY_ID")
        self.secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY")
        self.bucket_name = os.getenv("R2_BUCKET_NAME", "quickmind-mindmaps")
        self.endpoint = os.getenv("R2_ENDPOINT")
        
        # Initialize encryption key (you should store this securely)
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key)
        
        # Initialize S3 client for R2
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name='auto'  # R2 uses 'auto' as region
        )
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for mind map data"""
        key_env = os.getenv("MINDMAP_ENCRYPTION_KEY")
        if key_env:
            return key_env.encode()
        
        # Generate a new key (in production, store this securely)
        key = Fernet.generate_key()
        logger.warning("Generated new encryption key. Store this securely: %s", key.decode())
        return key
    
    def _encrypt_data(self, data: str) -> str:
        """Encrypt mind map data"""
        try:
            encrypted = self.cipher.encrypt(data.encode())
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            logger.error("Encryption failed: %s", e)
            raise
    
    def _decrypt_data(self, encrypted_data: str) -> str:
        """Decrypt mind map data"""
        try:
            encrypted_bytes = base64.b64decode(encrypted_data.encode())
            decrypted = self.cipher.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error("Decryption failed: %s", e)
            raise
    
    def _generate_mindmap_key(self, user_id: str, mindmap_id: str) -> str:
        """Generate a secure key for storing mind map"""
        return f"users/{user_id}/mindmaps/{mindmap_id}.json"
    
    def _generate_mindmap_id(self, user_id: str, title: str) -> str:
        """Generate a unique mind map ID"""
        timestamp = datetime.now(timezone.utc).isoformat()
        content = f"{user_id}_{title}_{timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _generate_notes_key(self, user_id: str, note_id: str) -> str:
        """Generate a secure key for storing notes"""
        return f"users/{user_id}/notes/{note_id}.json"
    
    def _generate_note_id(self, user_id: str, title: str) -> str:
        """Generate a unique note ID"""
        timestamp = datetime.now(timezone.utc).isoformat()
        content = f"{user_id}_{title}_{timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    async def _generate_default_title(self, user_id: str) -> str:
        """Generate a default title like 'Quickmaps note 01', 'Quickmaps note 02', etc."""
        try:
            # Get all existing mindmaps for the user
            mindmaps = await self.list_user_mindmaps(user_id, limit=1000)
            
            # Find existing "Quickmaps note XX" titles
            existing_numbers = []
            for mindmap in mindmaps:
                title = mindmap.get('title', '')
                if title.startswith('Quickmaps note '):
                    try:
                        # Extract the number part
                        number_part = title.replace('Quickmaps note ', '')
                        number = int(number_part)
                        existing_numbers.append(number)
                    except ValueError:
                        # Skip if not a valid number
                        continue
            
            # Find the next available number
            next_number = 1
            while next_number in existing_numbers:
                next_number += 1
            
            # Format with leading zero for numbers less than 10
            return f"Quickmaps note {next_number:02d}"
            
        except Exception as e:
            logger.error("Error generating default title: %s", e)
            # Fallback to timestamp-based title
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"Quickmaps note {timestamp}"
    
    async def _generate_default_notes_title(self, user_id: str) -> str:
        """Generate a default title like 'Educational Notes 01', 'Educational Notes 02', etc."""
        try:
            # Get all existing notes for the user
            notes = await self.list_user_notes(user_id, limit=1000)
            
            # Find existing "Educational Notes XX" titles
            existing_numbers = []
            for note in notes:
                title = note.get('title', '')
                if title.startswith('Educational Notes '):
                    try:
                        # Extract the number part
                        number_part = title.replace('Educational Notes ', '')
                        number = int(number_part)
                        existing_numbers.append(number)
                    except ValueError:
                        # Skip if not a valid number
                        continue
            
            # Find the next available number
            next_number = 1
            while next_number in existing_numbers:
                next_number += 1
            
            # Format with leading zero for numbers less than 10
            return f"Educational Notes {next_number:02d}"
            
        except Exception as e:
            logger.error("Error generating default notes title: %s", e)
            # Fallback to timestamp-based title
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"Educational Notes {timestamp}"
    
    async def save_mindmap(
        self, 
        user_id: str, 
        mindmap_data: Dict, 
        title: str = None,
        encrypt: bool = True
    ) -> Dict:
        """
        Save a mind map to R2 storage
        
        Args:
            user_id: The user's unique ID
            mindmap_data: The mind map JSON data
            title: Optional title for the mind map
            encrypt: Whether to encrypt the data (default: True)
            
        Returns:
            Dict with mindmap_id, key, and metadata
        """
        try:
            # Generate default title if none provided
            if not title or title.strip() == "":
                title = await self._generate_default_title(user_id)
            
            # Generate unique ID and key
            mindmap_id = self._generate_mindmap_id(user_id, title)
            storage_key = self._generate_mindmap_key(user_id, mindmap_id)
            
            # Prepare metadata
            metadata = {
                "user_id": user_id,
                "mindmap_id": mindmap_id,
                "title": title,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "encrypted": encrypt
            }
            
            # Prepare the data to store
            storage_data = {
                "metadata": metadata,
                "mindmap": mindmap_data
            }
            
            # Serialize to JSON
            json_data = json.dumps(storage_data, ensure_ascii=False, indent=2)
            
            # Encrypt if requested
            if encrypt:
                json_data = self._encrypt_data(json_data)
            
            # Upload to R2
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=json_data,
                ContentType='application/json',
                Metadata={
                    'user-id': user_id,
                    'mindmap-id': mindmap_id,
                    'title': title or "Untitled",
                    'encrypted': str(encrypt).lower(),
                    'created-at': metadata["created_at"]
                }
            )
            
            logger.info("Mind map saved successfully: %s", mindmap_id)
            
            return {
                "mindmap_id": mindmap_id,
                "storage_key": storage_key,
                "metadata": metadata,
                "success": True
            }
            
        except ClientError as e:
            logger.error("R2 storage error: %s", e)
            raise Exception(f"Failed to save mind map: {e}")
        except Exception as e:
            logger.error("Unexpected error saving mind map: %s", e)
            raise
    
    async def get_mindmap(self, user_id: str, mindmap_id: str) -> Optional[Dict]:
        """
        Retrieve a mind map from R2 storage
        
        Args:
            user_id: The user's unique ID
            mindmap_id: The mind map ID
            
        Returns:
            Dict with mind map data or None if not found
        """
        try:
            storage_key = self._generate_mindmap_key(user_id, mindmap_id)
            
            # Get object from R2
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )
            
            # Read the data
            data = response['Body'].read().decode('utf-8')
            
            # Check if data is encrypted
            metadata = response.get('Metadata', {})
            is_encrypted = metadata.get('encrypted', 'false').lower() == 'true'
            
            # Decrypt if necessary
            if is_encrypted:
                data = self._decrypt_data(data)
            
            # Parse JSON
            mindmap_data = json.loads(data)
            
            # Verify user ownership
            if mindmap_data.get('metadata', {}).get('user_id') != user_id:
                logger.warning("Unauthorized access attempt: user %s tried to access mindmap %s", user_id, mindmap_id)
                return None
            
            return mindmap_data
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info("Mind map not found: %s", mindmap_id)
                return None
            logger.error("R2 storage error: %s", e)
            raise Exception(f"Failed to retrieve mind map: {e}")
        except Exception as e:
            logger.error("Unexpected error retrieving mind map: %s", e)
            raise
    
    async def list_user_mindmaps(self, user_id: str, limit: int = 50) -> List[Dict]:
        """
        List all mind maps for a user
        
        Args:
            user_id: The user's unique ID
            limit: Maximum number of mind maps to return
            
        Returns:
            List of mind map metadata
        """
        try:
            prefix = f"users/{user_id}/mindmaps/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=limit
            )
            
            mindmaps = []
            
            for obj in response.get('Contents', []):
                # Get object metadata
                head_response = self.s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=obj['Key']
                )
                
                metadata = head_response.get('Metadata', {})
                
                mindmap_info = {
                    "mindmap_id": metadata.get('mindmap-id'),
                    "title": metadata.get('title', 'Untitled'),
                    "created_at": metadata.get('created-at'),
                    "size": obj['Size'],
                    "last_modified": obj['LastModified'].isoformat(),
                    "storage_key": obj['Key']
                }
                
                mindmaps.append(mindmap_info)
            
            # Sort by creation date (newest first)
            mindmaps.sort(key=lambda x: x['created_at'], reverse=True)
            
            return mindmaps
            
        except ClientError as e:
            logger.error("R2 storage error: %s", e)
            raise Exception(f"Failed to list mind maps: {e}")
        except Exception as e:
            logger.error("Unexpected error listing mind maps: %s", e)
            raise
    
    async def update_mindmap(self, user_id: str, mindmap_id: str, title: str = None, mindmap_data: Dict = None) -> Optional[Dict]:
        """
        Update a mind map in R2 storage
        
        Args:
            user_id: The user's unique ID
            mindmap_id: The mind map ID
            title: New title for the mind map (optional)
            mindmap_data: New mind map data (optional)
            
        Returns:
            Updated metadata if successful, None if not found
        """
        try:
            # First, get the existing mind map to verify ownership and get current data
            existing_mindmap = await self.get_mindmap(user_id, mindmap_id)
            if not existing_mindmap:
                return None
            
            # Use existing data if not provided
            updated_title = title if title is not None else existing_mindmap["metadata"]["title"]
            updated_data = mindmap_data if mindmap_data is not None else existing_mindmap["mindmap"]
            
            # Create updated metadata
            updated_at = datetime.now(timezone.utc).isoformat()
            metadata = {
                "mindmap-id": mindmap_id,
                "title": updated_title,
                "created-at": existing_mindmap["metadata"]["created_at"],  # Keep original creation date
                "updated-at": updated_at,
                "user-id": user_id,
                "encrypted": "true"
            }
            
            # Prepare the data to store
            storage_data = {
                "metadata": {
                    "mindmap_id": mindmap_id,
                    "title": updated_title,
                    "created_at": existing_mindmap["metadata"]["created_at"],
                    "updated_at": updated_at,
                    "user_id": user_id
                },
                "mindmap": updated_data
            }
            
            # Encrypt and store
            encrypted_data = self._encrypt_data(json.dumps(storage_data))
            storage_key = self._generate_mindmap_key(user_id, mindmap_id)
            
            # Upload to R2
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=encrypted_data,
                Metadata=metadata,
                ContentType='application/json'
            )
            
            logger.info("Mind map updated successfully: %s", mindmap_id)
            return {
                "mindmap_id": mindmap_id,
                "title": updated_title,
                "updated_at": updated_at
            }
            
        except ClientError as e:
            logger.error("R2 storage error: %s", e)
            raise Exception(f"Failed to update mind map: {e}")
        except Exception as e:
            logger.error("Unexpected error updating mind map: %s", e)
            raise

    async def delete_mindmap(self, user_id: str, mindmap_id: str) -> bool:
        """
        Delete a mind map from R2 storage
        
        Args:
            user_id: The user's unique ID
            mindmap_id: The mind map ID
            
        Returns:
            True if deleted successfully, False if not found
        """
        try:
            storage_key = self._generate_mindmap_key(user_id, mindmap_id)
            
            # Verify ownership before deletion
            mindmap = await self.get_mindmap(user_id, mindmap_id)
            if not mindmap:
                return False
            
            # Delete from R2
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )
            
            logger.info("Mind map deleted successfully: %s", mindmap_id)
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return False
            logger.error("R2 storage error: %s", e)
            raise Exception(f"Failed to delete mind map: {e}")
        except Exception as e:
            logger.error("Unexpected error deleting mind map: %s", e)
            raise

    async def save_notes(
        self, 
        user_id: str, 
        notes_data: Dict, 
        title: str = None,
        encrypt: bool = True
    ) -> Dict:
        """
        Save educational notes to R2 storage
        
        Args:
            user_id: The user's unique ID
            notes_data: The educational notes JSON data
            title: Optional title for the notes
            encrypt: Whether to encrypt the data (default: True)
            
        Returns:
            Dict with note_id, key, and metadata
        """
        try:
            # Generate default title if none provided
            if not title or title.strip() == "":
                title = await self._generate_default_notes_title(user_id)
            
            # Generate unique ID and key
            note_id = self._generate_note_id(user_id, title)
            storage_key = self._generate_notes_key(user_id, note_id)
            
            # Prepare metadata
            metadata = {
                "user_id": user_id,
                "note_id": note_id,
                "title": title,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "encrypted": encrypt,
                "source_type": "educational_notes"
            }
            
            # Prepare the data to store
            storage_data = {
                "metadata": metadata,
                "notes_data": notes_data
            }
            
            # Serialize to JSON
            json_data = json.dumps(storage_data, ensure_ascii=False, indent=2)
            
            # Encrypt if requested
            if encrypt:
                json_data = self._encrypt_data(json_data)
            
            # Upload to R2
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=json_data,
                ContentType='application/json',
                Metadata={
                    'user-id': user_id,
                    'note-id': note_id,
                    'title': title or "Untitled Notes",
                    'encrypted': str(encrypt).lower(),
                    'created-at': metadata["created_at"],
                    'source-type': 'educational_notes'
                }
            )
            
            logger.info("Educational notes saved successfully: %s", note_id)
            
            return {
                "note_id": note_id,
                "storage_key": storage_key,
                "metadata": metadata,
                "success": True
            }
            
        except ClientError as e:
            logger.error("R2 storage error: %s", e)
            raise Exception(f"Failed to save notes: {e}")
        except Exception as e:
            logger.error("Unexpected error saving notes: %s", e)
            raise

    async def get_notes(self, user_id: str, note_id: str) -> Optional[Dict]:
        """
        Retrieve educational notes from R2 storage
        
        Args:
            user_id: The user's unique ID
            note_id: The note ID
            
        Returns:
            Dict with note data or None if not found
        """
        try:
            storage_key = self._generate_notes_key(user_id, note_id)
            
            # Get object from R2
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )
            
            # Read and decode the data
            data = response['Body'].read()
            
            # Check if data is encrypted (from metadata)
            metadata = response.get('Metadata', {})
            is_encrypted = metadata.get('encrypted', 'true').lower() == 'true'
            
            if is_encrypted:
                json_str = self._decrypt_data(data.decode('utf-8'))
            else:
                json_str = data.decode('utf-8')
            
            # Parse JSON
            storage_data = json.loads(json_str)
            
            # Verify ownership
            if storage_data.get('metadata', {}).get('user_id') != user_id:
                logger.warning("Access denied for note %s by user %s", note_id, user_id)
                return None
            
            return storage_data
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            logger.error("R2 storage error: %s", e)
            raise Exception(f"Failed to retrieve notes: {e}")
        except Exception as e:
            logger.error("Unexpected error retrieving notes: %s", e)
            raise

    async def list_user_notes(self, user_id: str, limit: int = 50) -> List[Dict]:
        """
        List all educational notes for a user
        
        Args:
            user_id: The user's unique ID
            limit: Maximum number of notes to return
            
        Returns:
            List of note metadata dictionaries
        """
        try:
            prefix = f"users/{user_id}/notes/"
            
            # List objects with the user's prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=limit
            )
            
            notes = []
            
            if 'Contents' in response:
                for obj in response['Contents']:
                    try:
                        # Get object metadata
                        head_response = self.s3_client.head_object(
                            Bucket=self.bucket_name,
                            Key=obj['Key']
                        )
                        
                        metadata = head_response.get('Metadata', {})
                        
                        # Extract note ID from key
                        note_id = obj['Key'].split('/')[-1].replace('.json', '')
                        
                        note_info = {
                            "note_id": note_id,
                            "title": metadata.get('title', 'Untitled Notes'),
                            "created_at": metadata.get('created-at', obj['LastModified'].isoformat()),
                            "updated_at": obj['LastModified'].isoformat(),
                            "size": obj['Size'],
                            "source_type": metadata.get('source-type', 'educational_notes'),
                            "preview": ""  # Will be filled by frontend if needed
                        }
                        
                        notes.append(note_info)
                        
                    except Exception as e:
                        logger.warning("Error processing note %s: %s", obj['Key'], e)
                        continue
            
            # Sort by creation date (newest first)
            notes.sort(key=lambda x: x['created_at'], reverse=True)
            
            return notes
            
        except ClientError as e:
            logger.error("R2 storage error: %s", e)
            raise Exception(f"Failed to list notes: {e}")
        except Exception as e:
            logger.error("Unexpected error listing notes: %s", e)
            raise

    async def update_notes(self, user_id: str, note_id: str, title: str = None, notes_data: Dict = None) -> Optional[Dict]:
        """
        Update educational notes in R2 storage
        
        Args:
            user_id: The user's unique ID
            note_id: The note ID
            title: New title (optional)
            notes_data: New notes data (optional)
            
        Returns:
            Dict with updated metadata or None if not found
        """
        try:
            # First, get the existing notes
            existing_notes = await self.get_notes(user_id, note_id)
            if not existing_notes:
                return None
            
            # Update the data
            updated_title = title if title is not None else existing_notes['metadata']['title']
            updated_notes_data = notes_data if notes_data is not None else existing_notes['notes_data']
            updated_at = datetime.now(timezone.utc).isoformat()
            
            # Update metadata
            metadata = existing_notes['metadata'].copy()
            metadata['title'] = updated_title
            metadata['updated_at'] = updated_at
            
            # Prepare updated storage data
            storage_data = {
                "metadata": metadata,
                "notes_data": updated_notes_data
            }
            
            # Serialize and encrypt
            json_data = json.dumps(storage_data, ensure_ascii=False, indent=2)
            encrypted_data = self._encrypt_data(json_data)
            
            # Update in R2
            storage_key = self._generate_notes_key(user_id, note_id)
            
            metadata = {
                'user-id': user_id,
                'note-id': note_id,
                'title': updated_title,
                'encrypted': 'true',
                'created-at': existing_notes['metadata']['created_at'],
                'updated-at': updated_at,
                'source-type': 'educational_notes'
            }
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=encrypted_data,
                Metadata=metadata,
                ContentType='application/json'
            )
            
            logger.info("Educational notes updated successfully: %s", note_id)
            return {
                "note_id": note_id,
                "title": updated_title,
                "updated_at": updated_at
            }
            
        except ClientError as e:
            logger.error("R2 storage error: %s", e)
            raise Exception(f"Failed to update notes: {e}")
        except Exception as e:
            logger.error("Unexpected error updating notes: %s", e)
            raise

    async def delete_notes(self, user_id: str, note_id: str) -> bool:
        """
        Delete educational notes from R2 storage
        
        Args:
            user_id: The user's unique ID
            note_id: The note ID
            
        Returns:
            True if deleted successfully, False if not found
        """
        try:
            storage_key = self._generate_notes_key(user_id, note_id)
            
            # Verify ownership before deletion
            notes = await self.get_notes(user_id, note_id)
            if not notes:
                return False
            
            # Delete from R2
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=storage_key
            )
            
            logger.info("Educational notes deleted successfully: %s", note_id)
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return False
            logger.error("R2 storage error: %s", e)
            raise Exception(f"Failed to delete notes: {e}")
        except Exception as e:
            logger.error("Unexpected error deleting notes: %s", e)
            raise

# Global instance
_r2_storage = None

def get_r2_storage() -> R2Storage:
    """Get the global R2 storage instance"""
    global _r2_storage
    if _r2_storage is None:
        _r2_storage = R2Storage()
    return _r2_storage