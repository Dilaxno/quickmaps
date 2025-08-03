import os
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

@dataclass
class DeviceFingerprint:
    """Device fingerprint data structure"""
    device_id: str
    user_id: str
    visitor_id: str
    confidence: float
    components: Dict
    risk_assessment: Dict
    registration_timestamp: str
    last_seen: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_active: bool = True

class DeviceFingerprintManager:
    """
    Manages device fingerprints for duplicate signup prevention
    Uses file-based storage for simplicity (can be upgraded to database later)
    """
    
    def __init__(self, storage_path: str = None):
        if storage_path is None:
            storage_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'device_fingerprints.json')
        
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache for performance
        self._cache = {}
        self._load_from_file()
        
        logger.info(f"Device fingerprint manager initialized with storage: {self.storage_path}")
    
    def _load_from_file(self):
        """Load device fingerprints from file"""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    
                for device_id, device_data in data.items():
                    self._cache[device_id] = DeviceFingerprint(**device_data)
                    
                logger.info(f"Loaded {len(self._cache)} device fingerprints from storage")
            else:
                logger.info("No existing device fingerprints file found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading device fingerprints: {e}")
            self._cache = {}
    
    def _save_to_file(self):
        """Save device fingerprints to file"""
        try:
            data = {}
            for device_id, fingerprint in self._cache.items():
                data[device_id] = asdict(fingerprint)
                
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
                
            logger.debug(f"Saved {len(data)} device fingerprints to storage")
        except Exception as e:
            logger.error(f"Error saving device fingerprints: {e}")
    
    def register_device(self, device_data: Dict, user_id: str, ip_address: str = None, user_agent: str = None) -> Dict:
        """
        Register a new device fingerprint
        
        Args:
            device_data: Device fingerprint data from frontend
            user_id: User ID from Firebase
            ip_address: Client IP address
            user_agent: User agent string
            
        Returns:
            Registration result
        """
        try:
            device_id = device_data.get('device_id')
            if not device_id:
                raise ValueError("Device ID is required")
            
            # Check if device is already registered
            if device_id in self._cache:
                existing = self._cache[device_id]
                if existing.user_id != user_id and existing.is_active:
                    raise ValueError(f"Device {device_id} is already registered to another user")
            
            # Create device fingerprint record
            fingerprint = DeviceFingerprint(
                device_id=device_id,
                user_id=user_id,
                visitor_id=device_data.get('fingerprint', {}).get('visitorId', ''),
                confidence=device_data.get('fingerprint', {}).get('confidence', 0),
                components=device_data.get('fingerprint', {}).get('components', {}),
                risk_assessment=device_data.get('risk_assessment', {}),
                registration_timestamp=device_data.get('registration_timestamp', datetime.now().isoformat()),
                last_seen=datetime.now().isoformat(),
                ip_address=ip_address,
                user_agent=user_agent,
                is_active=True
            )
            
            # Store in cache and file
            self._cache[device_id] = fingerprint
            self._save_to_file()
            
            logger.info(f"Device {device_id} registered for user {user_id}")
            
            return {
                "success": True,
                "device_id": device_id,
                "message": "Device registered successfully",
                "risk_score": fingerprint.risk_assessment.get('riskScore', 0)
            }
            
        except Exception as e:
            logger.error(f"Error registering device: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def validate_device(self, device_data: Dict, user_id: str, ip_address: str = None) -> Dict:
        """
        Validate a device fingerprint for an existing user
        
        Args:
            device_data: Device fingerprint data from frontend
            user_id: User ID from Firebase
            ip_address: Client IP address
            
        Returns:
            Validation result
        """
        try:
            device_id = device_data.get('device_id')
            if not device_id:
                raise ValueError("Device ID is required")
            
            # Check if device exists
            if device_id not in self._cache:
                # Device not registered - this could be suspicious
                logger.warning(f"Unknown device {device_id} attempting to access user {user_id}")
                return {
                    "valid": False,
                    "reason": "device_not_registered",
                    "message": "Device not recognized. Please sign up from this device first."
                }
            
            fingerprint = self._cache[device_id]
            
            # Check if device belongs to the user
            if fingerprint.user_id != user_id:
                logger.warning(f"Device {device_id} registered to {fingerprint.user_id} but accessed by {user_id}")
                return {
                    "valid": False,
                    "reason": "device_user_mismatch",
                    "message": "This device is registered to a different user."
                }
            
            # Check if device is active
            if not fingerprint.is_active:
                return {
                    "valid": False,
                    "reason": "device_inactive",
                    "message": "This device has been deactivated."
                }
            
            # Update last seen
            fingerprint.last_seen = datetime.now().isoformat()
            if ip_address:
                fingerprint.ip_address = ip_address
            
            self._save_to_file()
            
            logger.info(f"Device {device_id} validated for user {user_id}")
            
            return {
                "valid": True,
                "device_id": device_id,
                "message": "Device validated successfully",
                "last_registration": fingerprint.registration_timestamp
            }
            
        except Exception as e:
            logger.error(f"Error validating device: {e}")
            return {
                "valid": False,
                "error": str(e)
            }
    
    def check_device_status(self, device_id: str) -> Dict:
        """
        Check if a device is registered and get its status
        
        Args:
            device_id: Device ID to check
            
        Returns:
            Device status information
        """
        try:
            if device_id not in self._cache:
                return {
                    "exists": False,
                    "device_id": device_id
                }
            
            fingerprint = self._cache[device_id]
            
            return {
                "exists": True,
                "device_id": device_id,
                "user_id": fingerprint.user_id,
                "registration_date": fingerprint.registration_timestamp,
                "last_seen": fingerprint.last_seen,
                "is_active": fingerprint.is_active,
                "risk_score": fingerprint.risk_assessment.get('riskScore', 0),
                "confidence": fingerprint.confidence
            }
            
        except Exception as e:
            logger.error(f"Error checking device status: {e}")
            return {
                "exists": False,
                "error": str(e)
            }
    
    def get_user_devices(self, user_id: str) -> List[Dict]:
        """
        Get all devices registered to a user
        
        Args:
            user_id: User ID to get devices for
            
        Returns:
            List of user's devices
        """
        try:
            user_devices = []
            
            for device_id, fingerprint in self._cache.items():
                if fingerprint.user_id == user_id and fingerprint.is_active:
                    user_devices.append({
                        "device_id": device_id,
                        "visitor_id": fingerprint.visitor_id,
                        "registration_date": fingerprint.registration_timestamp,
                        "last_seen": fingerprint.last_seen,
                        "risk_score": fingerprint.risk_assessment.get('riskScore', 0),
                        "confidence": fingerprint.confidence,
                        "platform": fingerprint.components.get('platform', 'Unknown'),
                        "browser": fingerprint.components.get('userAgent', 'Unknown')[:100] if fingerprint.components.get('userAgent') else 'Unknown'
                    })
            
            return user_devices
            
        except Exception as e:
            logger.error(f"Error getting user devices: {e}")
            return []
    
    def deactivate_device(self, device_id: str, user_id: str = None) -> Dict:
        """
        Deactivate a device (soft delete)
        
        Args:
            device_id: Device ID to deactivate
            user_id: Optional user ID for additional verification
            
        Returns:
            Deactivation result
        """
        try:
            if device_id not in self._cache:
                return {
                    "success": False,
                    "error": "Device not found"
                }
            
            fingerprint = self._cache[device_id]
            
            # Optional user verification
            if user_id and fingerprint.user_id != user_id:
                return {
                    "success": False,
                    "error": "Device belongs to different user"
                }
            
            fingerprint.is_active = False
            self._save_to_file()
            
            logger.info(f"Device {device_id} deactivated")
            
            return {
                "success": True,
                "message": "Device deactivated successfully"
            }
            
        except Exception as e:
            logger.error(f"Error deactivating device: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_statistics(self) -> Dict:
        """Get device fingerprinting statistics"""
        try:
            active_devices = sum(1 for fp in self._cache.values() if fp.is_active)
            inactive_devices = sum(1 for fp in self._cache.values() if not fp.is_active)
            
            high_risk_devices = sum(1 for fp in self._cache.values() 
                                  if fp.risk_assessment.get('isHighRisk', False) and fp.is_active)
            
            unique_users = len(set(fp.user_id for fp in self._cache.values() if fp.is_active))
            
            return {
                "total_devices": len(self._cache),
                "active_devices": active_devices,
                "inactive_devices": inactive_devices,
                "high_risk_devices": high_risk_devices,
                "unique_users": unique_users,
                "average_devices_per_user": round(active_devices / max(unique_users, 1), 2)
            }
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}

# Global instance
device_manager = DeviceFingerprintManager()

def get_device_manager() -> DeviceFingerprintManager:
    """Get the global device fingerprint manager instance"""
    return device_manager