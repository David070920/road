import time
import pynmea2
import logging

logger = logging.getLogger("SensorFusion")

def gps_thread_func(gps_serial_port, gps_data_lock, gps_data, stop_event, config, update_gps_map, sensor_instance):
    """Thread function for GPS data acquisition"""
    logger.info("GPS thread started")
    while not stop_event.is_set():
        try:
            if gps_serial_port is None:
                time.sleep(0.2)
                continue
                
            # Fetch the GPS data
            raw_data = gps_serial_port.readline().decode().strip()
            
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
                if current_time - sensor_instance.last_map_update >= config.GPS_MAP_UPDATE_INTERVAL:
                    # Pass the analyzer to the map update function
                    update_gps_map(gps_data, config, getattr(sensor_instance, 'analyzer', None))
                    sensor_instance.last_map_update = current_time
                
                logger.info(f"GPS: {gps_data}")
                
        except Exception as e:
            logger.debug(f"Error in GPS thread: {e}")
            
        # Sleep to prevent high CPU usage
        time.sleep(0.2)
        
    logger.info("GPS thread stopped")
