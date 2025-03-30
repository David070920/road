import logging
from contextlib import contextmanager

logger = logging.getLogger("SensorFusion")

@contextmanager
def lidar_device_context(device):
    """Context manager for LiDAR device to ensure proper cleanup"""
    try:
        yield device
    finally:
        if device:
            try:
                device.stopmotor()
                logger.info("LiDAR motor stopped")
            except Exception as e:
                logger.error(f"Error stopping LiDAR motor: {e}")

@contextmanager
def serial_port_context(port):
    """Context manager for serial port to ensure proper closure"""
    try:
        yield port
    finally:
        if port:
            try:
                port.close()
                logger.info("Serial port closed")
            except Exception as e:
                logger.error(f"Error closing serial port: {e}")

@contextmanager
def i2c_bus_context(bus):
    """Context manager for I2C bus to ensure proper closure"""
    try:
        yield bus
    finally:
        if bus:
            try:
                bus.close()
                logger.info("I2C bus closed")
            except Exception as e:
                logger.error(f"Error closing I2C bus: {e}")
