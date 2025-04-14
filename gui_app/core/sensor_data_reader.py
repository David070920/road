import threading
import time
import queue
from PyQt5.QtCore import QThread, pyqtSignal, QTimer

# Add project root to sys.path
import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from quality.config import Config
from quality.core.sensor_fusion import SensorFusion
from quality.analysis.road_quality_analyzer import RoadQualityAnalyzer

class SensorDataReader(QThread):
    """Thread to read data from the SensorFusion module"""
    # Define signals for data updates
    accel_data_signal = pyqtSignal(object, object, object)  # value, quality, classification
    # Updated signal for batch LiDAR data
    lidar_data_signal = pyqtSignal(object)  # list of (angle, distance) tuples
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
        
        # Use config value for LiDAR update interval
        self.lidar_update_interval = Config.LIDAR_DATA_BATCH_INTERVAL
        
        self.gps_update_interval = 0.5     # 500ms
        self.env_update_interval = 1.0     # 1s
        
        # Add snapshot lock to mimic SensorFusion API for web server
        self.snapshot_lock = threading.RLock()
        
        # Add cached data for web server access
        self._cached_snapshot = {
            'accel_data': [],
            'lidar_data': [],
            'gps_data': {'lat': 0, 'lon': 0, 'alt': 0, 'timestamp': 0},
            'env_data': {'temperature': None, 'humidity': None, 'pressure': None, 'altitude': None},
            'quality': {'lidar': 0, 'accel': 0, 'combined': 0},
            'classification': 'Unknown',
            'events': [],
            'timestamp': 0
        }
        
        # Update cache timer
        self.cache_timer = QTimer()
        self.cache_timer.timeout.connect(self.update_data_cache)
        self.cache_timer.start(200)  # Update cache every 200ms
        
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
            
            # Get quality metrics - use LiDAR quality score instead of combined score
            quality_score = None
            if hasattr(self.sensor_fusion, 'analyzer'):
                # Use LiDAR quality score as the primary score as requested
                quality_score = getattr(self.sensor_fusion.analyzer, 'lidar_quality_score', None)
                
                # Log the LiDAR quality score for debugging
                if quality_score is not None:
                    self.log_signal.emit(f"LiDAR road quality score: {quality_score:.1f}", "Debug")
                else:
                    self.log_signal.emit("LiDAR quality score not available", "Debug")
                
                # Fall back to combined score if LiDAR score is not available
                if quality_score is None:
                    quality_score = getattr(self.sensor_fusion.analyzer, 'combined_quality_score', None)
                    if quality_score is not None:
                        self.log_signal.emit(f"Using combined quality score as fallback: {quality_score:.1f}", "Debug")
                
                # Fall back to current_quality_score (accelerometer-based) if still None
                if quality_score is None:
                    quality_score = getattr(self.sensor_fusion.analyzer, 'current_quality_score', None)
                    if quality_score is not None:
                        self.log_signal.emit(f"Using accel quality score as fallback: {quality_score:.1f}", "Debug")
            
            # Default if all else fails
            if quality_score is None:
                quality_score = 75
                self.log_signal.emit("No quality scores available, using default value", "Debug")
                
            # Get road classification based on LiDAR
            classification = "Unknown"
            if hasattr(self.sensor_fusion, 'analyzer') and hasattr(self.sensor_fusion.analyzer, 'get_road_classification'):
                # Use the LiDAR-specific road classification
                classification = self.sensor_fusion.analyzer.get_road_classification()
            else:
                # Simple classification based on quality score
                if quality_score >= 75:
                    classification = "Good"
                elif quality_score >= 50:
                    classification = "Fair"
                else:
                    classification = "Poor"
            
            # Emit the data
            self.accel_data_signal.emit(latest_accel, quality_score, classification)
        except Exception as e:
            self.log_signal.emit(f"Error processing accelerometer data: {str(e)}", "Error")
    
    def process_lidar_data(self, lidar_data):
        """Process and emit LiDAR data in batches for better performance"""
        if not lidar_data:
            return
            
        current_time = time.time()
        if current_time - self.last_lidar_ts < self.lidar_update_interval:
            return
            
        self.last_lidar_ts = current_time
        
        try:
            # Filter points to those in our desired range (315°-360° or 0°-45°)
            filtered_points = []
            for point in lidar_data:
                angle_deg = point[0]
                distance = point[1]
                
                # Only include points in our desired range
                if (0 <= angle_deg <= 45) or (315 <= angle_deg <= 360):
                    filtered_points.append((angle_deg, distance))
            
            # Emit all points in a single batch
            if filtered_points:
                # Limit to a reasonable number of points to prevent performance issues
                max_points = 180  # One point per half-degree in our 90° FOV
                if len(filtered_points) > max_points:
                    # Sample evenly across the available points
                    step = len(filtered_points) // max_points
                    filtered_points = filtered_points[::step][:max_points]
                
                # Log the number of points being sent
                self.log_signal.emit(f"Sending batch of {len(filtered_points)} LiDAR points", "Debug")
                
                # Send the entire batch at once
                self.lidar_data_signal.emit(filtered_points)
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

    # Add web server adapter methods
    def update_data_cache(self):
        """Update the cached data for web server access"""
        if self.sensor_fusion:
            data_snapshot = self.get_data_snapshot()
            
            with self.snapshot_lock:
                # Update basic sensor data
                self._cached_snapshot['accel_data'] = data_snapshot[0] if data_snapshot[0] else []
                self._cached_snapshot['lidar_data'] = data_snapshot[1] if data_snapshot[1] else []
                self._cached_snapshot['gps_data'] = data_snapshot[2] if data_snapshot[2] else {'lat': 0, 'lon': 0, 'alt': 0, 'timestamp': 0}
                self._cached_snapshot['env_data'] = data_snapshot[3] if data_snapshot[3] else {'temperature': None, 'humidity': None, 'pressure': None, 'altitude': None}
                self._cached_snapshot['timestamp'] = time.time()
                
                # Get quality metrics if analyzer is available
                if hasattr(self.sensor_fusion, 'analyzer'):
                    # Get base quality scores from analyzer
                    lidar_score = getattr(self.sensor_fusion.analyzer, 'lidar_quality_score', 0)
                    accel_score = getattr(self.sensor_fusion.analyzer, 'current_quality_score', 0)
                    combined_score = getattr(self.sensor_fusion.analyzer, 'combined_quality_score', 0)
                    
                    # Update the cached quality scores
                    self._cached_snapshot['quality']['lidar'] = lidar_score
                    self._cached_snapshot['quality']['accel'] = accel_score
                    
                    # Use lidar_score as the combined score as requested
                    # Only fall back to combined_score if lidar_score is not available
                    if lidar_score > 0:
                        self._cached_snapshot['quality']['combined'] = lidar_score
                    else:
                        self._cached_snapshot['quality']['combined'] = combined_score
                    
                    # Get road classification using the LiDAR-specific method
                    classification = self.sensor_fusion.analyzer.get_road_classification()
                    
                    # Store the classification
                    self._cached_snapshot['classification'] = classification
                    self._cached_snapshot['events'] = getattr(self.sensor_fusion.analyzer, 'events', [])[-20:]
    
    # Web server adapter properties
    @property
    def analyzer(self):
        """Provide access to analyzer for web server"""
        if self.sensor_fusion and hasattr(self.sensor_fusion, 'analyzer'):
            return self.sensor_fusion.analyzer
        return None
    
    @property
    def accel_data(self):
        """Provide access to accelerometer data for web server"""
        with self.snapshot_lock:
            return self._cached_snapshot['accel_data']
    
    @property
    def lidar_data(self):
        """Provide access to LiDAR data for web server"""
        with self.snapshot_lock:
            return self._cached_snapshot['lidar_data']
    
    @property
    def gps_data(self):
        """Provide access to GPS data for web server"""
        with self.snapshot_lock:
            return self._cached_snapshot['gps_data']
    
    @property
    def env_data(self):
        """Provide access to environmental data for web server"""
        with self.snapshot_lock:
            return self._cached_snapshot['env_data']