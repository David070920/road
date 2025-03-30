import smbus2
import time
import logging

logger = logging.getLogger("SensorFusion")

def initialize_i2c():
    """Initialize the I2C bus"""
    try:
        i2c_bus = smbus2.SMBus(1)
        time.sleep(0.1)
        return i2c_bus
    except Exception as e:
        logger.error(f"Failed to initialize I2C: {e}")
        return None

def initialize_icm20948(i2c_bus, config):
    """Initialize the ICM20948 accelerometer"""
    try:
        who_am_i = read_byte(i2c_bus, config.ICM20948_ADDRESS, config.ICM20948_WHO_AM_I)
        
        if who_am_i == 0xEA:
            logger.info(f"ICM20948 found at address 0x{config.ICM20948_ADDRESS:02x}")
            # Wake up the sensor (clear sleep mode)
            i2c_bus.write_byte_data(
                config.ICM20948_ADDRESS, 
                config.ICM20948_PWR_MGMT_1, 
                0x00
            )
            time.sleep(0.1)
            return True
        else:
            logger.error(f"ICM20948 WHO_AM_I register mismatch. Expected 0xEA, got {who_am_i}")
            return False
    except Exception as e:
        logger.error(f"Failed to initialize ICM20948: {e}")
        return False

def read_byte(i2c_bus, addr, reg):
    """Read a byte from the I2C device"""
    retries = 3
    for _ in range(retries):
        try:
            return i2c_bus.read_byte_data(addr, reg)
        except Exception as e:
            logger.debug(f"Error reading byte from address 0x{addr:02x}, register 0x{reg:02x}: {e}")
            time.sleep(0.01)
    logger.warning(f"Failed to read from address 0x{addr:02x}, register 0x{reg:02x} after {retries} retries")
    return None
