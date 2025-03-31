import time
import logging
from ..io.i2c_utils import read_aht21_data, read_bmx280_data, read_bmx280_calibration

logger = logging.getLogger("SensorFusion")

def env_thread_func(i2c_bus, env_data_lock, env_data, stop_event, config):
    """Thread function for environmental sensors (AHT21 and BMX280) acquisition"""
    logger.debug("Environmental sensors thread started")
    
    # Read BMX280 calibration data once at startup
    bmx280_calibration = None
    try:
        bmx280_calibration = read_bmx280_calibration(i2c_bus, config)
        if bmx280_calibration:
            logger.debug("BMX280 calibration data read successfully")
        else:
            logger.warning("Failed to read BMX280 calibration data")
    except Exception as e:
        logger.error(f"Error reading BMX280 calibration data: {e}")
    
    # Time tracking for sensor update intervals
    last_update_time = 0
    
    while not stop_event.is_set():
        try:
            current_time = time.time()
            
            # Only update at specified interval to avoid unnecessary frequent readings
            if current_time - last_update_time >= config.ENV_UPDATE_INTERVAL:
                last_update_time = current_time
                
                # Read AHT21 temperature and humidity data
                aht21_data = read_aht21_data(i2c_bus, config)
                
                # Read BMX280 pressure and temperature data
                bmx280_data = read_bmx280_data(i2c_bus, config, bmx280_calibration)
                
                # Update shared data with lock
                with env_data_lock:
                    # Update AHT21 data if available
                    if aht21_data:
                        env_data['temperature'] = aht21_data['temperature'] 
                        env_data['humidity'] = aht21_data['humidity']
                        env_data['temperature_timestamp'] = current_time
                    
                    # Update BMX280 data if available
                    if bmx280_data:
                        # Use BMX280 temperature as a backup if AHT21 failed
                        if not aht21_data and 'temperature' in bmx280_data:
                            env_data['temperature'] = bmx280_data['temperature']
                            env_data['temperature_timestamp'] = current_time
                            
                        if 'pressure' in bmx280_data:
                            env_data['pressure'] = bmx280_data['pressure'] 
                            env_data['pressure_timestamp'] = current_time
                    
                    # Calculate altitude based on pressure (if available)
                    if 'pressure' in env_data and env_data['pressure'] > 0:
                        # Simple altitude formula: h = 44330 * (1 - (p/p0)^(1/5.255))
                        # where p0 is sea level pressure (typically 1013.25 hPa)
                        try:
                            p0 = 1013.25  # Standard sea level pressure in hPa
                            altitude = 44330 * (1 - (env_data['pressure'] / p0) ** (1/5.255))
                            env_data['altitude'] = round(altitude, 1)
                        except:
                            pass
                
                # Comment out or set to debug level to disable serial output of environmental data
                # if hasattr(env_thread_func, "_log_counter"):
                #     env_thread_func._log_counter += 1
                # else:
                #     env_thread_func._log_counter = 0
                    
                # if env_thread_func._log_counter % 10 == 0:  # Log every ~20 seconds
                #     log_msg = "Environmental data: "
                #     if aht21_data:
                #         log_msg += f"Temp: {aht21_data['temperature']}°C, Humidity: {aht21_data['humidity']}%"
                #     if bmx280_data:
                #         log_msg += f", Pressure: {bmx280_data['pressure']} hPa"
                #     if 'altitude' in env_data:
                #         log_msg += f", Est. Altitude: {env_data['altitude']} m"
                #     logger.info(log_msg)
                
        except Exception as e:
            logger.error(f"Error in environmental sensors thread: {e}")
            
        # Sleep to prevent high CPU usage
        time.sleep(0.5)  # Shorter sleep time than the update interval
        
    logger.debug("Environmental sensors thread stopped")
