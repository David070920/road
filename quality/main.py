import threading
import logging
import signal
import sys
import os
import time
import webbrowser
import matplotlib.pyplot as plt
from collections import deque  # Import deque
import subprocess

from config import Config
from initialization import initialize_i2c, initialize_lidar, initialize_gps, initialize_icm20948
from data_acquisition import lidar_thread_func, gps_thread_func, accel_thread_func
from visualization import setup_visualization
from utils import update_gps_map, create_default_map
from analysis import RoadQualityAnalyzer  # Import the analyzer

# Fix Wayland error
os.environ["QT_QPA_PLATFORM"] = "xcb"  # Use X11 instead of Wayland

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SensorFusion")

# Add new constants for auto-restart functionality
RESTART_EXIT_CODE = 42
LIDAR_CONNECT_TIMEOUT = 7  # Reduce timeout to 7 seconds before restarting

class SensorFusion:
    def __init__(self):
        self.config = Config()
        
        # Log user and session information
        logger.info(f"Starting SensorFusion - User: {self.config.USER_LOGIN}, Session start: {self.config.SYSTEM_START_TIME}")
        
        # Data structures with thread safety
        self.lidar_data_lock = threading.Lock()
        self.lidar_data = []
        
        self.accel_data_lock = threading.Lock()
        # Changed: Use deque instead of list
        self.accel_data = deque(maxlen=self.config.MAX_DATA_POINTS)
        
        self.gps_data_lock = threading.Lock()
        # Changed: Update structure to match display.py
        self.gps_data = {"timestamp": None, "lat": 0, "lon": 0, "alt": 0, "sats": 0, "lock": self.gps_data_lock}
        self.last_map_update = 0  # Added: Track last map update time
        
        # Initialize the road quality analyzer
        self.analyzer = RoadQualityAnalyzer(self.config)
        self.analysis_lock = threading.Lock()
        
        # Device handles
        self.lidar_device = None
        self.gps_serial_port = None
        self.i2c_bus = None
        
        # Thread control
        self.stop_event = threading.Event()
        self.threads = []
        
        # Visualization objects
        self.fig_lidar = None
        self.fig_accel = None
        self.lidar_ani = None
        self.accel_ani = None
        
        # Log the map file location
        logger.info(f"GPS map will be saved to: {self.config.MAP_HTML_PATH}")
        
        # Add a flag to track if LiDAR initialization is complete
        self.lidar_init_complete = False
        self.lidar_init_start_time = 0

    def initialize_devices(self):
        """Initialize all the devices"""
        self.i2c_bus = initialize_i2c()
        if not self.i2c_bus:
            logger.error("Failed to initialize I2C. Exiting.")
            return False
        
        # Start watchdog thread to monitor LiDAR initialization
        self.lidar_init_complete = False
        self.lidar_init_start_time = time.time()
        watchdog_thread = threading.Thread(target=self._lidar_init_watchdog, daemon=True)
        watchdog_thread.start()
        
        # Log that we're starting LiDAR initialization
        logger.info("Starting LiDAR initialization (this may take a moment)...")
        
        try:
            self.lidar_device = initialize_lidar(self.config)
        finally:
            # Mark initialization as complete regardless of success or failure
            self.lidar_init_complete = True
            logger.info("LiDAR initialization flag set to complete")
        
        if not self.lidar_device:
            logger.error("Failed to initialize LiDAR. LiDAR is required, exiting.")
            return False
            
        self.gps_serial_port = initialize_gps(self.config)
        if not self.gps_serial_port:
            logger.warning("Failed to initialize GPS. Continuing without GPS.")
            
        if not initialize_icm20948(self.i2c_bus, self.config):
            logger.warning("Failed to initialize ICM20948. Continuing without accelerometer data.")
        
        return True

    def _lidar_init_watchdog(self):
        """Watchdog thread that monitors LiDAR initialization and forces restart if stuck"""
        logger.info("LiDAR initialization watchdog started")
        restart_time = self.lidar_init_start_time + LIDAR_CONNECT_TIMEOUT
        
        while not self.lidar_init_complete:
            current_time = time.time()
            # Check if we've exceeded the timeout
            if current_time > restart_time:
                logger.error(f"LiDAR initialization timed out after {LIDAR_CONNECT_TIMEOUT} seconds. Forcing restart...")
                # Sleep a brief moment to allow log message to be written
                time.sleep(0.5)
                # Force restart the application
                self._force_restart()
                # If we're still here, something went wrong with the restart
                # Just exit with a special code
                logger.error("Restart failed, exiting with special code")
                os._exit(RESTART_EXIT_CODE)  # Use os._exit to force immediate termination
            
            # Check more frequently - every 0.2 seconds
            time.sleep(0.2)
            
        logger.info("LiDAR initialization watchdog completed normally")
    
    def _force_restart(self):
        """Force the application to restart using multiple methods"""
        logger.info("⚠️ RESTARTING APPLICATION DUE TO LIDAR TIMEOUT ⚠️")
        print("\n\n⚠️ RESTARTING APPLICATION DUE TO LIDAR TIMEOUT ⚠️\n\n")
        
        # Method 1: Create a restart script and execute it
        try:
            restart_script = """#!/bin/bash
            # Wait for original process to exit
            sleep 1
            # Start the application again
            python {}
            """.format(os.path.abspath(sys.argv[0]))
            
            script_path = "/tmp/restart_road_quality.sh"
            with open(script_path, 'w') as f:
                f.write(restart_script)
            
            os.chmod(script_path, 0o755)
            
            # Execute the script in background
            subprocess.Popen(["bash", script_path], start_new_session=True)
            
            logger.info("Restart script created and executed")
        except Exception as e:
            logger.error(f"Error creating restart script: {e}")
        
        # Method 2: Try the execv approach as backup
        try:
            # Try to perform minimal cleanup
            if hasattr(self, 'lidar_device') and self.lidar_device:
                try:
                    self.lidar_device.stopmotor()
                except:
                    pass
            
            if hasattr(self, 'gps_serial_port') and self.gps_serial_port:
                try:
                    self.gps_serial_port.close()
                except:
                    pass
                    
            if hasattr(self, 'i2c_bus') and self.i2c_bus:
                try:
                    self.i2c_bus.close()
                except:
                    pass
            
            logger.info("Attempting restart via execv...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            logger.error(f"Execv restart failed: {e}")
        
        # Method 3: Simple exit with restart code
        logger.info("Exiting with restart code for external handler...")
        sys.exit(RESTART_EXIT_CODE)

    def start_threads(self):
        """Start data acquisition threads"""
        threads = [
            threading.Thread(target=lidar_thread_func, 
                            args=(self.lidar_device, self.lidar_data_lock, self.lidar_data, 
                                 self.stop_event, self.config), 
                            daemon=True),
            threading.Thread(target=gps_thread_func, 
                            args=(self.gps_serial_port, self.gps_data_lock, self.gps_data, 
                                 self.stop_event, self.config, update_gps_map, self), 
                            daemon=True),
            threading.Thread(target=accel_thread_func, 
                            args=(self.i2c_bus, self.accel_data_lock, self.accel_data, 
                                 self.stop_event, self.config), 
                            daemon=True)
        ]
        
        # Start all threads
        for thread in threads:
            thread.start()
            
        self.threads = threads

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
                
        # Clean up device resources
        if self.lidar_device:
            try:
                self.lidar_device.stopmotor()
                logger.info("LiDAR motor stopped")
            except Exception as e:
                logger.error(f"Error stopping LiDAR motor: {e}")
                
        if self.gps_serial_port:
            try:
                self.gps_serial_port.close()
                logger.info("GPS serial port closed")
            except Exception as e:
                logger.error(f"Error closing GPS serial port: {e}")
                
        if self.i2c_bus:
            try:
                self.i2c_bus.close()
                logger.info("I2C bus closed")
            except Exception as e:
                logger.error(f"Error closing I2C bus: {e}")
                
        logger.info("Cleanup complete")

    def analyze_data(self):
        """Analyze sensor data and update metrics"""
        try:
            with self.accel_data_lock:
                accel_data_copy = list(self.accel_data)
                
            with self.lidar_data_lock:
                lidar_data_copy = list(self.lidar_data)
                
            with self.gps_data_lock:
                gps_data_copy = self.gps_data.copy()
                
            with self.analysis_lock:
                # Log lidar data status for debugging
                if not lidar_data_copy:
                    logger.warning("No LiDAR data available for analysis")
                else:
                    # Count points in center field of view (-10 to 10 degrees)
                    center_points = sum(1 for p in lidar_data_copy if (
                        p[0] >= 0 and p[0] <= 10) or (p[0] >= 350 and p[0] <= 360) or (
                        p[0] >= -10 and p[0] <= 0))
                    
                    logger.debug(f"Analyzing {len(lidar_data_copy)} LiDAR points ({center_points} in center FOV)")
                    
                # Calculate road quality using LiDAR data instead of accelerometer
                quality = self.analyzer.calculate_lidar_road_quality(lidar_data_copy)
                
                # Still detect road events using accelerometer as backup
                events = self.analyzer.detect_road_events(accel_data_copy, gps_data_copy)
                
                # Analyze frequency spectrum
                texture = self.analyzer.analyze_frequency_spectrum(accel_data_copy)
                
                # Log road quality info periodically
                classification = self.analyzer.get_road_classification()
                if events:
                    logger.info(f"Events detected: {len(events)}")
                
                # Always log quality at regular intervals for monitoring
                if hasattr(self, '_log_counter'):
                    self._log_counter += 1
                else:
                    self._log_counter = 0
                    
                if self._log_counter % 10 == 0:  # Log every ~5 seconds at 0.5s interval
                    logger.info(f"Road quality: {quality:.1f}/100 ({classification}), Texture: {texture:.1f}/100")
        except Exception as e:
            logger.error(f"Error in data analysis: {e}")
            import traceback
            logger.error(traceback.format_exc())  # Log the full traceback for debugging

    def analysis_thread_func(self):
        """Thread function for continuous data analysis"""
        logger.info("Analysis thread started")
        while not self.stop_event.is_set():
            self.analyze_data()
            time.sleep(0.5)  # Analysis interval
        logger.info("Analysis thread stopped")

    def run(self):
        """Main function to run the application"""
        self.setup_signal_handler()
        
        if not self.initialize_devices():
            self.cleanup()
            return
        
        # Create default map before starting threads
        create_default_map(self.config)
        
        # Start the threads
        self.start_threads()
        
        # Add a delay to allow threads to initialize and collect initial data
        logger.info("Waiting for sensors to initialize and collect initial data...")
        wait_time = 2  # seconds
        for i in range(wait_time * 2):
            if self.stop_event.is_set():
                break
            time.sleep(0.5)
            # Log progress dots
            if i % 2 == 0:
                print(".", end="", flush=True)
        print("")  # New line after dots
        
        # Start the analysis thread only after initial data collection
        analysis_thread = threading.Thread(
            target=self.analysis_thread_func,
            daemon=True
        )
        analysis_thread.start()
        self.threads.append(analysis_thread)
        
        try:
            # Check if we have any data before proceeding to visualization
            have_lidar_data = False
            have_accel_data = False
            timeout = 5  # Maximum seconds to wait for data
            logger.info("Checking for sensor data...")
            
            for _ in range(timeout * 2):
                with self.lidar_data_lock:
                    have_lidar_data = len(self.lidar_data) > 0
                    
                with self.accel_data_lock:
                    have_accel_data = len(self.accel_data) > 0
                    
                if have_lidar_data and have_accel_data:
                    logger.info("Initial sensor data received, proceeding to visualization")
                    break
                    
                if self.stop_event.is_set():
                    break
                    
                time.sleep(0.5)
                
            if not (have_lidar_data and have_accel_data):
                logger.warning("Timeout waiting for initial sensor data, but proceeding anyway")
            
            logger.info("Setting up visualization...")
            self.fig_lidar, self.fig_accel, self.lidar_ani, self.accel_ani = setup_visualization(
                self.lidar_data, self.lidar_data_lock, 
                self.accel_data, self.accel_data_lock, 
                self.config,
                self.analyzer,
                self.analysis_lock
            )
            
            # Move map opening to a separate thread to prevent blocking
            def open_map_browser():
                try:
                    time.sleep(1)  # Give a moment to ensure file is ready
                    map_url = 'file://' + os.path.abspath(self.config.MAP_HTML_PATH)
                    logger.info(f"Opening map at: {map_url}")
                    if webbrowser.open(map_url):
                        logger.info("Map opened in browser")
                    else:
                        logger.warning("Failed to open browser, but map file was created")
                except Exception as e:
                    logger.error(f"Error opening map in browser: {e}")
            
            # Launch browser in separate thread
            browser_thread = threading.Thread(target=open_map_browser, daemon=True)
            browser_thread.start()
            
            # Use plt.ioff() to avoid keeping windows always on top
            plt.ioff()
            # Show the figures but don't block
            plt.show(block=False)
            
            # Keep the main thread alive but responsive to signals
            while not self.stop_event.is_set():
                plt.pause(0.1)  # Update plots while allowing other operations
                
        except Exception as e:
            logger.error(f"Error in visualization: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            self.cleanup()

if __name__ == '__main__':
    # Add a script-level watchdog to restart for any hanging issues
    # This will handle the case where the watchdog inside SensorFusion doesn't work
    restart_script_path = None
    
    try:
        # Create a watchdog script that will restart the application if it hangs
        watchdog_script = """#!/bin/bash
        # Give the main program time to start
        sleep 20
        # Check if the process is still running
        if ps -p {} >/dev/null; then
            # Process is still running, restart it
            echo "Process still running, killing and restarting..."
            kill -9 {}
            sleep 1
            python {}
        fi
        """.format(os.getpid(), os.getpid(), os.path.abspath(sys.argv[0]))
        
        restart_script_path = "/tmp/watchdog_road_quality_{}.sh".format(os.getpid())
        with open(restart_script_path, 'w') as f:
            f.write(watchdog_script)
        
        os.chmod(restart_script_path, 0o755)
        
        # Execute the watchdog script in background
        subprocess.Popen(["bash", restart_script_path], start_new_session=True)
        
        # Normal execution
        sensor_fusion = SensorFusion()
        sensor_fusion.run()
    except SystemExit as e:
        # Handle the restart exit code
        if e.code == RESTART_EXIT_CODE:
            logger.info("Restarting application due to exit code...")
            # Small delay before restart
            time.sleep(1)
            # Try a more reliable restart method
            try:
                # First try to start a new process
                subprocess.Popen([sys.executable] + sys.argv, start_new_session=True)
                logger.info("Started new process, exiting current process")
                sys.exit(0)
            except:
                # Fall back to execv
                os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            # Clean up the watchdog script before exiting
            if restart_script_path and os.path.exists(restart_script_path):
                try:
                    os.remove(restart_script_path)
                except:
                    pass
            sys.exit(e.code)
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        # Clean up the watchdog script
        if restart_script_path and os.path.exists(restart_script_path):
            try:
                os.remove(restart_script_path)
            except:
                pass
