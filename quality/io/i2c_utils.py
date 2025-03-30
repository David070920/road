import time
import logging

logger = logging.getLogger("SensorFusion")

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

def read_word(i2c_bus, addr, reg):
    """Read a word from the I2C device"""
    high = read_byte(i2c_bus, addr, reg)
    low = read_byte(i2c_bus, addr, reg + 1)
    if high is not None and low is not None:
        val = (high << 8) + low
        return val
    else:
        return None

def read_word_2c(i2c_bus, addr, reg):
    """Read a 2's complement word from the I2C device"""
    val = read_word(i2c_bus, addr, reg)
    if val is not None:
        if val >= 0x8000:
            return -((65535 - val) + 1)
        else:
            return val
    else:
        return None

def get_accel_data(i2c_bus, config):
    """Get accelerometer data from ICM20948"""
    accel_z = read_word_2c(i2c_bus, config.ICM20948_ADDRESS, config.ICM20948_ACCEL_ZOUT_H)
    if accel_z is not None:
        return accel_z / 16384.0  # Convert to g
    return None
