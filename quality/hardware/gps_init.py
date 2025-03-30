import serial
import logging

logger = logging.getLogger("SensorFusion")

def initialize_gps(config):
    """Initialize the GPS module"""
    try:
        gps_serial_port = serial.Serial(
            config.GPS_PORT, 
            baudrate=config.GPS_BAUD_RATE, 
            timeout=config.GPS_TIMEOUT
        )
        logger.info("GPS initialized successfully")
        return gps_serial_port
    except Exception as e:
        logger.error(f"Failed to initialize GPS: {e}")
        return None
