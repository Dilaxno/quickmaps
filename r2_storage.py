"""
Cloudflare R2 Storage Service
Handles uploading, downloading, and managing notes in Cloudflare R2
"""

import boto3
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import hashlib
import uuid
from botocore.exceptions import ClientError, NoCredentialsError

from config import (
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, 
    R2_BUCKET_NAME, R2_ENDPOINT_URL, R2_PUBLIC_URL, ENABLE_R2_STORAGE
)

logger = logging.getLogger(__name__)

class R2StorageService:
    """Service for managing notes storage in Cloudflare R2"""
    
    def __init__(self):
        self.enabled = ENABLE_R2_STORAGE and all([
            R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
        ])
        
        if self.enabled:
            try:
                self.client = boto3.client(
                    's3',
                    endpoint_url=R2_ENDPOINT_URL,
                    aws_access_key_id=R2_ACCESS_KEY_ID,
                    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
                    region_name='auto'  # R2 uses 'auto' as region
                )
                
                # Test connection
                self._test_connection()
                logger.info("✅ R2 Storage service initialized successfully")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize R2 Storage: {e}")
                self.enabled = False
                self.client = None
        else:
            logger.warning("⚠️ R2 Storage disabled - missing configuration")
            self.client = None
    
    def is_available(self) -> bool:
        """Check if R2 storage is available"""
        return self.enabled and self.client is not None
    
    def _test_connection(self):
        """Test R2 connection by listing buckets"""
        try:
            self.client.head_bucket(Bucket=R2_BUCKET_NAME)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.warning(f"Bucket {R2_BUCKET_NAME} not found, attempting to create...")
                self._create_bucket()
            else:
                raise e
    
    def _create_bucket(self):
        """Create R2 bucket if it doesn't exist"""
        try:
            self.client.create_bucket(Bucket=R2_BUCKET_NAME)
            logger.info(f"✅ Created R2 bucket: {R2_BUCKET_NAME}")
        except ClientError as e:
            logger.error(f"❌ Failed to create bucket {R2_BUCKET_NAME}: {e}")
            raise e
    
    def _generate_note_key(self, job_id: str, note_type: str = "notes", user_id: str = None) -> str:
        """Generate a unique key for storing notes"""
        timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        if user_id:
            return f"users/{user_id}/notes/{timestamp}/{job_id}_{note_type}.json"
        else:
            return f"notes/{timestamp}/{job_id}_{note_type}.json"
    
    def save_notes(self, job_id: str, notes_content: str, metadata: Optional[Dict] = None, user_id: str = None) -> Optional[str]:
        """
        Save notes to R2 storage
        
        Args:
            job_id: Unique job identifier
            notes_content: The notes content to save
            metadata: Additional metadata about the notes
            user_id: Optional user ID for user-specific storage
            
        Returns:
            The R2 key if successful, None otherwise
        """
        if not self.is_available():
            logger.warning("R2 storage not available")
            return None
        
        try:
            # Prepare note data
            note_data = {
                "job_id": job_id,
                "content": notes_content,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": hashlib.sha256(notes_content.encode()).hexdigest(),
                "metadata": metadata or {}
            }
            
            # Generate sequential title instead of extracting from content
            title = self._generate_sequential_title(user_id)
            note_data["title"] = title
            
            # Generate key
            key = self._generate_note_key(job_id, user_id=user_id)
            
            # Upload to R2
            self.client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=key,
                Body=json.dumps(note_data, indent=2, ensure_ascii=False),
                ContentType='application/json',
                Metadata={
                    'job-id': str(job_id),
                    'title': str(title)[:100],  # Limit metadata size
                    'created-at': str(note_data["created_at"])
                }
            )
            
            logger.info(f"✅ Notes saved to R2: {key}")
            return key
            
        except Exception as e:
            logger.error(f"❌ Failed to save notes to R2: {e}")
            return None
    
    def get_notes(self, job_id: str, user_id: str = None) -> Optional[Dict]:
        """
        Retrieve notes from R2 storage
        
        Args:
            job_id: Unique job identifier
            user_id: Optional user ID for user-specific notes
            
        Returns:
            Note data if found, None otherwise
        """
        if not self.is_available():
            logger.warning("R2 storage not available for get_notes")
            return None
        
        try:
            logger.info(f"Getting notes for job_id: {job_id}, user_id: {user_id}")
            # Try to find the note by job_id
            key = self._find_note_key(job_id, user_id)
            if not key:
                logger.warning(f"No key found for job_id: {job_id}")
                return None
            
            # Get object from R2
            response = self.client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
            content = response['Body'].read().decode('utf-8')
            
            note_data = json.loads(content)
            logger.info(f"✅ Retrieved notes from R2: {key}")
            return note_data
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info(f"Notes not found in R2 for job: {job_id}")
            else:
                logger.error(f"❌ Failed to retrieve notes from R2: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to retrieve notes from R2: {e}")
            return None
    

    
    def delete_notes(self, job_id: str, user_id: str = None) -> bool:
        """
        Delete notes from R2 storage
        
        Args:
            job_id: Unique job identifier
            user_id: Optional user ID for user-specific notes
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            key = self._find_note_key(job_id, user_id)
            if not key:
                logger.warning(f"Notes not found for deletion: {job_id}")
                return False
            
            self.client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
            logger.info(f"✅ Deleted notes from R2: {key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to delete notes from R2: {e}")
            return False
    
    def get_public_url(self, key: str) -> Optional[str]:
        """
        Get public URL for a stored note (disabled for privacy)
        
        Args:
            key: R2 object key
            
        Returns:
            None (public URLs disabled for privacy)
        """
        # Public URLs disabled for privacy
        return None
    
    def _find_note_key(self, job_id: str, user_id: str = None) -> Optional[str]:
        """Find the R2 key for a given job_id"""
        try:
            logger.info(f"Searching for note key with job_id: {job_id}, user_id: {user_id}")
            # Determine search prefixes based on user_id
            if user_id:
                # Search user-specific notes first, then general notes
                prefixes = [f"users/{user_id}/notes/", "notes/"]
            else:
                # Search general notes
                prefixes = ["notes/"]
            
            logger.info(f"Search prefixes: {prefixes}")
            
            for prefix in prefixes:
                logger.info(f"Searching in prefix: {prefix}")
                # Use recursive search to find files in subdirectories (timestamp folders)
                paginator = self.client.get_paginator('list_objects_v2')
                page_iterator = paginator.paginate(
                    Bucket=R2_BUCKET_NAME,
                    Prefix=prefix
                )
                
                for page in page_iterator:
                    if 'Contents' in page:
                        logger.info(f"Found {len(page['Contents'])} objects in prefix {prefix}")
                        for obj in page['Contents']:
                            key = obj['Key']
                            # Extract filename from key
                            filename = key.split('/')[-1]
                            logger.info(f"Checking key: {key}, filename: {filename}")
                            # Check if job_id matches exactly (before the underscore)
                            if filename.startswith(f"{job_id}_") or filename == f"{job_id}.json":
                                logger.info(f"Found matching key: {key}")
                                return key
                    else:
                        logger.info(f"No contents found in page for prefix: {prefix}")
            
            logger.warning(f"No matching key found for job_id: {job_id}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to find note key for {job_id}: {e}")
            return None
    
    def _extract_title(self, content: str) -> str:
        """Extract title from notes content"""
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
            elif line.startswith('## ') and not line.startswith('### '):
                return line[3:].strip()
        
        # Fallback: use first non-empty line
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                return line[:50] + ('...' if len(line) > 50 else '')
        
        return "Untitled Notes"
    
    def _generate_sequential_title(self, user_id: str = None) -> str:
        """Generate sequential title like 'Quickmaps notes 01', 'Quickmaps notes 02', etc."""
        try:
            # Generate a simple timestamp-based title since we removed list_saved_notes
            timestamp = datetime.now(timezone.utc).strftime("%m%d")
            return f"Quickmaps notes {timestamp}"
            
        except Exception as e:
            logger.warning(f"Failed to generate sequential title: {e}")
            return "Quickmaps notes 01"
    
    def update_note_title(self, job_id: str, new_title: str, user_id: str = None) -> bool:
        """
        Update the title of an existing note
        
        Args:
            job_id: Unique job identifier
            new_title: New title for the note
            user_id: Optional user ID for user-specific notes
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            logger.warning("R2 storage not available for title update")
            return False
        
        try:
            # Get existing note data
            existing_note = self.get_notes(job_id, user_id)
            if not existing_note:
                logger.warning(f"Note not found for title update: {job_id}")
                return False
            
            # Update the title and updated_at timestamp
            existing_note["title"] = new_title
            existing_note["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            # Find the existing key
            key = self._find_note_key(job_id, user_id)
            if not key:
                logger.warning(f"Key not found for note: {job_id}")
                return False
            
            # Update the object in R2
            self.client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=key,
                Body=json.dumps(existing_note, indent=2, ensure_ascii=False),
                ContentType='application/json',
                Metadata={
                    'job-id': str(job_id),
                    'title': str(new_title)[:100],  # Limit metadata size
                    'created-at': str(existing_note.get("created_at", "")),
                    'updated-at': str(existing_note["updated_at"])
                }
            )
            
            logger.info(f"✅ Updated note title in R2: {job_id} -> {new_title}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update note title in R2: {e}")
            return False
    

    
    def update_notes(self, job_id: str, notes_content: str, metadata: Optional[Dict] = None) -> Optional[str]:
        """
        Update existing notes in R2 storage
        
        Args:
            job_id: Unique job identifier
            notes_content: Updated notes content
            metadata: Additional metadata
            
        Returns:
            The R2 key if successful, None otherwise
        """
        if not self.is_available():
            return None
        
        try:
            # Get existing note data
            existing_data = self.get_notes(job_id)
            if not existing_data:
                # If doesn't exist, create new
                return self.save_notes(job_id, notes_content, metadata)
            
            # Update the data
            existing_data.update({
                "content": notes_content,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": hashlib.sha256(notes_content.encode()).hexdigest(),
                "title": self._extract_title(notes_content)
            })
            
            if metadata:
                existing_data["metadata"].update(metadata)
            
            # Find and update the existing key
            key = self._find_note_key(job_id)
            if key:
                self.client.put_object(
                    Bucket=R2_BUCKET_NAME,
                    Key=key,
                    Body=json.dumps(existing_data, indent=2, ensure_ascii=False),
                    ContentType='application/json',
                    Metadata={
                        'job-id': job_id,
                        'title': existing_data["title"][:100],
                        'created-at': existing_data["created_at"],
                        'updated-at': existing_data["updated_at"]
                    }
                )
                
                logger.info(f"✅ Notes updated in R2: {key}")
                return key
            
        except Exception as e:
            logger.error(f"❌ Failed to update notes in R2: {e}")
            return None
    
    def save_bookmark(self, user_id: str, job_id: str, section_id: str, title: str, content: str, metadata: Optional[Dict] = None) -> Optional[str]:
        """
        Save a bookmarked note section to R2 storage
        
        Args:
            user_id: User ID
            job_id: Original job ID where the bookmark was created
            section_id: Section ID within the notes
            title: Title of the bookmarked section
            content: Content of the bookmarked section
            metadata: Additional metadata
            
        Returns:
            The R2 key if successful, None otherwise
        """
        if not self.is_available():
            logger.warning("R2 storage not available for bookmark")
            return None
        
        try:
            bookmark_id = str(uuid.uuid4())
            bookmark_data = {
                "bookmark_id": bookmark_id,
                "user_id": user_id,
                "job_id": job_id,
                "section_id": section_id,
                "title": title,
                "content": content,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {}
            }
            
            # Generate key for bookmark
            timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d")
            key = f"users/{user_id}/bookmarks/{timestamp}/{bookmark_id}.json"
            
            # Upload to R2
            self.client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=key,
                Body=json.dumps(bookmark_data, indent=2, ensure_ascii=False),
                ContentType='application/json',
                Metadata={
                    'user-id': str(user_id),
                    'job-id': str(job_id),
                    'section-id': str(section_id),
                    'title': str(title)[:100],  # Limit metadata size
                    'bookmark-id': str(bookmark_id),
                    'created-at': str(bookmark_data["created_at"])
                }
            )
            
            logger.info(f"✅ Bookmark saved to R2: {key}")
            return key
            
        except Exception as e:
            logger.error(f"❌ Failed to save bookmark to R2: {e}")
            return None
    
    def get_user_bookmarks(self, user_id: str, limit: int = 100) -> List[Dict]:
        """
        Get all bookmarks for a user
        
        Args:
            user_id: User ID
            limit: Maximum number of bookmarks to return
            
        Returns:
            List of bookmark data
        """
        if not self.is_available():
            return []
        
        try:
            search_prefix = f"users/{user_id}/bookmarks/"
            logger.info(f"Listing bookmarks with prefix: {search_prefix}")
            
            paginator = self.client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=R2_BUCKET_NAME,
                Prefix=search_prefix
            )
            
            bookmarks = []
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        try:
                            if len(bookmarks) >= limit:
                                break
                            
                            # Skip directories
                            if obj['Key'].endswith('/'):
                                continue
                            
                            # Get bookmark data
                            response = self.client.get_object(Bucket=R2_BUCKET_NAME, Key=obj['Key'])
                            content = response['Body'].read().decode('utf-8')
                            bookmark_data = json.loads(content)
                            
                            # Add file metadata
                            bookmark_data['file_size'] = obj['Size']
                            bookmark_data['last_modified'] = obj['LastModified'].isoformat()
                            bookmark_data['r2_key'] = obj['Key']
                            
                            bookmarks.append(bookmark_data)
                            
                        except Exception as e:
                            logger.warning(f"Failed to process bookmark {obj['Key']}: {e}")
                            continue
                
                if len(bookmarks) >= limit:
                    break
            
            # Sort by creation date (newest first)
            bookmarks.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            logger.info(f"✅ Retrieved {len(bookmarks)} bookmarks for user {user_id}")
            return bookmarks
            
        except Exception as e:
            logger.error(f"❌ Failed to get user bookmarks: {e}")
            return []
    
    def delete_bookmark(self, user_id: str, bookmark_id: str) -> bool:
        """
        Delete a specific bookmark
        
        Args:
            user_id: User ID
            bookmark_id: Bookmark ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available():
            logger.debug(f"R2 storage not available for bookmark deletion: {bookmark_id}")
            return False
        
        try:
            # Find the bookmark by searching with prefix
            search_prefix = f"users/{user_id}/bookmarks/"
            found_bookmark = False
            files_checked = 0
            
            logger.debug(f"🔍 Searching for bookmark {bookmark_id} with prefix: {search_prefix}")
            
            paginator = self.client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=R2_BUCKET_NAME,
                Prefix=search_prefix
            )
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        files_checked += 1
                        # Check if bookmark_id is in the key (filename contains the ID)
                        if bookmark_id in obj['Key'] and obj['Key'].endswith('.json'):
                            logger.debug(f"📄 Found potential bookmark file: {obj['Key']}")
                            # Verify it's the correct bookmark by checking content
                            try:
                                response = self.client.get_object(Bucket=R2_BUCKET_NAME, Key=obj['Key'])
                                content = response['Body'].read().decode('utf-8')
                                bookmark_data = json.loads(content)
                                
                                if bookmark_data.get('bookmark_id') == bookmark_id:
                                    # Delete the bookmark
                                    self.client.delete_object(Bucket=R2_BUCKET_NAME, Key=obj['Key'])
                                    logger.info(f"✅ Deleted bookmark: {obj['Key']}")
                                    found_bookmark = True
                                    return True
                                else:
                                    logger.debug(f"📄 File contains different bookmark_id: {bookmark_data.get('bookmark_id')}")
                                    
                            except ClientError as e:
                                error_code = e.response['Error']['Code']
                                if error_code == 'NoSuchKey':
                                    logger.debug(f"Bookmark file already deleted: {obj['Key']}")
                                    continue
                                else:
                                    logger.warning(f"Failed to access bookmark {obj['Key']}: {e}")
                                    continue
                            except json.JSONDecodeError as e:
                                logger.warning(f"Invalid JSON in bookmark {obj['Key']}: {e}")
                                continue
                            except Exception as e:
                                logger.warning(f"Failed to verify bookmark {obj['Key']}: {e}")
                                continue
            
            if not found_bookmark:
                logger.info(f"📝 Bookmark not found for deletion: {bookmark_id} (checked {files_checked} files)")
            
            return found_bookmark
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                logger.error(f"❌ R2 bucket not found: {R2_BUCKET_NAME}")
            else:
                logger.error(f"❌ R2 client error during bookmark deletion: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to delete bookmark: {e}")
            return False

    def bookmark_exists(self, user_id: str, bookmark_id: str) -> bool:
        """
        Check if a bookmark exists
        
        Args:
            user_id: User ID
            bookmark_id: Bookmark ID to check
            
        Returns:
            True if bookmark exists, False otherwise
        """
        if not self.is_available():
            return False
        
        try:
            # Find the bookmark by searching with prefix
            search_prefix = f"users/{user_id}/bookmarks/"
            
            paginator = self.client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=R2_BUCKET_NAME,
                Prefix=search_prefix
            )
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        if bookmark_id in obj['Key'] and obj['Key'].endswith('.json'):
                            try:
                                response = self.client.get_object(Bucket=R2_BUCKET_NAME, Key=obj['Key'])
                                content = response['Body'].read().decode('utf-8')
                                bookmark_data = json.loads(content)
                                
                                if bookmark_data.get('bookmark_id') == bookmark_id:
                                    return True
                                    
                            except Exception:
                                # If we can't read the bookmark, consider it as not existing
                                continue
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking bookmark existence: {e}")
            return False

    def save_notes_to_r2(self, user_id: str, notes_data: Dict, title: str = "Untitled Notes") -> Optional[str]:
        """Save complete notes document to R2 storage"""
        if not self.enabled:
            logger.warning("R2 Storage is disabled")
            return None
        
        try:
            # Generate unique note ID
            note_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            
            # Create note metadata
            note_metadata = {
                "note_id": note_id,
                "user_id": user_id,
                "title": title,
                "created_at": timestamp,
                "updated_at": timestamp,
                "notes_data": notes_data
            }
            
            # Generate key for saved note
            key = f"users/{user_id}/saved_notes/{note_id}.json"
            
            # Upload to R2
            self.client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=key,
                Body=json.dumps(note_metadata, indent=2),
                ContentType='application/json',
                Metadata={
                    'user_id': user_id,
                    'note_id': note_id,
                    'title': title,
                    'created_at': timestamp
                }
            )
            
            logger.info(f"✅ Saved notes to R2: {key}")
            return note_id
            
        except Exception as e:
            logger.error(f"❌ Failed to save notes to R2: {e}")
            return None

    def get_user_saved_notes(self, user_id: str, limit: int = 100) -> List[Dict]:
        """Get all saved notes for a user"""
        if not self.enabled:
            logger.warning("R2 Storage is disabled")
            return []
        
        try:
            notes = []
            search_prefix = f"users/{user_id}/saved_notes/"
            
            paginator = self.client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=R2_BUCKET_NAME,
                Prefix=search_prefix,
                MaxKeys=limit
            )
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        try:
                            # Get the note content
                            response = self.client.get_object(Bucket=R2_BUCKET_NAME, Key=obj['Key'])
                            content = response['Body'].read().decode('utf-8')
                            note_data = json.loads(content)
                            
                            # Add file metadata
                            note_data['file_size'] = obj['Size']
                            note_data['last_modified'] = obj['LastModified'].isoformat()
                            
                            notes.append(note_data)
                            
                        except Exception as e:
                            logger.warning(f"Failed to load saved note {obj['Key']}: {e}")
                            continue
            
            # Sort by creation date (newest first)
            notes.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            logger.info(f"✅ Retrieved {len(notes)} saved notes for user: {user_id}")
            return notes
            
        except Exception as e:
            logger.error(f"❌ Failed to get saved notes: {e}")
            return []

    def get_saved_note(self, user_id: str, note_id: str) -> Optional[Dict]:
        """Get a specific saved note"""
        if not self.enabled:
            logger.warning("R2 Storage is disabled")
            return None
        
        try:
            key = f"users/{user_id}/saved_notes/{note_id}.json"
            
            response = self.client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
            content = response['Body'].read().decode('utf-8')
            note_data = json.loads(content)
            
            logger.info(f"✅ Retrieved saved note: {key}")
            return note_data
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning(f"Saved note not found: {key}")
                return None
            else:
                logger.error(f"❌ Failed to get saved note: {e}")
                return None
        except Exception as e:
            logger.error(f"❌ Failed to get saved note: {e}")
            return None

    def update_saved_note(self, user_id: str, note_id: str, title: Optional[str] = None, notes_data: Optional[Dict] = None) -> bool:
        """Update a saved note"""
        if not self.enabled:
            logger.warning("R2 Storage is disabled")
            return False
        
        try:
            # First, get the existing note
            existing_note = self.get_saved_note(user_id, note_id)
            if not existing_note:
                logger.warning(f"Saved note not found for update: {note_id}")
                return False
            
            # Update the fields
            if title is not None:
                existing_note['title'] = title
            if notes_data is not None:
                existing_note['notes_data'] = notes_data
            
            # Update timestamp
            existing_note['updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Save back to R2
            key = f"users/{user_id}/saved_notes/{note_id}.json"
            
            self.client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=key,
                Body=json.dumps(existing_note, indent=2),
                ContentType='application/json',
                Metadata={
                    'user_id': user_id,
                    'note_id': note_id,
                    'title': existing_note['title'],
                    'updated_at': existing_note['updated_at']
                }
            )
            
            logger.info(f"✅ Updated saved note: {key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update saved note: {e}")
            return False

    def delete_saved_note(self, user_id: str, note_id: str) -> bool:
        """Delete a saved note"""
        if not self.enabled:
            logger.warning("R2 Storage is disabled")
            return False
        
        try:
            key = f"users/{user_id}/saved_notes/{note_id}.json"
            
            # Check if note exists first
            try:
                self.client.head_object(Bucket=R2_BUCKET_NAME, Key=key)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.warning(f"Saved note not found for deletion: {key}")
                    return False
                else:
                    raise
            
            # Delete the note
            self.client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
            logger.info(f"✅ Deleted saved note: {key}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to delete saved note: {e}")
            return False

# Global instance
r2_storage = R2StorageService()