import logging
from fastestrplidar import FastestRplidar

logger = logging.getLogger("SensorFusion")

def initialize_lidar(config):
    """Initialize the LiDAR sensor"""
    try:
        lidar_device = FastestRplidar()
        lidar_device.connectlidar()
        lidar_device.startmotor(my_scanmode=config.LIDAR_SCAN_MODE)
        logger.debug("LiDAR initialized successfully - no calibration needed")
        return lidar_device
    except Exception as e:
        logger.error(f"Failed to initialize LiDAR: {e}")
        return None
