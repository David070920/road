import time
import threading
import logging
from quality.io.i2c_utils import get_accel_data  # Fix import path
from quality.acquisition.network_gps_receiver import start_network_gps_server # Import server start function
from quality.acquisition.gps_acquisition import gps_thread_func as network_gps_thread_func # Import the modified gps_thread_func

logger = logging.getLogger("SensorFusion")

# Placeholder for initialize_sensors or similar setup function
# This function would be called at application startup.
def initialize_sensors_and_network_gps(config):
    """
    Initializes sensors and starts the network GPS server.
    This is a conceptual placement; actual integration might be in run.py or a main setup routine.
    """
    logger.info("Initializing sensors and starting Network GPS server...")

    # Start the Network GPS Receiver Server
    # Host and port can be made configurable via config.py
    network_gps_host = getattr(config, 'NETWORK_GPS_HOST', '0.0.0.0')
    network_gps_port = getattr(config, 'NETWORK_GPS_PORT', 5001)
    
    # Run the server in a separate thread so it doesn't block
    server_thread = threading.Thread(
        target=start_network_gps_server,
        args=(network_gps_host, network_gps_port),
        daemon=True # Ensure thread exits when main program exits
    )
    server_thread.start()
    logger.info(f"Network GPS server started on {network_gps_host}:{network_gps_port}")

    # ... existing sensor initialization logic would go here ...
    # For example, initializing LiDAR, Accelerometer, etc.
    # lidar_device = initialize_lidar(config)
    # i2c_bus = initialize_i2c(config)
    
    # The GPS hardware initialization (initialize_gps) will be removed or modified
    # in hardware/gps_init.py. No serial port is needed for network GPS.

    # Return any initialized objects if necessary
    # return lidar_device, i2c_bus

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

# The old gps_thread_func is removed.
# The new network_gps_thread_func (aliased from gps_acquisition.py) will be used instead.
# It will be started in a similar way to other sensor threads, but without a serial_port argument.
# Example of how it might be started (actual start logic is usually in run.py or a main class):
#
# from quality.acquisition.gps_acquisition import gps_thread_func as network_gps_thread_func
#
# gps_thread = threading.Thread(
#     target=network_gps_thread_func,
#     args=(
#         None,  # serial_port (no longer used for network GPS)
#         gps_data_lock,
#         gps_data_shared_dict,
#         stop_event,
#         config,
#         map_update_function_callback, # e.g., self.update_gps_map_data
#         sensor_fusion_instance
#     ),
#     daemon=True
# )
# gps_thread.start()

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
