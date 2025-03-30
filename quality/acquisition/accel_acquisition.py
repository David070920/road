import time
import logging
from ..io.i2c_utils import get_accel_data

logger = logging.getLogger("SensorFusion")

def accel_thread_func(i2c_bus, accel_data_lock, accel_data, stop_event, config):
    """Thread function for accelerometer data acquisition"""
    logger.info("Accelerometer thread started")
    while not stop_event.is_set():
        try:
            # Get accelerometer data
            accel_z = get_accel_data(i2c_bus, config)
            
            if accel_z is not None:
                # Update shared data with lock
                with accel_data_lock:
                    accel_data.append(accel_z)
                
                logger.debug(f"Accelerometer: Z={accel_z:.2f}g")
                
        except Exception as e:
            logger.error(f"Error in accelerometer thread: {e}")
            
        # Sleep to prevent high CPU usage
        time.sleep(0.1)
        
    logger.info("Accelerometer thread stopped")
