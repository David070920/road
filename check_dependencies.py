#!/usr/bin/env python3
"""
Dependency checker for Road Quality Measurement System
This script checks if all required dependencies are installed
"""

import sys
import importlib.util
import subprocess
import os

def check_module(module_name, package_name=None):
    """Check if a Python module is installed"""
    if package_name is None:
        package_name = module_name
    
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        print(f"❌ {module_name} is not installed. Install it with: pip install {package_name}")
        return False
    else:
        print(f"✅ {module_name} is installed")
        return True

def main():
    """Check all dependencies required for the road quality system"""
    print("Checking dependencies for Road Quality Measurement System...\n")
    
    # System environment
    print(f"Python version: {sys.version}")
    print(f"Platform: {sys.platform}")
    
    # Check pip version
    try:
        pip_version = subprocess.check_output(["pip", "--version"]).decode().strip()
        print(f"pip version: {pip_version}")
    except:
        print("❌ pip not found in path")
    
    print("\nChecking required Python modules:")
    
    # Core dependencies
    all_installed = True
    all_installed &= check_module("numpy")
    all_installed &= check_module("matplotlib")
    all_installed &= check_module("scipy")
    
    # Hardware interface
    all_installed &= check_module("smbus2")
    all_installed &= check_module("fastestrplidar")
    all_installed &= check_module("serial")
    all_installed &= check_module("pynmea2")
    
    # Web and mapping
    all_installed &= check_module("flask")
    all_installed &= check_module("flask_socketio", "flask-socketio")
    all_installed &= check_module("folium")
    
    # Test if hardware is accessible
    print("\nChecking hardware accessibility:")
    
    # LiDAR device
    lidar_dev = "/dev/ttyUSB0"
    if os.path.exists(lidar_dev):
        print(f"✅ LiDAR device found at {lidar_dev}")
    else:
        print(f"❌ LiDAR device not found at {lidar_dev}")
        all_installed = False
    
    # I2C bus
    i2c_dev = "/dev/i2c-1"
    if os.path.exists(i2c_dev):
        print(f"✅ I2C bus found at {i2c_dev}")
    else:
        print(f"❌ I2C bus not found at {i2c_dev}")
        all_installed = False
    
    # GPS device
    gps_dev = "/dev/ttyACM0"
    if os.path.exists(gps_dev):
        print(f"✅ GPS device found at {gps_dev}")
    else:
        print(f"❌ GPS device not found at {gps_dev}")
        # Don't fail on missing GPS, just warn
        print("   Note: System can function without GPS")
    
    print("\nSummary:")
    if all_installed:
        print("✅ All critical dependencies are satisfied")
        print("✅ System should be ready to run")
        return 0
    else:
        print("❌ Some dependencies are missing")
        print("Please install missing dependencies and try again")
        return 1

if __name__ == "__main__":
    sys.exit(main())
