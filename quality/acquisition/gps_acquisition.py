import time
import logging
from quality.acquisition.network_gps_receiver import network_gps_data # Import network_gps_data

logger = logging.getLogger("SensorFusion")

def gps_thread_func(serial_port, gps_data_lock, gps_data, stop_event, config, map_update_func=None, sensor_fusion=None): # serial_port is no longer used but kept for compatibility for now
    """Thread function for GPS acquisition from network"""
    logger.debug("Network GPS thread started")
    last_map_update = 0
    
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
                    current_gps_for_log = dict(gps_data)  # Make a copy
                try:
                    # Log data regardless of GPS values
                    sensor_fusion.analyzer.log_gps_quality_color(current_gps_for_log)
                except Exception as e:
                    logger.error(f"Error logging GPS quality data: {e}")

            # Fetch the GPS data from network_gps_data
            # network_gps_data is assumed to be thread-safe or accessed in a way that doesn't require explicit locking here
            # as it's updated by a different thread (Flask server)
            
            # Create a temporary copy to work with
            current_network_gps = network_gps_data.copy()

            if current_network_gps: # Check if there's any data
                # Update shared data with lock
                with gps_data_lock:
                    gps_data.update({
                        "timestamp": current_network_gps.get("timestamp"), # Handle missing optional fields
                        "lat": current_network_gps.get("lat"),
                        "lon": current_network_gps.get("lon"),
                        "alt": current_network_gps.get("alt"), # Optional
                        "sats": current_network_gps.get("sats")  # Optional
                    })
                
                # Check if it's time to update the map
                if (map_update_func is not None and
                    current_time - last_map_update >= config.GPS_MAP_UPDATE_INTERVAL and
                    getattr(config, 'ENABLE_GPS_MAP', False) and
                    gps_data.get("lat") is not None and gps_data.get("lon") is not None): # Ensure we have lat/lon for map
                    last_map_update = current_time
                    try:
                        # Pass a copy of gps_data to map_update_func
                        with gps_data_lock:
                            map_data_copy = dict(gps_data)
                        map_update_func(map_data_copy, config, sensor_fusion.analyzer if sensor_fusion else None)
                    except Exception as e:
                        logger.error(f"Error updating GPS map: {e}")
                
                # Reset force log timer when we have actual GPS updates
                force_log_timer = current_time
                
                logger.debug(f"Network GPS: {gps_data}")
            else:
                # Optional: Log if no network GPS data is available after some time, or handle as needed
                # logger.debug("No network GPS data available")
                pass
                
        except Exception as e:
            # Log specific errors if possible, e.g., issues with network_gps_data access
            logger.error(f"Error in Network GPS thread: {e}", exc_info=True) # Added exc_info for more details
            
        # Sleep to prevent high CPU usage, and to allow network_gps_data to be updated
        time.sleep(0.2) # Interval can be adjusted
        
    logger.debug("Network GPS thread stopped")
