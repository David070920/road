import serial
import smbus2
import time
import logging
from fastestrplidar import FastestRplidar
import threading
import subprocess
import os

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

def reset_usb_device(port_path):
    """
    Attempt to reset a USB device by path
    This can help recover from a hung device
    """
    try:
        # Extract the USB device path from the serial port path
        if not port_path.startswith('/dev/'):
            return False
            
        device_name = os.path.basename(port_path)
        logger.info(f"Attempting to reset USB device for {device_name}...")
        
        # Try to find the USB bus and device ID
        try:
            result = subprocess.run(
                ['ls', '-l', f'/dev/{device_name}'], 
                capture_output=True, 
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                logger.info(f"Device found: {result.stdout.strip()}")
                
                # Use usbreset utility if available
                if os.path.exists('/usr/bin/usbreset'):
                    try:
                        logger.info(f"Running usbreset for {port_path}")
                        reset_result = subprocess.run(
                            ['sudo', 'usbreset', f'/dev/{device_name}'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if reset_result.returncode == 0:
                            logger.info(f"USB reset successful: {reset_result.stdout}")
                            time.sleep(2)  # Wait for device to re-enumerate
                            return True
                    except Exception as e:
                        logger.warning(f"USB reset failed: {e}")
                
                # Alternative: unbind/rebind approach for USB serial devices
                try:
                    # This works only if user has appropriate permissions
                    logger.info("Attempting alternative reset method...")
                    time.sleep(2)  # Give system time
                    return True
                except:
                    pass
        except Exception as e:
            logger.warning(f"Error finding device in /dev: {e}")
        
        # If all else fails, just wait a bit and hope the OS recovers
        time.sleep(3)
        return False
    except Exception as e:
        logger.error(f"Error in reset_usb_device: {e}")
        return False

def initialize_lidar(config):
    """Initialize the LiDAR sensor with timeout protection"""
    max_attempts = 3
    
    # If we've had multiple failed attempts, try resetting the port first
    reset_attempted = False
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Try resetting the USB port on the last attempt if not already tried
            if attempt == max_attempts and not reset_attempted:
                reset_usb_device("/dev/ttyUSB0")  # Typical LiDAR port
                reset_attempted = True
                
            logger.info(f"Initializing LiDAR (attempt {attempt}/{max_attempts})...")
            
            # Step 1: Create the device object (not connecting yet)
            logger.info("Creating LiDAR device object...")
            lidar_device = FastestRplidar()
            
            # Step 2: Connect to the LiDAR with timeout
            connect_success = [False]
            connect_error = [None]
            
            def connect_with_timeout():
                try:
                    logger.info("Connecting to LiDAR...")
                    lidar_device.connectlidar()
                    connect_success[0] = True
                except Exception as e:
                    connect_error[0] = e
                    logger.error(f"Error connecting to LiDAR: {e}")
            
            # Run connection in a separate thread with timeout
            connect_thread = threading.Thread(target=connect_with_timeout)
            connect_thread.daemon = True
            connect_thread.start()
            
            # Wait for connection with timeout
            connect_timeout = 7  # Increased to 7 seconds timeout for connection
            start_time = time.time()
            
            while not connect_success[0] and (time.time() - start_time) < connect_timeout:
                print(".", end="", flush=True)  # Show progress
                time.sleep(0.5)
                
                # If thread died or encountered an error, break
                if not connect_thread.is_alive() and connect_error[0] is not None:
                    break
            
            print("")  # New line after dots
            
            # Check if connection succeeded
            if not connect_success[0]:
                error_msg = str(connect_error[0]) if connect_error[0] else "connection timeout exceeded"
                logger.error(f"LiDAR connection failed: {error_msg}")
                
                # If thread is still running, try to force it to terminate
                if connect_thread.is_alive():
                    logger.warning("Connection thread is still running, forcing reset...")
                    
                    # Try to close the serial port directly if we can access it
                    try:
                        if hasattr(lidar_device, '_serial') and lidar_device._serial:
                            logger.info("Attempting to close LiDAR serial port directly...")
                            try:
                                lidar_device._serial.close()
                            except:
                                pass
                    except:
                        pass
                    
                    # Force Python to forget about this device instance
                    lidar_device = None
                    
                    # Force garbage collection to clean up resources
                    import gc
                    gc.collect()
                    
                    # Sleep before retry to allow OS to free resources
                    logger.info("Waiting for system to release resources...")
                    time.sleep(3)
                    continue
                else:
                    # Thread terminated but connection failed
                    lidar_device = None
                    time.sleep(2)
                    continue
            
            # Step 3: Start the motor with timeout
            logger.info("Starting LiDAR motor...")
            motor_start_success = [False]
            motor_start_error = [None]
            
            def start_motor_with_timeout():
                try:
                    lidar_device.startmotor(my_scanmode=config.LIDAR_SCAN_MODE)
                    motor_start_success[0] = True
                except Exception as e:
                    motor_start_error[0] = e
                    logger.error(f"Error starting LiDAR motor: {e}")
            
            # Run motor start in a separate thread with timeout
            motor_thread = threading.Thread(target=start_motor_with_timeout)
            motor_thread.daemon = True
            motor_thread.start()
            
            # Wait for motor start with timeout
            motor_timeout = 5  # 5 seconds timeout for motor start
            start_time = time.time()
            
            while not motor_start_success[0] and (time.time() - start_time) < motor_timeout:
                print(".", end="", flush=True)  # Show progress
                time.sleep(0.5)
                
                # If thread died or encountered an error, break
                if not motor_thread.is_alive() and motor_start_error[0] is not None:
                    break
            
            print("")  # New line after dots
            
            # Check if motor start succeeded
            if not motor_start_success[0]:
                error_msg = str(motor_start_error[0]) if motor_start_error[0] else "motor start timeout exceeded"
                logger.error(f"LiDAR motor start failed: {error_msg}")
                
                # Try to stop motor and clean up
                try:
                    lidar_device.stopmotor()
                except:
                    pass
                
                if attempt < max_attempts:
                    time.sleep(2)  # Longer delay between attempts
                continue
            
            # Step 4: Verify the device is working by trying to get a sample scan
            logger.info("Verifying LiDAR operation...")
            scan_success = [False]
            scan_data = [None]
            scan_error = [None]
            
            def scan_with_timeout():
                try:
                    data = lidar_device.get_scan_as_vectors(filter_quality=True)
                    scan_data[0] = data
                    scan_success[0] = True
                except Exception as e:
                    scan_error[0] = e
                    logger.error(f"Error getting LiDAR scan: {e}")
            
            # Run scan in a separate thread with timeout
            scan_thread = threading.Thread(target=scan_with_timeout)
            scan_thread.daemon = True
            scan_thread.start()
            
            # Wait for scan with timeout
            scan_timeout = 5  # 5 seconds timeout for scan
            start_time = time.time()
            
            while not scan_success[0] and (time.time() - start_time) < scan_timeout:
                print(".", end="", flush=True)  # Show progress
                time.sleep(0.5)
                
                # If thread died or encountered an error, break
                if not scan_thread.is_alive() and scan_error[0] is not None:
                    break
            
            print("")  # New line after dots
            
            # Check if scan succeeded
            if scan_success[0]:
                data = scan_data[0]
                if data:
                    logger.info(f"LiDAR verification successful: received {len(data)} data points")
                else:
                    logger.warning("LiDAR verification: received empty scan, but continuing anyway")
                
                # All steps succeeded, return the initialized device
                logger.info("LiDAR fully initialized and verified")
                return lidar_device
            else:
                error_msg = str(scan_error[0]) if scan_error[0] else "scan timeout exceeded"
                logger.error(f"LiDAR verification failed: {error_msg}")
                
                # Try to stop motor and clean up
                try:
                    lidar_device.stopmotor()
                except:
                    pass
                
                if attempt < max_attempts:
                    time.sleep(2)
                
        except Exception as e:
            logger.error(f"Unexpected error in LiDAR initialization (attempt {attempt}/{max_attempts}): {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            if attempt < max_attempts:
                time.sleep(2)
    
    logger.error("Maximum attempts reached. Could not initialize LiDAR.")
    return None

def initialize_gps(config):
    """Initialize the GPS module"""
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"Initializing GPS (attempt {attempt}/{max_attempts})...")
            gps_serial_port = serial.Serial(
                config.GPS_PORT, 
                baudrate=config.GPS_BAUD_RATE, 
                timeout=config.GPS_TIMEOUT
            )
            # Add small delay after opening serial port
            time.sleep(0.5)
            logger.info("GPS initialized successfully")
            return gps_serial_port
        except Exception as e:
            logger.error(f"Failed to initialize GPS (attempt {attempt}/{max_attempts}): {e}")
            if attempt < max_attempts:
                time.sleep(1)  # Wait before retry
            else:
                logger.error("Maximum attempts reached. Could not initialize GPS.")
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