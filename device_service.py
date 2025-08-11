import os
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import logging
from google.cloud import firestore
from user_agents import parse as parse_user_agent
import ipaddress

logger = logging.getLogger(__name__)

class DeviceService:
    def __init__(self):
        # Initialize Firestore
        credentials_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        if credentials_json:
            try:
                credentials_dict = json.loads(credentials_json)
                self.db = firestore.Client.from_service_account_info(credentials_dict)
            except Exception as e:
                logger.error(f"Failed to initialize Firestore: {e}")
                self.db = None
        else:
            logger.warning("Firestore credentials not found")
            self.db = None
    
    def _get_ip_location(self, ip_address: str) -> Dict[str, str]:
        """
        Get location information for an IP address using a free IP geolocation service
        
        Args:
            ip_address: IP address to lookup
            
        Returns:
            Dict containing location information
        """
        try:
            # Skip private/local IP addresses
            try:
                ip_obj = ipaddress.ip_address(ip_address)
                if ip_obj.is_private or ip_obj.is_loopback:
                    return {
                        'country': 'Local Network',
                        'region': 'Private',
                        'city': 'Local',
                        'timezone': 'Local'
                    }
            except:
                pass
            
            # Use ip-api.com (free service with 1000 requests/hour limit)
            response = requests.get(
                f"http://ip-api.com/json/{ip_address}?fields=status,country,regionName,city,timezone",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return {
                        'country': data.get('country', 'Unknown'),
                        'region': data.get('regionName', 'Unknown'),
                        'city': data.get('city', 'Unknown'),
                        'timezone': data.get('timezone', 'Unknown')
                    }
            
            return {
                'country': 'Unknown',
                'region': 'Unknown', 
                'city': 'Unknown',
                'timezone': 'Unknown'
            }
            
        except Exception as e:
            logger.warning(f"Failed to get IP location for {ip_address}: {e}")
            return {
                'country': 'Unknown',
                'region': 'Unknown',
                'city': 'Unknown', 
                'timezone': 'Unknown'
            }
    
    def _parse_user_agent(self, user_agent: str) -> Dict[str, str]:
        """
        Parse user agent string to extract browser and OS information
        
        Args:
            user_agent: User agent string
            
        Returns:
            Dict containing browser and OS information
        """
        try:
            parsed = parse_user_agent(user_agent)
            
            # Get browser info
            browser_name = parsed.browser.family or 'Unknown Browser'
            browser_version = parsed.browser.version_string or ''
            browser = f"{browser_name} {browser_version}".strip()
            
            # Get OS info
            os_name = parsed.os.family or 'Unknown OS'
            os_version = parsed.os.version_string or ''
            os_info = f"{os_name} {os_version}".strip()
            
            # Generate device name based on OS and browser
            device_name = f"{os_name} - {browser_name}"
            
            return {
                'browser': browser,
                'os': os_info,
                'device_name': device_name,
                'user_agent': user_agent
            }
            
        except Exception as e:
            logger.warning(f"Failed to parse user agent: {e}")
            return {
                'browser': 'Unknown Browser',
                'os': 'Unknown OS',
                'device_name': 'Unknown Device',
                'user_agent': user_agent
            }
    
    def _generate_device_fingerprint(self, request_data: Dict[str, Any]) -> str:
        """
        Generate a unique device fingerprint based on request data
        
        Args:
            request_data: Dictionary containing request information
            
        Returns:
            Unique device fingerprint string
        """
        # Combine various device characteristics
        fingerprint_data = {
            'user_agent': request_data.get('user_agent', ''),
            'ip_address': request_data.get('ip_address', ''),
            'screen_resolution': request_data.get('screen_resolution', ''),
            'timezone': request_data.get('timezone', ''),
            'language': request_data.get('language', ''),
            'platform': request_data.get('platform', '')
        }
        
        # Create a hash of the combined data
        fingerprint_string = json.dumps(fingerprint_data, sort_keys=True)
        fingerprint_hash = hashlib.sha256(fingerprint_string.encode()).hexdigest()
        
        return fingerprint_hash[:16]  # Use first 16 characters
    
    def register_device(self, user_id: str, request_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Register a new device for a user
        
        Args:
            user_id: User's unique identifier
            request_data: Dictionary containing device and request information
            
        Returns:
            Tuple of (is_new_device, device_info)
        """
        if not self.db:
            logger.error("Firestore not initialized")
            return False, {}
        
        try:
            # Extract information from request
            ip_address = request_data.get('ip_address', 'Unknown')
            user_agent = request_data.get('user_agent', '')
            
            # Parse user agent
            ua_info = self._parse_user_agent(user_agent)
            
            # Get location information
            location_info = self._get_ip_location(ip_address)
            location_str = f"{location_info['city']}, {location_info['region']}, {location_info['country']}"
            
            # Generate device fingerprint
            device_fingerprint = self._generate_device_fingerprint(request_data)
            
            # Create device info
            device_info = {
                'device_id': device_fingerprint,
                'user_id': user_id,
                'device_name': ua_info['device_name'],
                'browser': ua_info['browser'],
                'os': ua_info['os'],
                'user_agent': user_agent,
                'ip_address': ip_address,
                'location': location_str,
                'country': location_info['country'],
                'region': location_info['region'],
                'city': location_info['city'],
                'timezone': location_info['timezone'],
                'first_seen': datetime.now(timezone.utc).isoformat(),
                'last_seen': datetime.now(timezone.utc).isoformat(),
                'login_count': 1,
                'is_active': True,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            # Check if device already exists
            devices_ref = self.db.collection('user_devices')
            existing_device = devices_ref.where('device_id', '==', device_fingerprint).where('user_id', '==', user_id).limit(1).get()
            
            is_new_device = len(existing_device) == 0
            
            if is_new_device:
                # Add new device
                devices_ref.add(device_info)
                logger.info(f"New device registered for user {user_id}: {device_fingerprint}")
            else:
                # Update existing device
                existing_doc = existing_device[0]
                existing_doc.reference.update({
                    'last_seen': datetime.now(timezone.utc).isoformat(),
                    'login_count': firestore.Increment(1),
                    'ip_address': ip_address,  # Update current IP
                    'location': location_str,  # Update current location
                    'updated_at': datetime.now(timezone.utc).isoformat()
                })
                logger.info(f"Updated existing device for user {user_id}: {device_fingerprint}")
            
            return is_new_device, device_info
            
        except Exception as e:
            logger.error(f"Error registering device: {e}")
            return False, {}
    
    def get_user_devices(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all devices for a user
        
        Args:
            user_id: User's unique identifier
            
        Returns:
            List of device information dictionaries
        """
        if not self.db:
            logger.error("Firestore not initialized")
            return []
        
        try:
            devices_ref = self.db.collection('user_devices')
            devices = devices_ref.where('user_id', '==', user_id).where('is_active', '==', True).order_by('last_seen', direction=firestore.Query.DESCENDING).get()
            
            device_list = []
            for device_doc in devices:
                device_data = device_doc.to_dict()
                device_data['id'] = device_doc.id
                
                # Format dates for display
                try:
                    last_seen = datetime.fromisoformat(device_data['last_seen'].replace('Z', '+00:00'))
                    device_data['last_seen_formatted'] = last_seen.strftime('%B %d, %Y at %I:%M %p UTC')
                except:
                    device_data['last_seen_formatted'] = device_data.get('last_seen', 'Unknown')
                
                try:
                    first_seen = datetime.fromisoformat(device_data['first_seen'].replace('Z', '+00:00'))
                    device_data['first_seen_formatted'] = first_seen.strftime('%B %d, %Y at %I:%M %p UTC')
                except:
                    device_data['first_seen_formatted'] = device_data.get('first_seen', 'Unknown')
                
                device_list.append(device_data)
            
            return device_list
            
        except Exception as e:
            logger.error(f"Error getting user devices: {e}")
            return []
    
    def remove_device(self, user_id: str, device_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Remove a device from user's account
        
        Args:
            user_id: User's unique identifier
            device_id: Device document ID to remove
            
        Returns:
            Tuple of (success, device_info)
        """
        if not self.db:
            logger.error("Firestore not initialized")
            return False, {}
        
        try:
            # Get device document
            device_doc = self.db.collection('user_devices').document(device_id).get()
            
            if not device_doc.exists:
                logger.warning(f"Device {device_id} not found")
                return False, {}
            
            device_data = device_doc.to_dict()
            
            # Verify device belongs to user
            if device_data.get('user_id') != user_id:
                logger.warning(f"Device {device_id} does not belong to user {user_id}")
                return False, {}
            
            # Mark device as inactive instead of deleting
            device_doc.reference.update({
                'is_active': False,
                'removed_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Device {device_id} removed for user {user_id}")
            return True, device_data
            
        except Exception as e:
            logger.error(f"Error removing device: {e}")
            return False, {}
    
    def get_device_info(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific device
        
        Args:
            device_id: Device document ID
            
        Returns:
            Device information dictionary or None
        """
        if not self.db:
            logger.error("Firestore not initialized")
            return None
        
        try:
            device_doc = self.db.collection('user_devices').document(device_id).get()
            
            if device_doc.exists:
                device_data = device_doc.to_dict()
                device_data['id'] = device_doc.id
                return device_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting device info: {e}")
            return None
    
    def cleanup_old_devices(self, days_threshold: int = 90) -> int:
        """
        Clean up devices that haven't been seen for a specified number of days
        
        Args:
            days_threshold: Number of days after which to mark devices as inactive
            
        Returns:
            Number of devices cleaned up
        """
        if not self.db:
            logger.error("Firestore not initialized")
            return 0
        
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)
            cutoff_iso = cutoff_date.isoformat()
            
            devices_ref = self.db.collection('user_devices')
            old_devices = devices_ref.where('last_seen', '<', cutoff_iso).where('is_active', '==', True).get()
            
            cleanup_count = 0
            for device_doc in old_devices:
                device_doc.reference.update({
                    'is_active': False,
                    'auto_removed_at': datetime.now(timezone.utc).isoformat(),
                    'removal_reason': f'inactive_for_{days_threshold}_days'
                })
                cleanup_count += 1
            
            logger.info(f"Cleaned up {cleanup_count} old devices")
            return cleanup_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old devices: {e}")
            return 0

# Global instance
device_service = DeviceService()