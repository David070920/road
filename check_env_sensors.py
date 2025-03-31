#!/usr/bin/env python3
"""
Quick test script for the environmental sensors (AHT21 and BMX280)
Run this script to verify the sensors are working correctly
"""

import sys
import os
import time
import logging

# Add the project root to the Python path
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from quality.config import Config
from quality.hardware import initialize_i2c, initialize_aht21, initialize_bmx280
from quality.io import read_aht21_data, read_bmx280_data, read_bmx280_calibration
from quality.core.context_managers import i2c_bus_context

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CheckSensors")

def main():
    """Test the environmental sensors"""
    print("-" * 60)
    print("Environmental Sensors Test Script")
    print("-" * 60)
    
    config = Config()
    
    # Initialize I2C
    print("\nInitializing I2C bus...")
    i2c_bus = initialize_i2c()
    if not i2c_bus:
        print("❌ Failed to initialize I2C bus. Exiting.")
        return 1
    
    print("✅ I2C bus initialized successfully")
    
    # Use context manager for I2C bus
    with i2c_bus_context(i2c_bus) as bus:
        # Test AHT21 temperature/humidity sensor
        print("\nTesting AHT21 temperature and humidity sensor...")
        aht21_result = initialize_aht21(bus, config)
        
        if aht21_result:
            print("✅ AHT21 sensor initialized successfully")
            
            # Read data from AHT21
            print("Reading temperature and humidity data...")
            
            for i in range(3):  # Try 3 readings
                aht21_data = read_aht21_data(bus, config)
                if aht21_data:
                    print(f"   Reading #{i+1}: Temperature: {aht21_data['temperature']}°C, "
                          f"Humidity: {aht21_data['humidity']}%")
                else:
                    print(f"   Reading #{i+1}: Failed to read data")
                time.sleep(1)
        else:
            print("❌ Failed to initialize AHT21 sensor")
        
        # Test BMX280 pressure/temperature sensor
        print("\nTesting BMX280 pressure and temperature sensor...")
        bmx280_result = initialize_bmx280(bus, config)
        
        if bmx280_result:
            print("✅ BMX280 sensor initialized successfully")
            
            # Read calibration data
            print("Reading calibration data...")
            calibration = read_bmx280_calibration(bus, config)
            
            if calibration:
                print("✅ Calibration data read successfully")
                
                # Read data from BMX280
                print("Reading temperature and pressure data...")
                
                for i in range(3):  # Try 3 readings
                    bmx280_data = read_bmx280_data(bus, config, calibration)
                    if bmx280_data:
                        print(f"   Reading #{i+1}: Temperature: {bmx280_data['temperature']}°C, "
                              f"Pressure: {bmx280_data['pressure']} hPa")
                        
                        # Calculate approximate altitude
                        p0 = 1013.25  # Standard sea level pressure in hPa
                        altitude = 44330 * (1 - (bmx280_data['pressure'] / p0) ** (1/5.255))
                        print(f"   Estimated altitude: {altitude:.1f} meters")
                    else:
                        print(f"   Reading #{i+1}: Failed to read data")
                    time.sleep(1)
            else:
                print("❌ Failed to read calibration data")
        else:
            print("❌ Failed to initialize BMX280 sensor")
    
    print("\nTest completed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
