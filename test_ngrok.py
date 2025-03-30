#!/usr/bin/env python3
"""
Test script for ngrok connectivity.
This helps diagnose ngrok issues independently of the main application.
"""

import os
import sys
import logging
import time

# Set up logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("NgrokTest")

def test_ngrok_connection():
    """Test if ngrok can establish a tunnel"""
    try:
        from pyngrok import ngrok, conf
        from pyngrok.exception import PyngrokError
        
        logger.info("pyngrok module found")
        
        # Get ngrok version
        try:
            version = ngrok.get_ngrok_version()
            logger.info(f"Ngrok version: {version}")
        except Exception as e:
            logger.warning(f"Could not get ngrok version: {e}")
        
        # Try to connect with and without auth token
        logger.info("Testing ngrok connection without auth token...")
        try:
            # Check for existing tunnels and close them
            tunnels = ngrok.get_tunnels()
            if tunnels:
                logger.info(f"Found {len(tunnels)} existing tunnels, cleaning up...")
                for tunnel in tunnels:
                    ngrok.disconnect(tunnel.public_url)
            
            # Connect without auth token
            tunnel = ngrok.connect(8081, "http")
            logger.info(f"Success! Tunnel established at: {tunnel.public_url}")
            time.sleep(1)
            ngrok.disconnect(tunnel.public_url)
        except PyngrokError as e:
            logger.error(f"Ngrok error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # Try with auth token if specified
        auth_token = input("Enter your ngrok auth token (or press enter to skip): ").strip()
        if auth_token:
            logger.info("Testing ngrok connection with auth token...")
            try:
                ngrok.set_auth_token(auth_token)
                tunnel = ngrok.connect(8082, "http")
                logger.info(f"Success with auth token! Tunnel established at: {tunnel.public_url}")
                
                # Test regions
                regions = ["us", "eu", "ap", "au", "sa", "jp", "in"]
                for region in regions:
                    try:
                        logger.info(f"Testing region: {region}")
                        conf.get_default().region = region
                        tunnel = ngrok.connect(8083, "http")
                        logger.info(f"Region {region} works! Tunnel: {tunnel.public_url}")
                        ngrok.disconnect(tunnel.public_url)
                    except Exception as e:
                        logger.error(f"Region {region} failed: {e}")
                
            except Exception as e:
                logger.error(f"Auth token test failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        logger.info("Ngrok test complete")
        
    except ImportError:
        logger.error("pyngrok module not installed. Install with: pip install pyngrok")
        return False
    
    return True

if __name__ == "__main__":
    print("==== Ngrok Connection Test ====")
    test_ngrok_connection()
    print("==============================")
    print("If the test failed, check your internet connection and firewall settings.")
    print("For more information, visit: https://ngrok.com/docs")
