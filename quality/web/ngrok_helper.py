"""
Helper module for ngrok integration to make the web interface accessible remotely.
"""
import logging
import os
import subprocess
import time
from threading import Thread
import json

logger = logging.getLogger("NgrokHelper")

try:
    # Try to import pyngrok
    from pyngrok import ngrok, conf
    NGROK_AVAILABLE = True
except ImportError:
    logger.warning("pyngrok not installed. Remote access via ngrok will not be available.")
    NGROK_AVAILABLE = False

class NgrokTunnel:
    def __init__(self, port=8080, auth_token=None, region="us"):
        """Initialize ngrok tunnel manager"""
        self.port = port
        self.auth_token = auth_token
        self.region = region
        self.tunnel = None
        self.public_url = None
        self.running = False
        self.status_thread = None
        
    def start(self):
        """Start ngrok tunnel to the specified port"""
        if not NGROK_AVAILABLE:
            logger.error("Cannot start ngrok: pyngrok not installed. Install with: pip install pyngrok")
            return False
        
        try:
            # Configure ngrok with auth token if provided
            if self.auth_token:
                logger.info(f"Configuring ngrok with auth token")
                ngrok.set_auth_token(self.auth_token)
            else:
                logger.warning("No ngrok auth token provided - connection may be limited")
            
            # Set region
            conf.get_default().region = self.region
            logger.info(f"Using ngrok region: {self.region}")
            
            # List tunnels before connecting to check for existing connections
            existing_tunnels = ngrok.get_tunnels()
            if existing_tunnels:
                logger.info(f"Found {len(existing_tunnels)} existing tunnels, closing them...")
                for tunnel in existing_tunnels:
                    ngrok.disconnect(tunnel.public_url)
            
            # Start tunnel to the web server port
            logger.info(f"Starting ngrok tunnel to port {self.port}...")
            self.tunnel = ngrok.connect(self.port, "http")
            self.public_url = self.tunnel.public_url
            logger.info(f"Ngrok tunnel established: {self.public_url}")
            
            # Start monitoring thread
            self.running = True
            self.status_thread = Thread(target=self._monitor_status, daemon=True)
            self.status_thread.start()
            
            return True
        except Exception as e:
            logger.error(f"Failed to start ngrok tunnel: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())  # Log full stack trace
            return False
    
    def stop(self):
        """Stop the ngrok tunnel"""
        if not NGROK_AVAILABLE or not self.tunnel:
            return
        
        try:
            self.running = False
            ngrok.disconnect(self.tunnel.public_url)
            logger.info("Ngrok tunnel closed")
        except Exception as e:
            logger.error(f"Error closing ngrok tunnel: {str(e)}")
    
    def _monitor_status(self):
        """Monitor ngrok tunnel status in background thread"""
        while self.running:
            try:
                # Get current tunnels
                tunnels = ngrok.get_tunnels()
                if not tunnels and self.tunnel:
                    logger.warning("Ngrok tunnel appears to be down. Attempting to restart...")
                    self.stop()
                    time.sleep(1)
                    self.start()
            except Exception as e:
                logger.error(f"Error monitoring ngrok tunnel: {str(e)}")
            
            # Check every 30 seconds
            time.sleep(30)

def check_ngrok_installed():
    """Check if ngrok is installed on the system"""
    if NGROK_AVAILABLE:
        return True
    else:
        return False

def get_ngrok_version():
    """Get the installed ngrok version"""
    if not NGROK_AVAILABLE:
        return None
    
    try:
        version = ngrok.get_ngrok_version()
        return version
    except:
        return "Unknown"
