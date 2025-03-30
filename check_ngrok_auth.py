#!/usr/bin/env python3
"""
Check if the ngrok auth token is valid.
"""

import sys
import logging
from quality.config import Config

# Set up logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("NgrokAuthCheck")

def check_auth_token():
    """Verify if the ngrok auth token in config is valid"""
    try:
        from pyngrok import ngrok
        
        # Get token from config
        config = Config()
        token = getattr(config, 'NGROK_AUTH_TOKEN', None)
        
        if not token:
            logger.error("No auth token found in config.py")
            return False
            
        logger.info(f"Found auth token in config: {token[:5]}...{token[-5:]}")
        
        # Try setting the auth token
        try:
            ngrok.set_auth_token(token)
            logger.info("Auth token accepted by ngrok!")
            
            # Try to create a tunnel
            try:
                tunnel = ngrok.connect(9999, "http")
                logger.info(f"Tunnel created successfully: {tunnel.public_url}")
                ngrok.disconnect(tunnel.public_url)
                return True
            except Exception as e:
                logger.error(f"Failed to create tunnel: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Invalid auth token: {e}")
            logger.info("Visit https://dashboard.ngrok.com/get-started/your-authtoken to get a valid token")
            return False
            
    except ImportError:
        logger.error("pyngrok module not installed. Install with: pip install pyngrok")
        return False

if __name__ == "__main__":
    print("==== Ngrok Auth Token Check ====")
    result = check_auth_token()
    print("===============================")
    if result:
        print("✅ Auth token is valid and working!")
    else:
        print("❌ Auth token check failed. Please update your token in config.py")
        print("Get a new token at: https://dashboard.ngrok.com/get-started/your-authtoken")
