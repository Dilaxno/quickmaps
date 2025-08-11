"""
Video Validation Service for checking video duration limits based on user plans
"""

import os
import subprocess
import json
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Configure logging
logger = logging.getLogger(__name__)

class PlanType(Enum):
    FREE = "free"
    STUDENT = "student"
    RESEARCHER = "researcher"
    EXPERT = "expert"

@dataclass
class VideoDurationLimits:
    """Video duration limits for each plan (in minutes)"""
    FREE = 30
    STUDENT = 60
    RESEARCHER = 120
    EXPERT = 300

@dataclass
class VideoValidationResult:
    """Result of video validation"""
    is_valid: bool
    duration_seconds: Optional[float]
    duration_minutes: Optional[float]
    allowed_minutes: int
    message: str
    user_plan: str

class VideoValidationService:
    """Service for validating video duration based on user subscription plans"""
    
    def __init__(self):
        self.duration_limits = {
            PlanType.FREE.value: VideoDurationLimits.FREE,
            PlanType.STUDENT.value: VideoDurationLimits.STUDENT,
            PlanType.RESEARCHER.value: VideoDurationLimits.RESEARCHER,
            PlanType.EXPERT.value: VideoDurationLimits.EXPERT
        }
    
    def get_video_duration(self, video_path: str) -> Optional[float]:
        """
        Get video duration in seconds using ffprobe
        Returns None if unable to determine duration
        """
        try:
            # Use ffprobe to get video duration
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"ffprobe failed with return code {result.returncode}: {result.stderr}")
                return None
            
            probe_data = json.loads(result.stdout)
            duration = float(probe_data['format']['duration'])
            
            logger.info(f"📹 Video duration detected: {duration:.2f} seconds ({duration/60:.2f} minutes)")
            return duration
            
        except subprocess.TimeoutExpired:
            logger.error("ffprobe command timed out")
            return None
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse ffprobe output: {e}")
            return None
        except FileNotFoundError:
            logger.error("ffprobe not found. Please install ffmpeg.")
            return None
        except Exception as e:
            logger.error(f"Error getting video duration: {e}")
            return None
    
    def get_user_plan_from_firestore(self, db, user_id: str) -> str:
        """Get user's current plan from Firestore"""
        try:
            if not db or not user_id:
                return PlanType.FREE.value
            
            user_ref = db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if not user_doc.exists:
                logger.warning(f"User {user_id} not found in database")
                return PlanType.FREE.value
            
            user_data = user_doc.to_dict()
            plan_id = user_data.get('planId', PlanType.FREE.value)
            subscription_status = user_data.get('subscriptionStatus', 'free')
            
            # If subscription is not active, default to free plan
            if subscription_status not in ['active']:
                plan_id = PlanType.FREE.value
            
            return plan_id
            
        except Exception as e:
            logger.error(f"Error fetching user plan: {e}")
            return PlanType.FREE.value
    
    def validate_video_duration(
        self, 
        video_path: str, 
        user_plan: str,
        user_id: str = None
    ) -> VideoValidationResult:
        """
        Validate if video duration is within user's plan limits
        
        Args:
            video_path: Path to the video file
            user_plan: User's subscription plan
            user_id: User ID for logging
            
        Returns:
            VideoValidationResult with validation details
        """
        try:
            # Get allowed duration for user's plan
            allowed_minutes = self.duration_limits.get(user_plan, VideoDurationLimits.FREE)
            
            # Get video duration
            duration_seconds = self.get_video_duration(video_path)
            
            if duration_seconds is None:
                return VideoValidationResult(
                    is_valid=False,
                    duration_seconds=None,
                    duration_minutes=None,
                    allowed_minutes=allowed_minutes,
                    message="Unable to determine video duration. Please ensure the video file is valid.",
                    user_plan=user_plan
                )
            
            duration_minutes = duration_seconds / 60
            
            # Log the validation attempt
            logger.info(f"🎬 Video validation for user {user_id}: "
                       f"Duration: {duration_minutes:.2f} min, "
                       f"Plan: {user_plan}, "
                       f"Limit: {allowed_minutes} min")
            
            # Check if within limits
            if duration_minutes <= allowed_minutes:
                return VideoValidationResult(
                    is_valid=True,
                    duration_seconds=duration_seconds,
                    duration_minutes=duration_minutes,
                    allowed_minutes=allowed_minutes,
                    message=f"Video approved. Duration: {duration_minutes:.1f} minutes (limit: {allowed_minutes} minutes)",
                    user_plan=user_plan
                )
            else:
                return VideoValidationResult(
                    is_valid=False,
                    duration_seconds=duration_seconds,
                    duration_minutes=duration_minutes,
                    allowed_minutes=allowed_minutes,
                    message=f"Video duration ({duration_minutes:.1f} minutes) exceeds your plan limit of {allowed_minutes} minutes. "
                           f"Please upgrade your plan or upload a shorter video.",
                    user_plan=user_plan
                )
                
        except Exception as e:
            logger.error(f"Error validating video duration: {e}")
            return VideoValidationResult(
                is_valid=False,
                duration_seconds=None,
                duration_minutes=None,
                allowed_minutes=self.duration_limits.get(user_plan, VideoDurationLimits.FREE),
                message=f"Error validating video: {str(e)}",
                user_plan=user_plan
            )
    
    def get_plan_upgrade_suggestion(self, current_plan: str, required_minutes: float) -> Dict[str, str]:
        """
        Suggest plan upgrade based on required video duration
        
        Args:
            current_plan: User's current plan
            required_minutes: Required video duration in minutes
            
        Returns:
            Dictionary with upgrade suggestions
        """
        suggestions = []
        
        for plan_type, limit in self.duration_limits.items():
            if limit >= required_minutes and plan_type != current_plan:
                suggestions.append({
                    "plan": plan_type,
                    "limit": limit,
                    "plan_name": plan_type.title()
                })
        
        # Sort by limit (ascending)
        suggestions.sort(key=lambda x: x["limit"])
        
        if suggestions:
            recommended = suggestions[0]
            return {
                "recommended_plan": recommended["plan"],
                "recommended_plan_name": recommended["plan_name"],
                "recommended_limit": recommended["limit"],
                "message": f"Consider upgrading to {recommended['plan_name']} plan (allows videos up to {recommended['limit']} minutes)"
            }
        
        return {
            "recommended_plan": PlanType.EXPERT.value,
            "recommended_plan_name": "Expert",
            "recommended_limit": VideoDurationLimits.EXPERT,
            "message": f"Your video requires the Expert plan (allows videos up to {VideoDurationLimits.EXPERT} minutes)"
        }
    
    def get_all_plan_limits(self) -> Dict[str, int]:
        """Get all plan duration limits for display purposes"""
        return self.duration_limits.copy()


# Create global instance
video_validation_service = VideoValidationService()