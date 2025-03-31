import time
import pynmea2
import logging

logger = logging.getLogger("SensorFusion")

def gps_thread_func(serial_port, gps_data_lock, gps_data, stop_event, config, map_update_func=None, sensor_fusion=None):
    """Thread function for GPS acquisition"""
    logger.debug("GPS thread started")
    last_map_update = 0
    while not stop_event.is_set():
        try:
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
                current_time = time.time()
                if (map_update_func is not None and 
                    current_time - last_map_update >= config.GPS_MAP_UPDATE_INTERVAL and
                    getattr(config, 'ENABLE_GPS_MAP', False)):
                    last_map_update = current_time
                    try:
                        map_update_func(gps_data, config, sensor_fusion.analyzer if sensor_fusion else None)
                    except Exception as e:
                        logger.error(f"Error updating GPS map: {e}")
                
                logger.debug(f"GPS: {gps_data}")
                
        except Exception as e:
            logger.debug(f"Error in GPS thread: {e}")
            
        # Sleep to prevent high CPU usage
        time.sleep(0.2)
        
    logger.debug("GPS thread stopped")
