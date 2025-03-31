import time
import logging
import struct

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

def read_aht21_data(i2c_bus, config):
    """Read temperature and humidity data from AHT21 sensor"""
    try:
        # Send measurement command
        i2c_bus.write_i2c_block_data(config.AHT21_ADDRESS, 
                                     config.AHT21_MEASURE_COMMAND[0],
                                     config.AHT21_MEASURE_COMMAND[1:])
        
        # Wait for measurement to complete (80ms typical)
        time.sleep(0.08)
        
        # Read 6 bytes of data
        data = i2c_bus.read_i2c_block_data(config.AHT21_ADDRESS, 0, 6)
        
        # Check status bit (bit 7 of the first byte)
        if (data[0] & 0x80):
            logger.warning("AHT21 sensor busy or in command mode")
            return None
        
        # Calculate humidity and temperature
        # Humidity is in the bits 16-39 (3 bytes starting from second byte)
        # Temperature is in the bits 40-59 (2.5 bytes at the end)
        
        # Extract humidity (20 bits)
        humidity_raw = ((data[1] << 16) | (data[2] << 8) | data[3]) >> 4
        humidity = (humidity_raw / 1048576.0) * 100  # Convert to percentage
        
        # Extract temperature (20 bits)
        temp_raw = ((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]
        temperature = (temp_raw / 1048576.0) * 200 - 50  # Convert to Celsius
        
        return {
            'temperature': round(temperature, 1),
            'humidity': round(humidity, 1)
        }
    except Exception as e:
        logger.error(f"Error reading AHT21 data: {e}")
        return None

def read_bmx280_calibration(i2c_bus, config):
    """Read calibration data from BMX280 sensor"""
    try:
        # Read calibration data - 24 bytes starting at register 0x88
        cal_data = i2c_bus.read_i2c_block_data(config.BMX280_ADDRESS, config.BMX280_CALIB_REGISTER, 24)
        
        # Create a dictionary to store calibration values
        calibration = {}
        
        # Temperature calibration values (16-bit signed/unsigned)
        calibration['dig_T1'] = cal_data[0] | (cal_data[1] << 8)  # unsigned
        temp = cal_data[2] | (cal_data[3] << 8)  # signed
        calibration['dig_T2'] = struct.unpack('h', struct.pack('H', temp))[0]
        temp = cal_data[4] | (cal_data[5] << 8)  # signed
        calibration['dig_T3'] = struct.unpack('h', struct.pack('H', temp))[0]
        
        # Pressure calibration values (16-bit signed/unsigned)
        calibration['dig_P1'] = cal_data[6] | (cal_data[7] << 8)  # unsigned
        temp = cal_data[8] | (cal_data[9] << 8)  # signed
        calibration['dig_P2'] = struct.unpack('h', struct.pack('H', temp))[0]
        temp = cal_data[10] | (cal_data[11] << 8)  # signed
        calibration['dig_P3'] = struct.unpack('h', struct.pack('H', temp))[0]
        temp = cal_data[12] | (cal_data[13] << 8)  # signed
        calibration['dig_P4'] = struct.unpack('h', struct.pack('H', temp))[0]
        temp = cal_data[14] | (cal_data[15] << 8)  # signed
        calibration['dig_P5'] = struct.unpack('h', struct.pack('H', temp))[0]
        temp = cal_data[16] | (cal_data[17] << 8)  # signed
        calibration['dig_P6'] = struct.unpack('h', struct.pack('H', temp))[0]
        temp = cal_data[18] | (cal_data[19] << 8)  # signed
        calibration['dig_P7'] = struct.unpack('h', struct.pack('H', temp))[0]
        temp = cal_data[20] | (cal_data[21] << 8)  # signed
        calibration['dig_P8'] = struct.unpack('h', struct.pack('H', temp))[0]
        temp = cal_data[22] | (cal_data[23] << 8)  # signed
        calibration['dig_P9'] = struct.unpack('h', struct.pack('H', temp))[0]
        
        return calibration
    except Exception as e:
        logger.error(f"Error reading BMX280 calibration data: {e}")
        return None

def calculate_temperature(raw_temp, calibration):
    """Calculate temperature from BMX280 raw value and calibration data"""
    # Algorithm from BME280 datasheet
    var1 = (raw_temp / 16384.0 - calibration['dig_T1'] / 1024.0) * calibration['dig_T2']
    var2 = ((raw_temp / 131072.0 - calibration['dig_T1'] / 8192.0) * 
            (raw_temp / 131072.0 - calibration['dig_T1'] / 8192.0) * calibration['dig_T3'])
    t_fine = var1 + var2
    temperature = t_fine / 5120.0
    
    return temperature, t_fine

def calculate_pressure(raw_pressure, t_fine, calibration):
    """Calculate pressure from BMX280 raw value and calibration data"""
    # Algorithm from BME280 datasheet
    var1 = (t_fine / 2.0) - 64000.0
    var2 = var1 * var1 * calibration['dig_P6'] / 32768.0
    var2 = var2 + var1 * calibration['dig_P5'] * 2.0
    var2 = (var2 / 4.0) + (calibration['dig_P4'] * 65536.0)
    var1 = (calibration['dig_P3'] * var1 * var1 / 524288.0 + 
            calibration['dig_P2'] * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * calibration['dig_P1']
    
    # Avoid division by zero
    if var1 == 0:
        return 0
        
    p = 1048576.0 - raw_pressure
    p = (p - (var2 / 4096.0)) * 6250.0 / var1
    var1 = calibration['dig_P9'] * p * p / 2147483648.0
    var2 = p * calibration['dig_P8'] / 32768.0
    p = p + (var1 + var2 + calibration['dig_P7']) / 16.0
    
    # Convert to hPa (millibar)
    p = p / 100.0
    
    return p

def read_bmx280_data(i2c_bus, config, calibration=None):
    """Read temperature and pressure data from BMX280 sensor"""
    try:
        # Get calibration data if not provided
        if calibration is None:
            calibration = read_bmx280_calibration(i2c_bus, config)
            if calibration is None:
                return None
                
        # Read raw pressure and temperature data
        # Pressure: 3 bytes starting at register 0xF7
        # Temperature: 3 bytes starting at register 0xFA
        data = i2c_bus.read_i2c_block_data(config.BMX280_ADDRESS, config.BMX280_PRESSURE_REGISTER, 6)
        
        # Extract pressure (20 bits)
        pressure_raw = ((data[0] << 16) | (data[1] << 8) | data[2]) >> 4
        
        # Extract temperature (20 bits)
        temp_raw = ((data[3] << 16) | (data[4] << 8) | data[5]) >> 4
        
        # Calculate temperature and pressure
        temperature, t_fine = calculate_temperature(temp_raw, calibration)
        pressure = calculate_pressure(pressure_raw, t_fine, calibration)
        
        return {
            'temperature': round(temperature, 1),
            'pressure': round(pressure, 1)
        }
    except Exception as e:
        logger.error(f"Error reading BMX280 data: {e}")
        return None
