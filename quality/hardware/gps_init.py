# import serial # No longer needed for network GPS
import logging

logger = logging.getLogger("SensorFusion")

def initialize_gps(config):
    """
    Initialize the GPS module.
    For network GPS, this function no longer initializes a serial port.
    It can be used for other GPS-related setup if needed in the future.
    """
    logger.info("Physical GPS initialization skipped (using Network GPS).")
    # No serial port is initialized for network GPS.
    # The function now effectively does nothing in terms of hardware setup for GPS.
    # It's kept for structural consistency or if other non-hardware GPS setup is needed.
    return None # Return None as no serial port object is created.
