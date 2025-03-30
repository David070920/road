#!/usr/bin/env python3
"""
Road Quality Measurement System
------------------------------
A system for measuring road quality using LiDAR, accelerometer, and GPS sensors.
"""

import sys
import os
import logging
from quality import SensorFusion

def main():
    """Main entry point for the road quality measurement system."""
    # Set up logging to file and console
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "road_quality.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Road Quality Measurement System")
    
    try:
        # Create and run the sensor fusion system
        sensor_fusion = SensorFusion()
        sensor_fusion.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
    finally:
        logger.info("Road Quality Measurement System shutdown complete")

if __name__ == "__main__":
    main()
