import time
import threading
import pynmea2
import logging
from quality.io.i2c_utils import get_accel_data  # Fix import path

logger = logging.getLogger("SensorFusion")

def filter_lidar_angles(scan_data, config):
    """Filter LiDAR data to only include points within specified angle ranges"""
    filtered_data = []
    
    for point in scan_data:
        angle = point[0]
        for angle_range in config.LIDAR_FILTER_ANGLES:
            if angle_range[0] <= angle <= angle_range[1]:
                filtered_data.append(point)
                break
                
    return filtered_data

def lidar_thread_func(lidar_device, lidar_data_lock, lidar_data, stop_event, config):
    """Thread function for LiDAR data acquisition with improved synchronization"""
    logger.info("LiDAR thread started")
    data_log_interval = 0
    empty_scan_count = 0
    
    while not stop_event.is_set():
        try:
            # Fetch the LiDAR scan data
            scan_data = lidar_device.get_scan_as_vectors(filter_quality=True)
            
            if not scan_data:
                empty_scan_count += 1
                if empty_scan_count % 10 == 0:  # Log only occasionally to avoid spam
                    logger.warning(f"Empty LiDAR scan received ({empty_scan_count} consecutive empty scans)")
                time.sleep(0.05)
                continue
            else:
                if empty_scan_count > 0:
                    logger.info(f"LiDAR scan data received after {empty_scan_count} empty scans")
                    empty_scan_count = 0
            
            # Filter data based on angles
            filtered_data = filter_lidar_angles(scan_data, config)
            
            # Periodically log data counts for debugging
            data_log_interval += 1
            if data_log_interval >= 50:  # Log every ~5 seconds (assuming 10Hz)
                logger.debug(f"LiDAR scan: {len(scan_data)} points, filtered to {len(filtered_data)} points")
                data_log_interval = 0
            
            # Update shared data with lock - Replace data instead of appending
            # Use the condition to notify waiting threads that new data is available
            with lidar_data_lock:
                lidar_data.clear()  # Clear old data
                lidar_data.extend(filtered_data)  # Add new data
                
                # If a condition variable exists, notify waiting threads
                if hasattr(lidar_data_lock, 'notify_all'):
                    lidar_data_lock.notify_all()
                    
        except Exception as e:
            logger.error(f"Error in LiDAR thread: {e}")
            
        # Sleep to prevent high CPU usage
        time.sleep(0.05)
    
    logger.info("LiDAR thread stopped")

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
                
                # Comment out or change to debug to stop printing GPS data
                # logger.info(f"GPS: {gps_data}")
                
        except Exception as e:
            logger.debug(f"Error in GPS thread: {e}")
            
        # Sleep to prevent high CPU usage
        time.sleep(0.2)
        
    logger.info("GPS thread stopped")

def accel_thread_func(i2c_bus, accel_data_lock, accel_data, stop_event, config):
    """Thread function for accelerometer data acquisition"""
    logger.info("Accelerometer thread started")
    while not stop_event.is_set():
        try:
            # Get accelerometer data
            accel_z = get_accel_data(i2c_bus, config)
            
            if accel_z is not None:
                # Update shared data with lock
                with accel_data_lock:
                    accel_data.append(accel_z)
                
                logger.debug(f"Accelerometer: Z={accel_z:.2f}g")
                
        except Exception as e:
            logger.error(f"Error in accelerometer thread: {e}")
            
        # Sleep to prevent high CPU usage
        time.sleep(0.1)
        
    logger.info("Accelerometer thread stopped")
