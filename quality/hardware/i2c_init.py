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

def initialize_aht21(i2c_bus, config):
    """Initialize the AHT21 temperature and humidity sensor with improved reliability"""
    try:
        # Try to read a byte to verify device exists
        try:
            i2c_bus.read_byte(config.AHT21_ADDRESS)
            logger.info(f"AHT21 found at address 0x{config.AHT21_ADDRESS:02x}")
        except:
            logger.error(f"AHT21 not found at address 0x{config.AHT21_ADDRESS:02x}")
            return False
        
        # Reset the sensor first to clear any previous state
        i2c_bus.write_byte(config.AHT21_ADDRESS, config.AHT21_RESET_COMMAND)
        time.sleep(0.04)  # 40ms wait time after reset (doubled for reliability)
        
        # Initialize sensor
        i2c_bus.write_i2c_block_data(config.AHT21_ADDRESS, 
                                     config.AHT21_INIT_COMMAND[0], 
                                     config.AHT21_INIT_COMMAND[1:])
        time.sleep(0.04)  # 40ms wait time (doubled for reliability)
        
        # Verify initialization by reading status
        status = i2c_bus.read_byte(config.AHT21_ADDRESS)
        
        # Bit 3 (Calibrated bit) should be set if initialized correctly
        if status & 0x08:
            logger.info("AHT21 sensor initialized successfully (calibration bit set)")
            return True
        else:
            logger.warning("AHT21 sensor initialization may have failed (calibration bit not set)")
            # Try once more
            i2c_bus.write_i2c_block_data(config.AHT21_ADDRESS, 
                                        config.AHT21_INIT_COMMAND[0], 
                                        config.AHT21_INIT_COMMAND[1:])
            time.sleep(0.04)
            return True
    except Exception as e:
        logger.error(f"Failed to initialize AHT21 sensor: {e}")
        return False

def initialize_bmx280(i2c_bus, config):
    """Initialize the BMX280 pressure and temperature sensor"""
    try:
        # Try to check the device ID to verify it's a BMx280
        chip_id = read_byte(i2c_bus, config.BMX280_ADDRESS, 0xD0)
        
        if chip_id in [0x58, 0x60]:
            logger.info(f"BMx280 found at address 0x{config.BMX280_ADDRESS:02x}, chip ID: 0x{chip_id:02x}")
            
            # Reset the sensor
            i2c_bus.write_byte_data(config.BMX280_ADDRESS, 
                                    config.BMX280_RESET_REGISTER, 
                                    config.BMX280_RESET_VALUE)
            time.sleep(0.005)  # 5ms wait time after reset
            
            # Configure sensor - set oversampling and mode
            # Set ctrl_meas register (0xF4)
            # Bits 7-5: temperature oversampling (010 = x2)
            # Bits 4-2: pressure oversampling (101 = x16)
            # Bits 1-0: mode (11 = normal mode)
            i2c_bus.write_byte_data(config.BMX280_ADDRESS, 
                                    config.BMX280_CTRL_MEAS_REGISTER, 
                                    0b01010111)
            
            # Set config register (0xF5)
            # Bits 7-5: standby time (100 = 500ms)
            # Bits 4-2: filter setting (010 = 4x filter)
            # Bits 1-0: unused
            i2c_bus.write_byte_data(config.BMX280_ADDRESS, 
                                    config.BMX280_CONFIG_REGISTER, 
                                    0b10001000)
            
            time.sleep(0.05)  # 50ms wait for sensor to stabilize
            
            logger.info("BMx280 sensor initialized successfully")
            return True
        else:
            logger.error(f"Unknown chip ID for BMx280: 0x{chip_id:02x}")
            return False
    except Exception as e:
        logger.error(f"Failed to initialize BMx280 sensor: {e}")
        return False
