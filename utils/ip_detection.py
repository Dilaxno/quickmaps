import os
import IP2Proxy
from typing import Dict, Optional
from fastapi import Request
import logging

logger = logging.getLogger(__name__)

class VPNProxyDetector:
    """
    VPN/Proxy detection using IP2PROXY database
    """
    
    def __init__(self, database_path: str = None):
        """
        Initialize the IP2PROXY detector
        
        Args:
            database_path: Path to the IP2PROXY database file
        """
        if database_path is None:
            database_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'IP2PROXY-LITE-PX10.BIN')
        
        self.database_path = database_path
        self.ip2proxy = None
        self.initialize_database()
    
    def initialize_database(self):
        """Initialize the IP2PROXY database"""
        try:
            if os.path.exists(self.database_path):
                self.ip2proxy = IP2Proxy.IP2Proxy()
                self.ip2proxy.open(self.database_path)
                logger.info(f"IP2PROXY database loaded from: {self.database_path}")
            else:
                logger.error(f"IP2PROXY database not found at: {self.database_path}")
                self.ip2proxy = None
        except Exception as e:
            logger.error(f"Error initializing IP2PROXY database: {e}")
            self.ip2proxy = None
    
    def get_client_ip(self, request: Request) -> str:
        """
        Extract client IP from request headers, considering proxy headers
        
        Args:
            request: FastAPI request object
            
        Returns:
            Client IP address
        """
        # Check for forwarded headers first (common in production behind proxies/load balancers)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs, the first one is the original client
            client_ip = forwarded_for.split(",")[0].strip()
            if client_ip:
                return client_ip
        
        # Check other common headers
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        cf_connecting_ip = request.headers.get("CF-Connecting-IP")  # Cloudflare
        if cf_connecting_ip:
            return cf_connecting_ip.strip()
        
        # Fall back to direct client IP
        return request.client.host if request.client else "unknown"
    
    def check_ip(self, ip_address: str) -> Dict[str, any]:
        """
        Check if an IP address is from a VPN/Proxy
        
        Args:
            ip_address: IP address to check
            
        Returns:
            Dictionary containing detection results
        """
        if not self.ip2proxy:
            return {
                "is_proxy": False,
                "is_vpn": False,
                "proxy_type": "UNKNOWN",
                "country_code": "UNKNOWN",
                "country_name": "UNKNOWN",
                "region": "UNKNOWN",
                "city": "UNKNOWN",
                "isp": "UNKNOWN",
                "error": "IP2PROXY database not available"
            }
        
        try:
            record = self.ip2proxy.get_all(ip_address)
            
            # Handle both object attributes and dictionary keys
            def safe_get(data, key):
                if isinstance(data, dict):
                    return data.get(key, "-")
                else:
                    return getattr(data, key, "-")
            
            # Get proxy information
            proxy_type = safe_get(record, "proxy_type")
            is_proxy_flag = safe_get(record, "is_proxy")
            
            # Map proxy detection - use both the flag and proxy type
            is_proxy = False
            if is_proxy_flag == 1 or is_proxy_flag == "1":
                is_proxy = True
            elif proxy_type not in ["-", ""]:
                is_proxy = proxy_type not in ["DCH"]  # DCH = Data Center/Hosting, might be legitimate
            
            # Determine if it's a VPN/TOR specifically
            is_vpn = proxy_type in ["VPN", "TOR", "PUB", "WEB", "SES"]  # VPN, TOR, Public Proxy, Web Proxy, Search Engine Spider
            
            # Get threat level if available
            threat = safe_get(record, "threat")
            provider = safe_get(record, "provider")
            
            result = {
                "ip_address": ip_address,
                "is_proxy": is_proxy,
                "is_vpn": is_vpn,
                "proxy_type": proxy_type,
                "is_proxy_flag": is_proxy_flag,
                "country_code": safe_get(record, "country_short"),
                "country_name": safe_get(record, "country_long"),
                "region": safe_get(record, "region"),
                "city": safe_get(record, "city"),
                "isp": safe_get(record, "isp"),
                "domain": safe_get(record, "domain"),
                "usage_type": safe_get(record, "usage_type"),
                "asn": safe_get(record, "asn"),
                "as_name": safe_get(record, "as_name"),
                "last_seen": safe_get(record, "last_seen"),
                "threat": threat,
                "provider": provider
            }
            
            logger.info(f"IP check result for {ip_address}: proxy={is_proxy}, vpn={is_vpn}, type={proxy_type}")
            return result
            
        except Exception as e:
            logger.error(f"Error checking IP {ip_address}: {e}")
            return {
                "ip_address": ip_address,
                "is_proxy": False,
                "is_vpn": False,
                "proxy_type": "ERROR",
                "country_code": "UNKNOWN",
                "country_name": "UNKNOWN",
                "region": "UNKNOWN",
                "city": "UNKNOWN",
                "isp": "UNKNOWN",
                "error": str(e)
            }
    
    def is_blocked_ip(self, ip_address: str, strict_mode: bool = True) -> tuple[bool, Dict[str, any]]:
        """
        Check if an IP should be blocked based on VPN/Proxy detection
        
        Args:
            ip_address: IP address to check
            strict_mode: If True, block all proxy types. If False, only block VPN/TOR/Public proxies
            
        Returns:
            Tuple of (should_block, detection_result)
        """
        result = self.check_ip(ip_address)
        
        if strict_mode:
            should_block = result.get("is_proxy", False)
        else:
            should_block = result.get("is_vpn", False)
        
        return should_block, result

# Global instance
vpn_detector = VPNProxyDetector()

def get_vpn_detector() -> VPNProxyDetector:
    """Get the global VPN detector instance"""
    return vpn_detector