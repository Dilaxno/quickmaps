"""
Job Manager Module

Handles job status tracking and management for background tasks.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid

logger = logging.getLogger(__name__)

class JobManager:
    """Service for managing background job status and tracking"""
    
    def __init__(self):
        self.job_status: Dict[str, Dict[str, Any]] = {}
    
    def create_job(self, user_id: Optional[str] = None, user_email: Optional[str] = None, 
                   user_name: Optional[str] = None, action_type: Optional[str] = None,
                   workspace_id: Optional[str] = None) -> str:
        """
        Create a new job with unique ID
        
        Args:
            user_id (str, optional): User ID
            user_email (str, optional): User email
            user_name (str, optional): User name
            action_type (str, optional): Type of action for credit tracking
            workspace_id (str, optional): Workspace ID for collaboration
            
        Returns:
            str: Unique job ID
        """
        job_id = str(uuid.uuid4())
        self.job_status[job_id] = {
            "status": "created",
            "progress": "Job created...",
            "user_id": user_id,
            "user_email": user_email,
            "user_name": user_name,
            "credits_deducted": False,
            "action_type": action_type,
            "workspace_id": workspace_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        logger.info(f"Created job {job_id} with action_type: {action_type}")
        return job_id
    
    def update_job_status(self, job_id: str, status: str, progress: Optional[str] = None, 
                         **kwargs) -> None:
        """
        Update job status and progress
        
        Args:
            job_id (str): Job ID
            status (str): New status
            progress (str, optional): Progress message
            **kwargs: Additional fields to update
        """
        if job_id not in self.job_status:
            logger.warning(f"Job {job_id} not found")
            return
        
        self.job_status[job_id]["status"] = status
        self.job_status[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        if progress:
            self.job_status[job_id]["progress"] = progress
        
        # Update additional fields
        for key, value in kwargs.items():
            self.job_status[job_id][key] = value
    
    def update_job_progress(self, job_id: str, progress: str) -> None:
        """
        Update job progress message
        
        Args:
            job_id (str): Job ID
            progress (str): Progress message
        """
        if job_id not in self.job_status:
            logger.warning(f"Job {job_id} not found")
            return
        
        self.job_status[job_id]["progress"] = progress
        self.job_status[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    def set_job_completed(self, job_id: str, result_data: Dict[str, Any]) -> None:
        """
        Mark job as completed with result data
        
        Args:
            job_id (str): Job ID
            result_data (dict): Result data to store
        """
        if job_id not in self.job_status:
            logger.warning(f"Job {job_id} not found")
            return
        
        self.job_status[job_id].update({
            "status": "completed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **result_data
        })
    
    def set_job_error(self, job_id: str, error: str) -> None:
        """
        Mark job as failed with error message
        
        Args:
            job_id (str): Job ID
            error (str): Error message
        """
        if job_id not in self.job_status:
            logger.warning(f"Job {job_id} not found")
            return
        
        self.job_status[job_id].update({
            "status": "error",
            "error": error,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job status and information
        
        Args:
            job_id (str): Job ID
            
        Returns:
            dict: Job status data or None if not found
        """
        job_data = self.job_status.get(job_id)
        if not job_data:
            logger.warning(f"Job {job_id} not found. Available jobs: {list(self.job_status.keys())}")
        return job_data
    
    def job_exists(self, job_id: str) -> bool:
        """
        Check if job exists
        
        Args:
            job_id (str): Job ID
            
        Returns:
            bool: True if job exists
        """
        return job_id in self.job_status
    
    def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        """
        Clean up old jobs older than specified hours
        
        Args:
            max_age_hours (int): Maximum age in hours
            
        Returns:
            int: Number of jobs cleaned up
        """
        from datetime import timedelta
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        jobs_to_remove = []
        
        for job_id, job_data in self.job_status.items():
            try:
                created_at = datetime.fromisoformat(job_data.get("created_at", ""))
                if created_at.replace(tzinfo=timezone.utc) < cutoff_time:
                    jobs_to_remove.append(job_id)
            except (ValueError, TypeError):
                # If we can't parse the date, consider it old
                jobs_to_remove.append(job_id)
        
        for job_id in jobs_to_remove:
            del self.job_status[job_id]
        
        if jobs_to_remove:
            logger.info(f"Cleaned up {len(jobs_to_remove)} old jobs")
        
        return len(jobs_to_remove)
    
    def get_user_jobs(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all jobs for a specific user
        
        Args:
            user_id (str): User ID
            
        Returns:
            dict: Dictionary of job_id -> job_data for the user
        """
        user_jobs = {}
        for job_id, job_data in self.job_status.items():
            if job_data.get("user_id") == user_id:
                user_jobs[job_id] = job_data
        return user_jobs

# Global instance
job_manager = JobManager()