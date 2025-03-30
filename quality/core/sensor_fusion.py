import threading
import logging
import signal
import sys
import os
import time
import webbrowser
import matplotlib.pyplot as plt
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from ..config import Config
from ..hardware import initialize_i2c, initialize_lidar, initialize_gps, initialize_icm20948
from ..acquisition import lidar_thread_func, gps_thread_func, accel_thread_func
from ..visualization import setup_visualization
from ..io.gps_utils import update_gps_map, create_default_map
from ..analysis import RoadQualityAnalyzer
from .context_managers import lidar_device_context, serial_port_context, i2c_bus_context

# Fix Wayland error
os.environ["QT_QPA_PLATFORM"] = "xcb"  # Use X11 instead of Wayland

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SensorFusion")

class SensorFusion:
    def __init__(self):
        self.config = Config()
        
        # Log user and session information
        logger.info(f"Starting SensorFusion - User: {self.config.USER_LOGIN}, Session start: {self.config.SYSTEM_START_TIME}")
        
        # Data structures with improved thread safety
        # Use RLock instead of Lock for cases where the same thread might need to acquire the lock multiple times
        self.lidar_data_lock = threading.RLock()
        self.lidar_data = deque(maxlen=self.config.MAX_DATA_POINTS)
        # Add condition for signaling when new lidar data is available
        self.lidar_data_condition = threading.Condition(self.lidar_data_lock)
        
        self.accel_data_lock = threading.RLock()
        self.accel_data = deque(maxlen=self.config.MAX_DATA_POINTS)
        # Add condition for signaling when new accelerometer data is available
        self.accel_data_condition = threading.Condition(self.accel_data_lock)
        
        self.gps_data_lock = threading.RLock()
        self.gps_data = {"timestamp": None, "lat": 0, "lon": 0, "alt": 0, "sats": 0, "lock": self.gps_data_lock}
        self.last_map_update = 0
        
        # Add a data snapshot attribute to avoid full copies
        self.data_snapshot = {
            'lidar': None,
            'accel': None,
            'gps': None,
            'timestamp': 0
        }
        self.snapshot_lock = threading.RLock()
        
        # Use RLock for the analyzer to allow recursive acquisition
        self.analyzer = RoadQualityAnalyzer(self.config)
        self.analysis_lock = threading.RLock()
        
        # Add data ready flag and condition for efficient waiting
        self.data_ready = False
        self.data_ready_condition = threading.Condition(self.snapshot_lock)
        
        # Device handles
        self.lidar_device = None
        self.gps_serial_port = None
        self.i2c_bus = None
        
        # Thread control
        self.stop_event = threading.Event()
        self.threads = []
        self.thread_pool = None
        self.futures = []
        
        # Visualization objects
        self.fig_lidar = None
        self.fig_accel = None
        self.lidar_ani = None
        self.accel_ani = None
        
        # Log the map file location
        logger.info(f"GPS map will be saved to: {self.config.MAP_HTML_PATH}")

    def initialize_devices(self):
        """Initialize all the devices"""
        self.i2c_bus = initialize_i2c()
        if not self.i2c_bus:
            logger.error("Failed to initialize I2C. Exiting.")
            return False
        
        self.lidar_device = initialize_lidar(self.config)
        if not self.lidar_device:
            logger.error("Failed to initialize LiDAR. Exiting.")
            return False
            
        self.gps_serial_port = initialize_gps(self.config)
        if not self.gps_serial_port:
            logger.warning("Failed to initialize GPS. Continuing without GPS.")
            
        if not initialize_icm20948(self.i2c_bus, self.config):
            logger.warning("Failed to initialize ICM20948. Continuing without accelerometer data.")
        
        return True

    def start_threads(self):
        """Start data acquisition threads using a thread pool"""
        # Create a thread pool with appropriate number of workers
        self.thread_pool = ThreadPoolExecutor(max_workers=4)  # Adjust number as needed
        
        # Submit tasks to the thread pool and store futures
        self.futures = [
            self.thread_pool.submit(
                lidar_thread_func, 
                self.lidar_device, self.lidar_data_lock, 
                self.lidar_data, self.stop_event, self.config
            ),
            self.thread_pool.submit(
                gps_thread_func, 
                self.gps_serial_port, self.gps_data_lock, 
                self.gps_data, self.stop_event, self.config, 
                update_gps_map, self
            ),
            self.thread_pool.submit(
                accel_thread_func, 
                self.i2c_bus, self.accel_data_lock, 
                self.accel_data, self.stop_event, self.config
            )
        ]
        
        # Start the analysis thread separately since it depends on the other threads
        analysis_thread = threading.Thread(
            target=self.analysis_thread_func,
            daemon=True
        )
        analysis_thread.start()
        self.threads.append(analysis_thread)

    def setup_signal_handler(self):
        """Set up signal handler for graceful shutdown"""
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        """Handle SIGINT (Ctrl+C) gracefully"""
        logger.info("Shutdown signal received. Cleaning up...")
        self.cleanup()
        sys.exit(0)

    def cleanup(self):
        """Clean up resources before exit"""
        # Signal threads to stop
        self.stop_event.set()
        
        # Wait for threads to complete
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=1.0)
        
        # Shutdown the thread pool gracefully
        if self.thread_pool:
            self.thread_pool.shutdown(wait=True, cancel_futures=True)
            logger.info("Thread pool shut down")
                
        # Use context managers for device cleanup
        with lidar_device_context(self.lidar_device):
            pass  # Cleanup happens in context manager
            
        with serial_port_context(self.gps_serial_port):
            pass  # Cleanup happens in context manager
            
        with i2c_bus_context(self.i2c_bus):
            pass  # Cleanup happens in context manager
                
        logger.info("Cleanup complete")

    def analyze_data(self):
        """Analyze sensor data and update metrics with improved synchronization"""
        try:
            # Create a single snapshot of all data with minimal copying and better synchronization
            current_time = time.time()
            data_updated = False
            
            # Only update the snapshot every 0.1 seconds to reduce locking overhead
            with self.snapshot_lock:
                if current_time - self.data_snapshot['timestamp'] > 0.1:
                    # Use a more efficient approach: acquire all locks at once to avoid deadlocks
                    # Python's with statement allows multiple context managers
                    with self.lidar_data_lock, self.accel_data_lock, self.gps_data_lock:
                        self.data_snapshot['lidar'] = list(self.lidar_data)
                        self.data_snapshot['accel'] = list(self.accel_data)
                        self.data_snapshot['gps'] = {
                            'lat': self.gps_data['lat'],
                            'lon': self.gps_data['lon'],
                            'alt': self.gps_data['alt'],
                            'sats': self.gps_data['sats'],
                            'timestamp': self.gps_data['timestamp']
                        }
                        
                    self.data_snapshot['timestamp'] = current_time
                    data_updated = True
                    
                    # Signal that new data is ready
                    with self.data_ready_condition:
                        self.data_ready = True
                        self.data_ready_condition.notify_all()
            
            # Skip analysis if no new data is available
            if not data_updated and hasattr(self, '_last_analysis_time') and \
               current_time - self._last_analysis_time < 0.2:
                time.sleep(0.05)  # Short sleep to reduce CPU usage
                return
                
            self._last_analysis_time = current_time
            
            # Use the snapshot for analysis - no need for locks here since we have a copy
            lidar_data = self.data_snapshot['lidar']
            accel_data = self.data_snapshot['accel']
            gps_data = self.data_snapshot['gps']
            
            # Only lock during the critical section of update
            with self.analysis_lock:
                # Log lidar data status for debugging - optimized to avoid string formatting
                if not lidar_data:
                    if not hasattr(self, '_log_warning_counter') or self._log_warning_counter % 20 == 0:
                        logger.warning("No LiDAR data available for analysis")
                    self._log_warning_counter = getattr(self, '_log_warning_counter', 0) + 1
                else:
                    # Count points in center field of view (-10 to 10 degrees)
                    center_points = sum(1 for p in lidar_data if (
                        p[0] >= 0 and p[0] <= 10) or (p[0] >= 350 and p[0] <= 360) or (
                        p[0] >= -10 and p[0] <= 0))
                    
                    # Only calculate and format debug message if debug logging is enabled
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Analyzing {len(lidar_data)} LiDAR points ({center_points} in center FOV)")
                
                # Calculate quality metrics - these don't modify shared state so could be done outside the lock
                # but we keep them here for code clarity
                quality = self.analyzer.calculate_lidar_road_quality(lidar_data)
                events = self.analyzer.detect_road_events(accel_data, gps_data)
                texture = self.analyzer.analyze_frequency_spectrum(accel_data)
                
                # Log road quality info periodically with more efficient counter logic
                classification = self.analyzer.get_road_classification()
                if events:
                    if not hasattr(self, '_events_reported') or self._events_reported != len(events):
                        logger.info(f"Events detected: {len(events)}")
                        self._events_reported = len(events)
                
                # Use the periodic logging function for regular updates
                if not hasattr(self, '_log_counter'):
                    self._log_counter = 0
                    
                self._log_counter += 1
                if self._log_counter % 10 == 0:
                    logger.info(f"Road quality: {quality:.1f}/100 ({classification}), Texture: {texture:.1f}/100")
        
        except Exception as e:
            logger.error(f"Error in data analysis: {e}")
            import traceback
            logger.error(traceback.format_exc())  # Log the full traceback for debugging

    def analysis_thread_func(self):
        """Thread function for continuous data analysis with improved wait logic"""
        logger.info("Analysis thread started")
        
        while not self.stop_event.is_set():
            try:
                # Wait for data to be ready instead of polling at fixed intervals
                # This is more efficient and responsive
                with self.data_ready_condition:
                    # Wait for data_ready or timeout after 0.5 seconds
                    self.data_ready_condition.wait(0.5)
                    # Reset flag to wait for next update
                    self.data_ready = False
                
                self.analyze_data()
            except Exception as e:
                logger.error(f"Error in analysis thread: {e}")
                time.sleep(0.5)  # Prevent tight loop in case of recurring errors
                
        logger.info("Analysis thread stopped")

    def run(self):
        """Main function to run the application"""
        self.setup_signal_handler()
        
        if not self.initialize_devices():
            self.cleanup()
            return
        
        # Use context managers for device resources during the entire run
        with lidar_device_context(self.lidar_device) as lidar, \
             serial_port_context(self.gps_serial_port) as gps, \
             i2c_bus_context(self.i2c_bus) as i2c:
            
            # Update the device references to ensure we use the managed resources
            self.lidar_device = lidar
            self.gps_serial_port = gps
            self.i2c_bus = i2c
            
            # Create default map before starting threads
            create_default_map(self.config)
            
            self.start_threads()
            
            try:
                logger.info("Setting up visualization...")
                self.fig_lidar, self.fig_accel, self.lidar_ani, self.accel_ani = setup_visualization(
                    self.lidar_data, self.lidar_data_lock, 
                    self.accel_data, self.accel_data_lock, 
                    self.config,
                    self.analyzer,
                    self.analysis_lock
                )
                
                # Try to open the map in browser
                try:
                    map_url = 'file://' + os.path.abspath(self.config.MAP_HTML_PATH)
                    logger.info(f"Opening map at: {map_url}")
                    if webbrowser.open(map_url):
                        logger.info("Map opened in browser")
                    else:
                        logger.warning("Failed to open browser, but map file was created")
                except Exception as e:
                    logger.error(f"Error opening map in browser: {e}")
                
                # Use plt.ioff() to avoid keeping windows always on top
                plt.ioff()
                # Show the figures but don't block
                plt.show(block=False)
                
                # Keep the main thread alive but responsive to signals
                while not self.stop_event.is_set():
                    plt.pause(0.1)  # Update plots while allowing other operations
                    
            except Exception as e:
                logger.error(f"Error in visualization: {e}")
            finally:
                self.cleanup()
