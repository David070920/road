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

# Handle both direct execution and module import
if __name__ == "__main__":
    # Add the project root to the Python path
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
    sys.path.insert(0, project_root)
    
    # Use absolute imports when run directly
    from quality.config import Config
    from quality.hardware import initialize_i2c, initialize_lidar, initialize_gps, initialize_icm20948, initialize_aht21, initialize_bmx280
    from quality.acquisition import lidar_thread_func, gps_thread_func, accel_thread_func, env_thread_func
    from quality.visualization import setup_visualization
    from quality.io.gps_utils import update_gps_map, create_default_map
    from quality.analysis import RoadQualityAnalyzer
    from quality.core.context_managers import lidar_device_context, serial_port_context, i2c_bus_context
    from quality.web.server import RoadQualityWebServer
    from quality.logging_config import configure_logging  # Add this import
    from quality.core.data_structures import LidarPointBuffer, AccelerometerBuffer, GPSHistoryBuffer, EnvironmentalDataBuffer
else:
    # Use relative imports when imported as a module
    from ..config import Config
    from ..hardware import initialize_i2c, initialize_lidar, initialize_gps, initialize_icm20948, initialize_aht21, initialize_bmx280
    from ..acquisition import lidar_thread_func, gps_thread_func, accel_thread_func, env_thread_func
    from ..visualization import setup_visualization
    from ..io.gps_utils import update_gps_map, create_default_map
    from ..analysis import RoadQualityAnalyzer
    from .context_managers import lidar_device_context, serial_port_context, i2c_bus_context
    from ..web.server import RoadQualityWebServer
    from ..logging_config import configure_logging  # Add this import
    from .data_structures import LidarPointBuffer, AccelerometerBuffer, GPSHistoryBuffer, EnvironmentalDataBuffer

# Fix Wayland error
# os.environ["QT_QPA_PLATFORM"] = "xcb"  # Disabled to allow proper Qt backend selection

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
configure_logging()  # Add this line to silence werkzeug and other libraries
logger = logging.getLogger("SensorFusion")

class SensorFusion:
    def __init__(self, safe_mode=False):
        self.config = Config()
        self.safe_mode = safe_mode
        
        if self.safe_mode:
            logger.info("Running in safe mode - some features will be disabled")
            # Force disable potentially problematic components in safe mode
            self.config.ENABLE_VISUALIZATION = False
            
        # Log user and session information
        logger.info(f"Starting SensorFusion - User: {self.config.USER_LOGIN}, Session start: {self.config.SYSTEM_START_TIME}")
        
        # Data structures with improved thread safety
        # Use RLock instead of Lock for cases where the same thread might need to acquire the lock multiple times
        self.lidar_data_lock = threading.RLock()
        # Replace deque with LidarPointBuffer for more efficient memory management
        self.lidar_data = LidarPointBuffer(capacity=self.config.MAX_DATA_POINTS)
        # Add condition for signaling when new lidar data is available
        self.lidar_data_condition = threading.Condition(self.lidar_data_lock)
        
        # Initialize other data structures and objects
        try:
            self.accel_data_lock = threading.RLock()
            # Replace deque with AccelerometerBuffer for optimized numeric storage
            self.accel_data = AccelerometerBuffer(capacity=self.config.MAX_DATA_POINTS)
            # Add condition for signaling when new accelerometer data is available
            self.accel_data_condition = threading.Condition(self.accel_data_lock)
            
            self.gps_data_lock = threading.RLock()
            self.gps_data = {"timestamp": None, "lat": 0, "lon": 0, "alt": 0, "sats": 0, "lock": self.gps_data_lock}
            self.last_map_update = 0
            
            # Add environmental data structure
            self.env_data_lock = threading.RLock()
            self.env_data = {
                'temperature': None,
                'humidity': None,
                'pressure': None,
                'altitude': None,
                'temperature_timestamp': 0,
                'pressure_timestamp': 0
            }
            # Add buffer for historical environmental data
            self.env_data_history = EnvironmentalDataBuffer(capacity=300)  # 5 minutes at 1 sample/sec
            
            # Add a condition for signaling when new environmental data is available
            self.env_data_condition = threading.Condition(self.env_data_lock)
            
            # Add a data snapshot attribute to avoid full copies
            self.data_snapshot = {
                'lidar': None,
                'accel': None,
                'gps': None,
                'env': None,  # Add environmental data to snapshot
                'timestamp': 0
            }
            self.snapshot_lock = threading.RLock()
            
            # Use RLock for the analyzer to allow recursive acquisition
            self.analyzer = RoadQualityAnalyzer(self.config, self)
            self.analysis_lock = threading.RLock()
            
            # Add GPS quality history with circular buffer for memory efficiency
            self.gps_quality_history = GPSHistoryBuffer(capacity=1000)
            
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
            
            # Add web server
            self.web_server = None
            
            # Log the map file location only if GPS map is enabled
            if getattr(self.config, 'ENABLE_GPS_MAP', False) and hasattr(self.config, 'MAP_HTML_PATH'):
                logger.info(f"GPS map will be saved to: {self.config.MAP_HTML_PATH}")
            else:
                logger.info("GPS map generation is disabled")
        except Exception as e:
            logger.error(f"Error during SensorFusion initialization: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def initialize_devices(self):
        """Initialize all the devices with improved error handling"""
        try:
            self.i2c_bus = initialize_i2c()
            if not self.i2c_bus:
                logger.error("Failed to initialize I2C. Exiting.")
                return False
        except Exception as e:
            logger.error(f"Critical error initializing I2C: {e}")
            return False
            
        try:
            self.lidar_device = initialize_lidar(self.config)
            if not self.lidar_device:
                if self.safe_mode:
                    logger.warning("Failed to initialize LiDAR but continuing in safe mode.")
                else:
                    logger.error("Failed to initialize LiDAR. Exiting.")
                    return False
        except Exception as e:
            logger.error(f"Error initializing LiDAR: {e}")
            if not self.safe_mode:
                return False
            
        try:
            self.gps_serial_port = initialize_gps(self.config)
            if not self.gps_serial_port:
                logger.warning("Failed to initialize GPS. Continuing without GPS.")
        except Exception as e:
            logger.warning(f"Error initializing GPS: {e}")
        
        try:
            if not initialize_icm20948(self.i2c_bus, self.config):
                logger.warning("Failed to initialize ICM20948. Continuing without accelerometer data.")
        except Exception as e:
            logger.warning(f"Error initializing accelerometer: {e}")
        
        try:
            # Initialize AHT21 temperature/humidity sensor
            if not initialize_aht21(self.i2c_bus, self.config):
                logger.warning("Failed to initialize AHT21 sensor. Continuing without temperature/humidity data.")
        except Exception as e:
            logger.warning(f"Error initializing temperature/humidity sensor: {e}")
        
        try:
            # Initialize BMX280 pressure/temperature sensor
            if not initialize_bmx280(self.i2c_bus, self.config):
                logger.warning("Failed to initialize BMX280 sensor. Continuing without pressure data.")
        except Exception as e:
            logger.warning(f"Error initializing pressure sensor: {e}")
        
        return True

    def start_threads(self):
        """Start data acquisition threads using a thread pool with improved error handling"""
        # Create a thread pool with appropriate number of workers
        self.thread_pool = ThreadPoolExecutor(max_workers=5)
        self.futures = []
        
        # Submit tasks to the thread pool with proper error handling
        if self.lidar_device:
            try:
                self.futures.append(
                    self.thread_pool.submit(
                        lidar_thread_func, 
                        self.lidar_device, self.lidar_data_lock, 
                        self.lidar_data, self.stop_event, self.config
                    )
                )
                logger.info("LiDAR acquisition thread started")
            except Exception as e:
                logger.error(f"Failed to start LiDAR thread: {e}")
        elif not self.safe_mode:
            logger.warning("LiDAR device not initialized, skipping LiDAR thread")
            
        if self.gps_serial_port:
            try:
                self.futures.append(
                    self.thread_pool.submit(
                        gps_thread_func, 
                        self.gps_serial_port, self.gps_data_lock, 
                        self.gps_data, self.stop_event, self.config, 
                        update_gps_map, self
                    )
                )
                logger.info("GPS acquisition thread started")
            except Exception as e:
                logger.error(f"Failed to start GPS thread: {e}")
        else:
            logger.warning("GPS device not initialized, skipping GPS thread")
            
        if self.i2c_bus:
            try:
                self.futures.append(
                    self.thread_pool.submit(
                        accel_thread_func, 
                        self.i2c_bus, self.accel_data_lock, 
                        self.accel_data, self.stop_event, self.config
                    )
                )
                logger.info("Accelerometer acquisition thread started")
            except Exception as e:
                logger.error(f"Failed to start accelerometer thread: {e}")
                
            # Add environmental sensors thread
            try:
                self.futures.append(
                    self.thread_pool.submit(
                        env_thread_func,
                        self.i2c_bus, self.env_data_lock,
                        self.env_data, self.stop_event, self.config
                    )
                )
                logger.info("Environmental sensors thread started")
            except Exception as e:
                logger.error(f"Failed to start environmental sensors thread: {e}")
        else:
            logger.warning("I2C bus not initialized, skipping accelerometer and environmental threads")
        
        # Start the analysis thread separately since it depends on the other threads
        try:
            analysis_thread = threading.Thread(
                target=self.analysis_thread_func,
                daemon=True
            )
            analysis_thread.start()
            self.threads.append(analysis_thread)
            logger.info("Analysis thread started")
        except Exception as e:
            logger.error(f"Failed to start analysis thread: {e}")
            # Analysis thread is critical, consider stopping if it fails
            if not self.safe_mode:
                self.stop_event.set()
                logger.error("Critical thread failed, initiating shutdown")
                return False
                
        return True

    def setup_signal_handler(self):
        """Set up signal handler for graceful shutdown"""
        import threading
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self.signal_handler)
        else:
            logger.warning("Skipping signal handler setup: not in main thread")

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
        
        # Stop web server
        if self.web_server:
            try:
                self.web_server.stop()
                logger.info("Web server stopped")
            except Exception as e:
                logger.error(f"Error stopping web server: {e}")
                
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
                    with self.lidar_data_lock, self.accel_data_lock, self.gps_data_lock, self.env_data_lock:
                        self.data_snapshot['lidar'] = list(self.lidar_data)
                        self.data_snapshot['accel'] = list(self.accel_data)
                        self.data_snapshot['gps'] = {
                            'lat': self.gps_data['lat'],
                            'lon': self.gps_data['lon'],
                            'alt': self.gps_data['alt'],
                            'sats': self.gps_data['sats'],
                            'timestamp': self.gps_data['timestamp']
                        }
                        # Add environmental data to snapshot
                        self.data_snapshot['env'] = {
                            'temperature': self.env_data['temperature'],
                            'humidity': self.env_data['humidity'],
                            'pressure': self.env_data['pressure'],
                            'altitude': self.env_data['altitude'],
                            'temperature_timestamp': self.env_data['temperature_timestamp'],
                            'pressure_timestamp': self.env_data['pressure_timestamp']
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
            env_data = self.data_snapshot['env']
            
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
                
                # Calculate quality metrics directly without calibration check
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
                # Comment out or change to debug level to stop printing road quality values
                # if self._log_counter % 10 == 0:
                #     logger.info(f"Road quality: {quality:.1f}/100 ({classification}), Texture: {texture:.1f}/100")
            
            # Add to GPS quality history for heatmap visualization
            try:
                if gps_data['lat'] != 0 and gps_data['lon'] != 0:
                    with self.analysis_lock:
                        quality_score = self.analyzer.lidar_quality_score
                        # Only add points if we've moved (to avoid clustering)
                        add_point = True
                        if self.gps_quality_history:
                            last_point = self.gps_quality_history[-1]
                            # Calculate rough distance using simple formula
                            dist = (
                                (last_point['lat'] - gps_data['lat'])**2 + 
                                (last_point['lon'] - gps_data['lon'])**2
                            ) ** 0.5
                            # Only add point if we've moved at least a small distance
                            add_point = dist > 0.00005  # ~5 meters
                        
                        if add_point:
                            self.gps_quality_history.append({
                                'lat': gps_data['lat'],
                                'lon': gps_data['lon'],
                                'quality': quality_score,
                                'timestamp': time.time()
                            })
                            # Limit history size
                            if len(self.gps_quality_history) > 1000:
                                # Keep more recent points
                                self.gps_quality_history = self.gps_quality_history[-1000:]
            except Exception as e:
                logger.error(f"Error updating GPS quality history: {e}")
        
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
        """Main function to run the application with improved error handling"""
        try:
            self.setup_signal_handler()
            
            if not self.initialize_devices():
                logger.error("Device initialization failed, cannot continue")
                self.cleanup()
                return
            
            # Use context managers for device resources during the entire run
            # But handle potential segfaults with try/except blocks
            try:
                with lidar_device_context(self.lidar_device) as lidar:
                    self.lidar_device = lidar
                    logger.debug("LiDAR context manager initialized successfully")
                    
                    with serial_port_context(self.gps_serial_port) as gps:
                        self.gps_serial_port = gps
                        logger.debug("GPS context manager initialized successfully")
                        
                        with i2c_bus_context(self.i2c_bus) as i2c:
                            self.i2c_bus = i2c
                            logger.debug("I2C bus context manager initialized successfully")
                            
                            # Skip map creation if disabled
                            if getattr(self.config, 'ENABLE_GPS_MAP', False):
                                try:
                                    create_default_map(self.config)
                                except Exception as e:
                                    logger.error(f"Error creating default map: {e}")
                            
                            # Start data acquisition threads
                            thread_start_success = self.start_threads()
                            if not thread_start_success and not self.safe_mode:
                                logger.error("Failed to start critical threads, exiting")
                                return
                            
                            try:
                                # Only setup visualization if enabled in config and not in safe mode
                                if self.config.ENABLE_VISUALIZATION and not self.safe_mode:
                                    logger.info("Setting up visualization...")
                                    try:
                                        self.fig_lidar, self.fig_accel, self.lidar_ani, self.accel_ani = setup_visualization(
                                            self.lidar_data, self.lidar_data_lock, 
                                            self.accel_data, self.accel_data_lock, 
                                            self.config,
                                            self.analyzer,
                                            self.analysis_lock
                                        )
                                        # Show the figures but don't block
                                        plt.ioff()  # Use plt.ioff() to avoid keeping windows always on top
                                        plt.show(block=False)
                                    except Exception as vis_error:
                                        logger.error(f"Visualization setup failed: {vis_error}")
                                        self.config.ENABLE_VISUALIZATION = False
                                else:
                                    logger.info("Visualization disabled in configuration")
                                
                                # Don't automatically start web server - let GUI handle this
                                logger.info("Web server initialization skipped - will be started on demand by GUI")
                                
                                # Skip map opening if disabled
                                if getattr(self.config, 'ENABLE_GPS_MAP', False) and not self.safe_mode:
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
                                
                                # Keep the main thread alive but responsive to signals
                                logger.info("System running - Press Ctrl+C to exit")
                                while not self.stop_event.is_set():
                                    try:
                                        if self.config.ENABLE_VISUALIZATION:
                                            plt.pause(0.1)  # Update plots while allowing other operations
                                        else:
                                            time.sleep(0.1)  # Just sleep when visualization is disabled
                                    except Exception as loop_error:
                                        logger.error(f"Error in main loop: {loop_error}")
                                        if not self.safe_mode:
                                            break
                                        time.sleep(0.2)  # Avoid spinning too fast in case of error
                                
                            except Exception as e:
                                logger.error(f"Error in system operation: {e}", exc_info=True)
                
            except Exception as device_error:
                logger.error(f"Critical error in device management: {device_error}", exc_info=True)
                
        except Exception as outer_error:
            logger.error(f"Unhandled exception in system: {outer_error}", exc_info=True)
            
        finally:
            logger.info("Beginning system cleanup...")
            self.cleanup()

# Add a main block to make the file runnable directly
if __name__ == "__main__":
    print("Starting Road Quality Measurement System directly...")
    sensor_fusion = SensorFusion()
    try:
        sensor_fusion.run()
    except KeyboardInterrupt:
        print("Interrupted by user. Shutting down...")
    except Exception as e:
        import traceback
        print(f"Error: {e}")
        traceback.print_exc()
