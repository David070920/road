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
    from pyngrok.exception import PyngrokError
    NGROK_AVAILABLE = True
except ImportError:
    logger.warning("pyngrok not installed. Remote access via ngrok will not be available.")
    NGROK_AVAILABLE = False

class NgrokTunnel:
    def __init__(self, port=8080, auth_token=None, region='us', tunnel_type='http'):
        """Initialize an ngrok tunnel configuration"""
        self.port = port
        self.auth_token = auth_token
        self.region = region
        self.tunnel_type = tunnel_type
        self.process = None
        self.public_url = None
        self.tunnel = None
        self._monitor_thread = None
        
        # Configure ngrok if token is provided
        if auth_token:
            try:
                conf.get_default().auth_token = auth_token
                logger.info("Ngrok configured with auth token")
            except Exception as e:
                logger.error(f"Failed to configure ngrok with auth token: {e}")
        
        logger.debug(f"NgrokTunnel initialized for port {port}")
    
    def start(self):
        """Start the ngrok tunnel"""
        if not NGROK_AVAILABLE:
            logger.error("Ngrok is not available. Install pyngrok first.")
            return False
            
        try:
            # Kill any existing tunnels first
            ngrok.kill()
            
            # Set region if specified
            if self.region:
                conf.get_default().region = self.region
            
            # Start a new tunnel
            logger.info(f"Starting {self.tunnel_type} tunnel on port {self.port}...")
            self.tunnel = ngrok.connect(self.port, self.tunnel_type)
            self.public_url = self.tunnel.public_url
            
            # Start monitor thread
            self._monitor_thread = Thread(target=self._monitor_tunnel, daemon=True)
            self._monitor_thread.start()
            
            # Check if tunnel is actually working
            self._verify_tunnel()
            
            return True
        except PyngrokError as e:
            logger.error(f"Pyngrok error starting tunnel: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error starting ngrok tunnel: {e}")
            return False
    
    def _verify_tunnel(self):
        """Verify that the tunnel is actually working by making a test request"""
        try:
            import urllib.request
            import urllib.error
            
            # Wait a moment for the tunnel to be fully established
            time.sleep(1)
            
            # Try to connect to the public URL
            with urllib.request.urlopen(self.public_url, timeout=5) as response:
                if response.status == 200:
                    logger.info("Ngrok tunnel verified and working correctly")
                else:
                    logger.warning(f"Ngrok tunnel returned status {response.status}")
        except urllib.error.URLError as e:
            logger.warning(f"Could not verify ngrok tunnel: {e}")
        except Exception as e:
            logger.warning(f"Error verifying ngrok tunnel: {e}")
    
    def _monitor_tunnel(self):
        """Monitor the tunnel and log any issues"""
        while self.tunnel:
            try:
                time.sleep(30)  # Check every 30 seconds
                
                # Verify tunnel is still up
                tunnels = ngrok.get_tunnels()
                if not tunnels or self.public_url not in [t.public_url for t in tunnels]:
                    logger.warning("Ngrok tunnel appears to be down")
                    # Attempt to restart if down
                    self.start()
            except Exception as e:
                logger.error(f"Error monitoring ngrok tunnel: {e}")
            
    def stop(self):
        """Stop the ngrok tunnel"""
        if not NGROK_AVAILABLE:
            return
            
        try:
            if self.tunnel:
                logger.info("Stopping ngrok tunnel...")
                ngrok.disconnect(self.public_url)
                ngrok.kill()
                self.tunnel = None
                self.public_url = None
                logger.info("Ngrok tunnel stopped")
        except Exception as e:
            logger.error(f"Error stopping ngrok tunnel: {e}")
            # Force kill if we had an error
            try:
                ngrok.kill()
            except:
                pass

def check_ngrok_installed():
    """Check if ngrok is installed on the system"""
    if not NGROK_AVAILABLE:
        return False
        
    try:
        # Version-compatible check for ngrok installation
        # Different versions of pyngrok have different APIs
        try:
            # Newer versions
            if hasattr(ngrok, 'get_ngrok_path'):
                return ngrok.get_ngrok_path() is not None
            # Older versions
            elif hasattr(conf.get_default(), 'ngrok_path'):
                return conf.get_default().ngrok_path is not None
            # Check if we can get tunnels as another approach
            else:
                ngrok.get_tunnels()  # If this works, ngrok is installed
                return True
        except:
            # Try another approach - if connect works, ngrok is installed
            test_tunnel = ngrok.connect(5000, "http", options={"bind_tls": True})
            ngrok.disconnect(test_tunnel.public_url)
            return True
    except Exception as e:
        logger.error(f"Error checking ngrok installation: {e}")
        return False

def get_ngrok_version():
    """Get the installed ngrok version"""
    if not NGROK_AVAILABLE:
        return "Not installed"
        
    try:
        # Try to find ngrok path in different ways for compatibility
        ngrok_path = None
        
        # Try different approaches based on pyngrok version
        if hasattr(ngrok, 'get_ngrok_path'):
            ngrok_path = ngrok.get_ngrok_path()
        elif hasattr(conf.get_default(), 'ngrok_path'):
            ngrok_path = conf.get_default().ngrok_path
        
        if ngrok_path and os.path.exists(ngrok_path):
            result = subprocess.run([ngrok_path, "version"], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE,
                                   text=True)
            return result.stdout.strip()
        else:
            # If we can't get the path, just return a generic message
            return "Unknown (but installed)"
    except Exception as e:
        logger.error(f"Error getting ngrok version: {e}")
        return "Error"
