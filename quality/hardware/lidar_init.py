import logging
import time
import sys
import os

logger = logging.getLogger("SensorFusion")

def initialize_lidar(config):
    """Initialize the LiDAR sensor with enhanced error handling to prevent segmentation faults"""
    try:
        # Set a timeout for importing the potentially problematic module
        import signal
        
        # Define a timeout handler
        def timeout_handler(signum, frame):
            raise TimeoutError("LiDAR initialization timed out")
            
        # Set timeout for critical operations
        import threading
        if hasattr(signal, 'SIGALRM') and threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(5)  # 5 second timeout
        else:
            # Skip signal alarm setup in non-main thread
            pass
        
        # Import the C extension module with careful error handling
        try:
            from fastestrplidar import FastestRplidar
        except ImportError as e:
            logger.error(f"Failed to import FastestRplidar library: {e}")
            return None
        except Exception as e:
            logger.error(f"Unknown error importing FastestRplidar library: {e}")
            return None
        
        # Create LiDAR object instance
        try:
            lidar_device = FastestRplidar()
        except Exception as e:
            logger.error(f"Failed to create FastestRplidar instance: {e}")
            return None
        
        # Connect to the LiDAR device
        try:
            connect_result = lidar_device.connectlidar()
            if not connect_result and hasattr(lidar_device, 'is_connected') and not lidar_device.is_connected:
                logger.error("LiDAR connection failed")
                return None
        except Exception as e:
            logger.error(f"Failed to connect to LiDAR: {e}")
            return None
            
        # Start the LiDAR motor
        try:
            scan_mode = getattr(config, 'LIDAR_SCAN_MODE', 2)  # Default to mode 2 if not specified
            motor_result = lidar_device.startmotor(my_scanmode=scan_mode)
            if not motor_result and hasattr(lidar_device, 'is_motor_running') and not lidar_device.is_motor_running:
                logger.error("LiDAR motor failed to start")
                return None
                
            # Reset the alarm
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
                
            # Short delay to ensure the LiDAR is ready
            time.sleep(0.5)
            
            logger.debug("LiDAR initialized successfully - no calibration needed")
            return lidar_device
        except TimeoutError:
            logger.error("LiDAR initialization timed out")
            return None
        except Exception as e:
            logger.error(f"Failed to start LiDAR motor: {e}")
            return None
    except Exception as e:
        logger.error(f"Critical error in LiDAR initialization: {e}")
        return None
