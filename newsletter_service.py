"""
Newsletter Service for handling user signups and Excel export
"""

import os
import json
import logging
import requests
from datetime import datetime
from typing import Dict, Optional, Any
import pandas as pd
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logger = logging.getLogger(__name__)

class NewsletterService:
    """Service for handling newsletter signups and Excel export"""
    
    def __init__(self):
        self.excel_file_path = Path("newsletter_signups.xlsx")
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # Initialize Excel file if it doesn't exist
        self._initialize_excel_file()
    
    def _initialize_excel_file(self):
        """Initialize Excel file with headers if it doesn't exist"""
        if not self.excel_file_path.exists():
            df = pd.DataFrame(columns=[
                'email', 
                'signup_type', 
                'timestamp', 
                'ip_address', 
                'user_agent', 
                'country', 
                'city', 
                'region'
            ])
            df.to_excel(self.excel_file_path, index=False)
            logger.info(f"📊 Created newsletter Excel file: {self.excel_file_path}")
    
    async def get_location_info(self, ip_address: str) -> Dict[str, str]:
        """Get location information from IP address using ipapi.co"""
        try:
            # Use ipapi.co for free IP geolocation
            response = requests.get(f"http://ipapi.co/{ip_address}/json/", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return {
                    'country': data.get('country_name', 'Unknown'),
                    'city': data.get('city', 'Unknown'),
                    'region': data.get('region', 'Unknown')
                }
        except Exception as e:
            logger.warning(f"⚠️ Could not get location for IP {ip_address}: {e}")
        
        return {
            'country': 'Unknown',
            'city': 'Unknown', 
            'region': 'Unknown'
        }
    
    async def add_newsletter_signup(self, 
                                  email: str, 
                                  signup_type: str,
                                  ip_address: str = None,
                                  user_agent: str = None) -> bool:
        """Add newsletter signup to Excel file"""
        try:
            # Get location info if IP is provided
            location_info = {'country': 'Unknown', 'city': 'Unknown', 'region': 'Unknown'}
            if ip_address and ip_address != '127.0.0.1':
                location_info = await self.get_location_info(ip_address)
            
            # Prepare signup data
            signup_data = {
                'email': email,
                'signup_type': signup_type,  # 'credit_exhausted' or 'pricing_upgrade'
                'timestamp': datetime.now().isoformat(),
                'ip_address': ip_address or 'Unknown',
                'user_agent': user_agent or 'Unknown',
                'country': location_info['country'],
                'city': location_info['city'],
                'region': location_info['region']
            }
            
            # Add to Excel file in background thread
            await asyncio.get_event_loop().run_in_executor(
                self.executor, 
                self._add_to_excel, 
                signup_data
            )
            
            logger.info(f"📧 Newsletter signup added: {email} ({signup_type})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error adding newsletter signup: {e}")
            return False
    
    def _add_to_excel(self, signup_data: Dict[str, str]):
        """Add signup data to Excel file (runs in thread)"""
        try:
            # Read existing data
            if self.excel_file_path.exists():
                df = pd.read_excel(self.excel_file_path)
            else:
                df = pd.DataFrame()
            
            # Add new row
            new_row = pd.DataFrame([signup_data])
            df = pd.concat([df, new_row], ignore_index=True)
            
            # Save to Excel
            df.to_excel(self.excel_file_path, index=False)
            
        except Exception as e:
            logger.error(f"❌ Error writing to Excel file: {e}")
            raise
    
    def get_signup_stats(self) -> Dict[str, Any]:
        """Get newsletter signup statistics"""
        try:
            if not self.excel_file_path.exists():
                return {'total_signups': 0, 'by_type': {}}
            
            df = pd.read_excel(self.excel_file_path)
            
            stats = {
                'total_signups': len(df),
                'by_type': df['signup_type'].value_counts().to_dict(),
                'by_country': df['country'].value_counts().head(10).to_dict(),
                'recent_signups': len(df[df['timestamp'] >= (datetime.now() - pd.Timedelta(days=7)).isoformat()])
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error getting signup stats: {e}")
            return {'total_signups': 0, 'by_type': {}}

# Global newsletter service instance
newsletter_service = NewsletterService()