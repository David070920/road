import threading
import time
import queue
from PyQt5.QtCore import QThread, pyqtSignal

# Add project root to sys.path
import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from quality.core.sensor_fusion import SensorFusion
from quality.analysis.road_quality_analyzer import RoadQualityAnalyzer

class SensorDataReader(QThread):
    """Thread to read data from the SensorFusion module"""
    # Define signals for data updates
    accel_data_signal = pyqtSignal(object, object, object)  # value, quality, classification
    lidar_data_signal = pyqtSignal(float, float)  # angle, distance
    gps_data_signal = pyqtSignal(float, float)  # lat, lon
    env_data_signal = pyqtSignal(object)  # env_data dict
    sensor_status_signal = pyqtSignal(str, bool)  # sensor_name, is_connected
    log_signal = pyqtSignal(str, str)  # message, level
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sensor_fusion = None
        self.running = False
        self.safe_mode = True  # Use safe mode to avoid hardware access if not available
        
        # Data tracking
        self.last_accel_ts = 0
        self.last_lidar_ts = 0
        self.last_gps_ts = 0
        self.last_env_ts = 0
        
        # Minimum time between updates (in seconds)
        self.accel_update_interval = 0.05  # 50ms
        self.lidar_update_interval = 0.1   # 100ms
        self.gps_update_interval = 0.5     # 500ms
        self.env_update_interval = 1.0     # 1s
        
    def initialize(self):
        """Initialize the SensorFusion system"""
        try:
            self.log_signal.emit("Initializing sensor system...", "Info")
            self.sensor_fusion = SensorFusion(safe_mode=self.safe_mode)
            success = self.sensor_fusion.initialize_devices()
            
            if success:
                self.log_signal.emit("Sensor system initialized successfully", "Info")
                return True
            else:
                self.log_signal.emit("Failed to initialize sensor system", "Error")
                return False
        except Exception as e:
            self.log_signal.emit(f"Error initializing sensor system: {str(e)}", "Error")
            return False
    
    def run(self):
        """Main thread function that reads sensor data"""
        if not self.sensor_fusion:
            if not self.initialize():
                self.log_signal.emit("Failed to start sensor data reader", "Error")
                return
            
        try:
            # Start the SensorFusion system
            self.sensor_fusion.start_threads()
            self.running = True
            self.log_signal.emit("Sensor data reader started", "Info")
            
            # Check sensor status initially
            self.update_sensor_status()
            
            # Main data reading loop
            while self.running:
                # Get a snapshot of current data with minimal locking
                accel_data, lidar_data, gps_data, env_data = self.get_data_snapshot()
                
                # Update sensor status periodically
                if self.running:
                    self.update_sensor_status()
                
                # Process and emit accelerometer data if available
                self.process_accel_data(accel_data)
                
                # Process and emit LiDAR data if available
                self.process_lidar_data(lidar_data)
                
                # Process and emit GPS data if available
                self.process_gps_data(gps_data)
                
                # Process and emit environmental data if available
                self.process_env_data(env_data)
                
                # Sleep briefly to avoid high CPU usage
                threading.Event().wait(0.01)  # 10ms sleep
        
        except Exception as e:
            self.log_signal.emit(f"Error in sensor data reader: {str(e)}", "Error")
        finally:
            # Clean up resources
            if self.sensor_fusion:
                try:
                    self.sensor_fusion.cleanup()
                    self.log_signal.emit("Sensor fusion system stopped", "Info")
                except Exception as e:
                    self.log_signal.emit(f"Error stopping sensor fusion: {str(e)}", "Error")
    
    def get_data_snapshot(self):
        """Get a snapshot of current data from SensorFusion"""
        if not self.sensor_fusion:
            return None, None, None, None
            
        try:
            with self.sensor_fusion.snapshot_lock:
                accel_data = list(self.sensor_fusion.accel_data) if self.sensor_fusion.accel_data else []
                lidar_data = list(self.sensor_fusion.lidar_data) if self.sensor_fusion.lidar_data else []
                gps_data = {
                    'lat': self.sensor_fusion.gps_data['lat'],
                    'lon': self.sensor_fusion.gps_data['lon'],
                    'alt': self.sensor_fusion.gps_data['alt'],
                    'timestamp': self.sensor_fusion.gps_data['timestamp']
                }
                env_data = {
                    'temperature': self.sensor_fusion.env_data['temperature'],
                    'humidity': self.sensor_fusion.env_data['humidity'],
                    'pressure': self.sensor_fusion.env_data['pressure'],
                    'altitude': self.sensor_fusion.env_data['altitude']
                }
                
            return accel_data, lidar_data, gps_data, env_data
        except Exception as e:
            self.log_signal.emit(f"Error getting data snapshot: {str(e)}", "Error")
            return None, None, None, None
    
    def process_accel_data(self, accel_data):
        """Process and emit accelerometer data"""
        if not accel_data or not self.sensor_fusion:
            return
            
        current_time = time.time()
        if current_time - self.last_accel_ts < self.accel_update_interval:
            return
            
        self.last_accel_ts = current_time
        
        try:
            # Get the latest accelerometer value
            latest_accel = accel_data[-1] if accel_data else 0
            
            # Get quality metrics
            quality_score = getattr(self.sensor_fusion.analyzer, 'combined_quality_score', None)
            if quality_score is None:
                quality_score = getattr(self.sensor_fusion.analyzer, 'current_quality_score', 50)
                
            classification = self.sensor_fusion.analyzer.get_road_classification()
            
            # Emit the data
            self.accel_data_signal.emit(latest_accel, quality_score, classification)
        except Exception as e:
            self.log_signal.emit(f"Error processing accelerometer data: {str(e)}", "Error")
    
    def process_lidar_data(self, lidar_data):
        """Process and emit LiDAR data"""
        if not lidar_data:
            return
            
        current_time = time.time()
        if current_time - self.last_lidar_ts < self.lidar_update_interval:
            return
            
        self.last_lidar_ts = current_time
        
        try:
            # Process each LiDAR point and emit
            for point in lidar_data:
                angle_deg = point[0]
                distance = point[1]
                
                # Only emit points in our desired range (315°-360° or 0°-45°)
                if (0 <= angle_deg <= 45) or (315 <= angle_deg <= 360):
                    self.lidar_data_signal.emit(angle_deg, distance)
        except Exception as e:
            self.log_signal.emit(f"Error processing LiDAR data: {str(e)}", "Error")
    
    def process_gps_data(self, gps_data):
        """Process and emit GPS data"""
        if not gps_data or gps_data['lat'] == 0 or gps_data['lon'] == 0:
            return
            
        current_time = time.time()
        if current_time - self.last_gps_ts < self.gps_update_interval:
            return
            
        self.last_gps_ts = current_time
        
        try:
            # Emit GPS coordinates
            self.gps_data_signal.emit(gps_data['lat'], gps_data['lon'])
        except Exception as e:
            self.log_signal.emit(f"Error processing GPS data: {str(e)}", "Error")
    
    def process_env_data(self, env_data):
        """Process and emit environmental data"""
        if not env_data:
            return
            
        current_time = time.time()
        if current_time - self.last_env_ts < self.env_update_interval:
            return
            
        self.last_env_ts = current_time
        
        # Emit environmental data dictionary
        self.env_data_signal.emit(env_data)
    
    def update_sensor_status(self):
        """Check and emit sensor status"""
        if not self.sensor_fusion:
            return
            
        # Check LiDAR status
        lidar_status = self.sensor_fusion.lidar_device is not None
        self.sensor_status_signal.emit("lidar_status", lidar_status)
        
        # Check accelerometer status (inferred from data availability)
        accel_status = len(self.sensor_fusion.accel_data) > 0 if self.sensor_fusion.accel_data else False
        self.sensor_status_signal.emit("accel_status", accel_status)
        
        # Check GPS status (inferred from valid coordinates)
        gps_status = self.sensor_fusion.gps_data['lat'] != 0 and self.sensor_fusion.gps_data['lon'] != 0
        self.sensor_status_signal.emit("gps_status", gps_status)
        
        # Check environmental sensor status
        env_status = (self.sensor_fusion.env_data['temperature'] is not None or 
                     self.sensor_fusion.env_data['humidity'] is not None or
                     self.sensor_fusion.env_data['pressure'] is not None)
        self.sensor_status_signal.emit("env_status", env_status)
    
    def stop(self):
        """Stop the thread safely"""
        self.running = False
        self.wait(1000)  # Wait up to 1 second for thread to finish