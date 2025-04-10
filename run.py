#!/usr/bin/env python3
"""
Road Quality Measurement System
------------------------------
A system for measuring road quality using LiDAR, accelerometer, and GPS sensors.
"""

import sys
import quality.config as config
from quality.visualization.plot_setup import setup_visualization
import os
import logging
import traceback
import faulthandler
from quality import SensorFusion

# Enable faulthandler to help debug segmentation faults
faulthandler.enable()

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
    
    # Conditionally set environment variables based on visualization config
    if not getattr(config, 'ENABLE_VISUALIZATION', False):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["MPLBACKEND"] = "Agg"
    
    try:
        # Create the sensor fusion system
        sensor_fusion = SensorFusion(safe_mode=False)

        # If visualization is enabled, start it
        if getattr(config, 'ENABLE_VISUALIZATION', False):
            setup_visualization(
                sensor_fusion.lidar_data,
                sensor_fusion.lidar_data_lock,
                sensor_fusion.accel_data,
                sensor_fusion.accel_data_lock,
                config,
                analyzer=sensor_fusion.analyzer,
                analysis_lock=sensor_fusion.analysis_lock
            )
        else:
            # Run headless mode
            sensor_fusion.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
    finally:
        logger.info("Road Quality Measurement System shutdown complete")

if __name__ == "__main__":
    main()

    # If visualization is enabled, block with plt.show()
    if getattr(config, 'ENABLE_VISUALIZATION', False):
        import matplotlib.pyplot as plt
        # Block until all plot windows are closed
        plt.show(block=True)
