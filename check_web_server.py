#!/usr/bin/env python3
"""
Tool to diagnose web server issues by checking port availability and dependencies
"""
import sys
import os
import socket
import logging
import subprocess
import importlib

# Add the project root to the Python path
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("WebServerDiagnostic")

def check_port_availability(host, port):
    """Check if a port is available on the specified host"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)  # 2-second timeout
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            logger.error(f"Port {port} is already in use on {host}")
            return False
        else:
            logger.info(f"Port {port} is available on {host}")
            return True
    except Exception as e:
        logger.error(f"Error checking port {port}: {e}")
        return False

def check_dependencies():
    """Check if all required packages for the web server are installed"""
    required_packages = [
        "flask", "flask_socketio", "eventlet", "gevent", "werkzeug"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            importlib.import_module(package)
            logger.info(f"✅ {package} is installed")
        except ImportError:
            logger.error(f"❌ {package} is NOT installed")
            missing_packages.append(package)
    
    return missing_packages

def check_network_interfaces():
    """Check available network interfaces"""
    try:
        import netifaces
        interfaces = netifaces.interfaces()
        
        logger.info(f"Network interfaces: {interfaces}")
        
        for interface in interfaces:
            addresses = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addresses:
                for address in addresses[netifaces.AF_INET]:
                    logger.info(f"Interface {interface}: {address['addr']}")
    except ImportError:
        logger.warning("netifaces package not installed, skipping interface check")
        logger.info("To install: pip install netifaces")
    except Exception as e:
        logger.error(f"Error checking network interfaces: {e}")

def main():
    """Run diagnostic tests for the web server"""
    print("\n" + "=" * 60)
    print(" Web Server Diagnostic Tool ")
    print("=" * 60 + "\n")
    
    # Test port availability
    print("\nChecking port availability...")
    from quality.config import Config
    config = Config()
    check_port_availability(getattr(config, 'WEB_SERVER_HOST', '0.0.0.0'), 
                           getattr(config, 'WEB_SERVER_PORT', 8080))
    
    # Check dependencies
    print("\nChecking required dependencies...")
    missing_packages = check_dependencies()
    if missing_packages:
        print(f"\nMissing packages: {', '.join(missing_packages)}")
        print("To install missing packages, run:")
        print(f"pip install {' '.join(missing_packages)}")
    else:
        print("\nAll required packages are installed!")
    
    # Check network interfaces
    print("\nChecking network interfaces...")
    check_network_interfaces()
    
    print("\nDiagnostic complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
