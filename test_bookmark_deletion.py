#!/usr/bin/env python3
"""
Test script for bookmark deletion functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from r2_storage import R2StorageService
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_bookmark_operations():
    """Test bookmark creation, existence check, and deletion"""
    
    # Initialize R2 storage
    r2_storage = R2StorageService()
    
    if not r2_storage.is_available():
        logger.error("❌ R2 storage not available for testing")
        return False
    
    # Test data
    test_user_id = "test-user-123"
    test_job_id = "test-job-456"
    test_section_id = "test-section-789"
    test_title = "Test Bookmark"
    test_content = "This is a test bookmark content"
    
    try:
        logger.info("🧪 Testing bookmark operations...")
        
        # 1. Create a test bookmark
        logger.info("1️⃣ Creating test bookmark...")
        bookmark_id = r2_storage.save_bookmark(
            user_id=test_user_id,
            job_id=test_job_id,
            section_id=test_section_id,
            title=test_title,
            content=test_content
        )
        
        if not bookmark_id:
            logger.error("❌ Failed to create test bookmark")
            return False
        
        logger.info(f"✅ Created bookmark with ID: {bookmark_id}")
        
        # 2. Check if bookmark exists
        logger.info("2️⃣ Checking bookmark existence...")
        exists = r2_storage.bookmark_exists(user_id=test_user_id, bookmark_id=bookmark_id)
        
        if not exists:
            logger.error("❌ Bookmark should exist but doesn't")
            return False
        
        logger.info("✅ Bookmark exists as expected")
        
        # 3. Delete the bookmark
        logger.info("3️⃣ Deleting bookmark...")
        success = r2_storage.delete_bookmark(user_id=test_user_id, bookmark_id=bookmark_id)
        
        if not success:
            logger.error("❌ Failed to delete bookmark")
            return False
        
        logger.info("✅ Bookmark deleted successfully")
        
        # 4. Check if bookmark no longer exists
        logger.info("4️⃣ Verifying bookmark deletion...")
        exists_after_deletion = r2_storage.bookmark_exists(user_id=test_user_id, bookmark_id=bookmark_id)
        
        if exists_after_deletion:
            logger.error("❌ Bookmark should not exist after deletion")
            return False
        
        logger.info("✅ Bookmark no longer exists as expected")
        
        # 5. Try to delete non-existent bookmark
        logger.info("5️⃣ Testing deletion of non-existent bookmark...")
        fake_bookmark_id = "non-existent-bookmark-id"
        success_fake = r2_storage.delete_bookmark(user_id=test_user_id, bookmark_id=fake_bookmark_id)
        
        if success_fake:
            logger.error("❌ Deletion of non-existent bookmark should return False")
            return False
        
        logger.info("✅ Non-existent bookmark deletion handled correctly")
        
        logger.info("🎉 All bookmark operation tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed with exception: {e}")
        return False

def test_duplicate_deletion():
    """Test handling of duplicate deletion requests"""
    
    r2_storage = R2StorageService()
    
    if not r2_storage.is_available():
        logger.error("❌ R2 storage not available for testing")
        return False
    
    test_user_id = "test-user-duplicate"
    
    try:
        logger.info("🧪 Testing duplicate deletion handling...")
        
        # Create a bookmark
        bookmark_id = r2_storage.save_bookmark(
            user_id=test_user_id,
            job_id="test-job",
            section_id="test-section",
            title="Test Duplicate Deletion",
            content="Test content"
        )
        
        if not bookmark_id:
            logger.error("❌ Failed to create test bookmark")
            return False
        
        logger.info(f"✅ Created bookmark: {bookmark_id}")
        
        # Delete it once
        success1 = r2_storage.delete_bookmark(user_id=test_user_id, bookmark_id=bookmark_id)
        logger.info(f"First deletion result: {success1}")
        
        # Try to delete it again (should return False)
        success2 = r2_storage.delete_bookmark(user_id=test_user_id, bookmark_id=bookmark_id)
        logger.info(f"Second deletion result: {success2}")
        
        # Try to delete it a third time (should return False)
        success3 = r2_storage.delete_bookmark(user_id=test_user_id, bookmark_id=bookmark_id)
        logger.info(f"Third deletion result: {success3}")
        
        if success1 and not success2 and not success3:
            logger.info("✅ Duplicate deletion handling works correctly")
            return True
        else:
            logger.error("❌ Duplicate deletion handling failed")
            return False
        
    except Exception as e:
        logger.error(f"❌ Duplicate deletion test failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("🚀 Starting bookmark deletion tests...")
    
    # Run basic operations test
    basic_test_passed = test_bookmark_operations()
    
    # Run duplicate deletion test
    duplicate_test_passed = test_duplicate_deletion()
    
    if basic_test_passed and duplicate_test_passed:
        logger.info("🎉 All tests passed!")
        sys.exit(0)
    else:
        logger.error("❌ Some tests failed!")
        sys.exit(1)