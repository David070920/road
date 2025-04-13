import time
import pynmea2
import logging

logger = logging.getLogger("SensorFusion")

def gps_thread_func(serial_port, gps_data_lock, gps_data, stop_event, config, map_update_func=None, sensor_fusion=None):
    """Thread function for GPS acquisition"""
    logger.debug("GPS thread started")
    last_map_update = 0
    last_data_log = 0
    
    # Force a logging interval even without GPS updates
    log_interval = getattr(config, 'GPS_QUALITY_LOG_INTERVAL', 2.0)  # Default 2 seconds
    force_log_timer = time.time()
    
    while not stop_event.is_set():
        try:
            current_time = time.time()
            
            # Check if we need to force a log entry even without new GPS data
            if (sensor_fusion and sensor_fusion.analyzer and 
                current_time - force_log_timer >= log_interval):
                force_log_timer = current_time
                # Use current GPS data (even if zeros) for logging
                with gps_data_lock:
                    current_gps = dict(gps_data)  # Make a copy
                try:
                    # Log data regardless of GPS values
                    sensor_fusion.analyzer.log_gps_quality_color(current_gps)
                except Exception as e:
                    logger.error(f"Error logging GPS quality data: {e}")
                
            if serial_port is None:
                time.sleep(0.2)
                continue
                
            # Fetch the GPS data
            raw_data = serial_port.readline().decode().strip()
            
            if raw_data.find('GGA') > 0:
                gps_message = pynmea2.parse(raw_data)
                
                # Update shared data with lock
                with gps_data_lock:
                    gps_data.update({
                        "timestamp": gps_message.timestamp,
                        "lat": round(gps_message.latitude, 6),
                        "lon": round(gps_message.longitude, 6),
                        "alt": gps_message.altitude,
                        "sats": gps_message.num_sats
                    })
                
                # Check if it's time to update the map
                if (map_update_func is not None and 
                    current_time - last_map_update >= config.GPS_MAP_UPDATE_INTERVAL and
                    getattr(config, 'ENABLE_GPS_MAP', False)):
                    last_map_update = current_time
                    try:
                        map_update_func(gps_data, config, sensor_fusion.analyzer if sensor_fusion else None)
                    except Exception as e:
                        logger.error(f"Error updating GPS map: {e}")
                
                # Reset force log timer when we have actual GPS updates
                # This avoids duplicate logging right after a GPS update
                force_log_timer = current_time
                
                logger.debug(f"GPS: {gps_data}")
                
        except Exception as e:
            logger.debug(f"Error in GPS thread: {e}")
            
        # Sleep to prevent high CPU usage
        time.sleep(0.2)
        
    logger.debug("GPS thread stopped")
