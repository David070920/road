import sys
import os
import subprocess
import datetime
import threading
import queue
import time
import json
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QPushButton, QLabel, QHBoxLayout, QFileDialog, 
                            QMessageBox, QScrollArea, QTabWidget, QGridLayout, 
                            QLineEdit, QFormLayout, QGroupBox, QCheckBox,
                            QComboBox, QTextEdit, QProgressBar, QSplitter,
                            QFrame, QToolBar, QAction, QStatusBar, QStyleFactory,
                            QAbstractItemView, QListWidget, QListWidgetItem, QDialogButtonBox, QDialog, QRadioButton, QSpinBox, QSlider, QSplashScreen)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QUrl
from PyQt5.QtGui import QIcon, QColor, QPalette, QFont, QDesktopServices, QPixmap

# Matplotlib integration
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from quality.config import Config
from quality.visualization.accel_plots import update_accel_plot
from quality.visualization.lidar_plots import update_lidar_plot
from quality.core.sensor_fusion import SensorFusion
from quality.analysis.road_quality_analyzer import RoadQualityAnalyzer

class SplashScreen(QSplashScreen):
    """Custom splash screen with progress indicator"""
    def __init__(self):
        # Create a basic splash image if none exists
        splash_pixmap = QPixmap(400, 300)
        splash_pixmap.fill(QColor("#3559e0"))  # Blue background matching web theme
        
        super(SplashScreen, self).__init__(splash_pixmap)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        
        # Add title and version
        self.setFont(QFont("Arial", 12))
        self.showMessage("Road Quality Measurement System", 
                         Qt.AlignHCenter | Qt.AlignBottom, Qt.white)
        
        # Add progress text
        self.progress_text = ""
        
    def show_message(self, message):
        """Update splash screen message"""
        self.progress_text = message
        self.showMessage(f"Road Quality Measurement System\n\n{self.progress_text}", 
                         Qt.AlignHCenter | Qt.AlignBottom, Qt.white)
        QApplication.processEvents()

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


class MplCanvas(FigureCanvas):
    """Canvas for matplotlib figures"""
    def __init__(self, fig):
        self.fig = fig
        super(MplCanvas, self).__init__(self.fig)
        self.setMinimumSize(400, 300)


class AccelerometerChart(QWidget):
    """Widget for accelerometer data visualization"""
    def __init__(self, parent=None):
        super(AccelerometerChart, self).__init__(parent)
        
        # Setup layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Create matplotlib figure
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        
        # Setup the plot
        self.data_points = Config.MAX_DATA_POINTS if hasattr(Config, 'MAX_DATA_POINTS') else 100
        self.x_data = np.arange(self.data_points)
        self.y_data = np.zeros(self.data_points)
        
        self.line, = self.ax.plot(self.x_data, self.y_data, 'b-', label='Acceleration (Z)')
        
        self.ax.set_xlim(0, self.data_points - 1)
        self.ax.set_ylim(-2, 2)
        self.ax.set_title("Accelerometer Data")
        self.ax.set_xlabel("Sample")
        self.ax.set_ylabel("Acceleration (g)")
        self.ax.grid(True)
        self.ax.legend(loc='upper right')
        
        # Create quality score axis
        self.ax_quality = self.ax.twinx()
        self.ax_quality.set_ylabel("Road Quality Score")
        self.ax_quality.set_ylim(0, 100)
        self.ax_quality.spines['right'].set_color('green')
        self.ax_quality.tick_params(axis='y', colors='green')
        self.ax_quality.yaxis.label.set_color('green')
        
        # Canvas
        self.canvas = MplCanvas(self.fig)
        
        # Navigation toolbar
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        # Add to layout
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        # Set up data queue
        self.data_queue = queue.Queue(maxsize=100)
        self.data_lock = threading.Lock()
        
        # Setup animation
        self.ani = animation.FuncAnimation(
            self.fig, 
            self.update_plot, 
            interval=100, 
            blit=True, 
            cache_frame_data=False
        )
        
    def update_plot(self, frame):
        """Update the plot with new data"""
        # Get data from queue if available
        try:
            data_points = []
            while not self.data_queue.empty() and len(data_points) < 10:
                data_points.append(self.data_queue.get_nowait())
                self.data_queue.task_done()
                
            if data_points:
                with self.data_lock:
                    # Shift existing data to make room for new points
                    self.y_data = np.roll(self.y_data, -len(data_points))
                    
                    # Add new points
                    self.y_data[-len(data_points):] = data_points
                    
                    # Update the plot
                    self.line.set_ydata(self.y_data)
        except Exception as e:
            print(f"Error updating accel plot: {e}")
            
        return self.line,
    
    def add_data_point(self, value, quality_score=None, classification=None):
        """Add a new data point to the queue"""
        try:
            self.data_queue.put_nowait(value)
            
            # Update quality score and classification if provided
            if quality_score is not None:
                self.ax.set_title(f"Accelerometer Data | Road Quality: {quality_score:.1f}/100 ({classification or 'Unknown'})")
                
                # Change line color based on quality
                if quality_score >= 75:  # Good
                    self.line.set_color('green')
                elif 50 <= quality_score < 75:  # Fair
                    self.line.set_color('orange')
                else:  # Poor
                    self.line.set_color('red')
        except queue.Full:
            # Queue is full, discard oldest data point
            try:
                self.data_queue.get_nowait()
                self.data_queue.put_nowait(value)
            except Exception:
                pass


class LidarChart(QWidget):
    """Widget for LiDAR data visualization"""
    def __init__(self, parent=None):
        super(LidarChart, self).__init__(parent)
        
        # Setup layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Create matplotlib figure (polar)
        self.fig, self.ax = plt.subplots(subplot_kw={'polar': True}, figsize=(6, 6))
        
        # Setup the plot
        self.scatter = self.ax.scatter([0, 0], [0, 0], s=5, c=[0, 0], cmap=plt.cm.Greys_r, lw=0)
        
        # Configure axis
        min_angle = -45 if not hasattr(Config, 'LIDAR_MIN_ANGLE') else Config.LIDAR_MIN_ANGLE
        max_angle = 45 if not hasattr(Config, 'LIDAR_MAX_ANGLE') else Config.LIDAR_MAX_ANGLE
        self.ax.set_thetamin(min_angle)
        self.ax.set_thetamax(max_angle)
        self.ax.set_rmax(1000)  # Maximum distance in mm
        
        self.ax.grid(True)
        self.ax.set_title("LiDAR Data (90° FOV)")
        
        # Canvas
        self.canvas = MplCanvas(self.fig)
        
        # Navigation toolbar
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        # Add to layout
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        # Set up data queue and lock
        self.data_queue = queue.Queue(maxsize=100)
        self.data_lock = threading.Lock()
        
        # Setup animation
        self.ani = animation.FuncAnimation(
            self.fig, 
            self.update_plot, 
            interval=200, 
            blit=True,
            cache_frame_data=False
        )
        
    def update_plot(self, frame):
        """Update the plot with new data"""
        try:
            # Get data from queue if available
            lidar_points = []
            while not self.data_queue.empty() and len(lidar_points) < 100:
                point = self.data_queue.get_nowait()
                lidar_points.append(point)
                self.data_queue.task_done()
                
            if lidar_points:
                with self.data_lock:
                    # Process for polar plot
                    polar_data = []
                    for point in lidar_points:
                        angle_deg = point[0]
                        distance = point[1]
                        
                        # Convert 315-360 degrees to -45-0 degrees for the polar plot
                        if angle_deg >= 315 and angle_deg <= 360:
                            angle_deg = angle_deg - 360
                        
                        # Only include angles in our desired range
                        if -45 <= angle_deg <= 45:
                            polar_data.append((np.radians(angle_deg), distance))
                    
                    if polar_data:
                        # Convert to numpy arrays
                        angles = np.array([point[0] for point in polar_data])
                        distances = np.array([point[1] for point in polar_data])
                        
                        # Update the scatter plot
                        offsets = np.column_stack((angles, distances))
                        self.scatter.set_offsets(offsets)
                        
                        # Color points based on distance
                        # Simple coloring by distance
                        intensity = distances / 1000.0 * 50  # Scale to colormap range
                        self.scatter.set_array(intensity)
        except Exception as e:
            print(f"Error updating LiDAR plot: {e}")
            
        return self.scatter,
    
    def add_data_point(self, angle, distance):
        """Add a new data point to the queue"""
        try:
            self.data_queue.put_nowait((angle, distance))
        except queue.Full:
            # Queue is full, discard oldest data point
            try:
                self.data_queue.get_nowait()
                self.data_queue.put_nowait((angle, distance))
            except Exception:
                pass


class MapChart(QWidget):
    """Widget for GPS/Map visualization"""
    def __init__(self, parent=None):
        super(MapChart, self).__init__(parent)
        
        # Setup layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Create matplotlib figure
        self.fig, self.ax = plt.subplots(figsize=(6, 6))
        
        # Setup the plot with placeholder
        self.ax.set_xlim(-100, 100)
        self.ax.set_ylim(-100, 100)
        self.ax.grid(True)
        self.ax.set_title("GPS Track")
        self.ax.set_xlabel("Longitude Offset (m)")
        self.ax.set_ylabel("Latitude Offset (m)")
        
        # Initial plot with empty data
        self.track_line, = self.ax.plot([], [], 'b-', label='Vehicle Path')
        self.current_pos, = self.ax.plot([], [], 'ro', markersize=8, label='Current Position')
        
        self.ax.legend(loc='upper right')
        
        # Canvas
        self.canvas = MplCanvas(self.fig)
        
        # Navigation toolbar
        self.toolbar = NavigationToolbar(self.canvas, self)
        
        # Add to layout
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        # Store GPS track points
        self.track_x = []
        self.track_y = []
        self.origin = (0, 0)  # Origin point for relative positioning
        
        # Set up data queue and lock
        self.data_queue = queue.Queue(maxsize=100)
        self.data_lock = threading.Lock()
        
        # Setup animation
        self.ani = animation.FuncAnimation(
            self.fig, 
            self.update_plot, 
            interval=500,
            blit=True,
            cache_frame_data=False
        )
        
    def update_plot(self, frame):
        """Update the plot with new GPS data"""
        try:
            # Get data from queue if available
            gps_points = []
            while not self.data_queue.empty():
                point = self.data_queue.get_nowait()
                gps_points.append(point)
                self.data_queue.task_done()
                
            if gps_points:
                with self.data_lock:
                    # Process new points
                    for lat, lon in gps_points:
                        # Set origin if this is the first point
                        if not self.track_x and not self.track_y:
                            self.origin = (lat, lon)
                            
                        # Convert to relative coordinates in meters
                        x, y = self.gps_to_meters(lat, lon)
                        
                        self.track_x.append(x)
                        self.track_y.append(y)
                    
                    # Update track line
                    self.track_line.set_data(self.track_x, self.track_y)
                    
                    # Update current position (last point)
                    if self.track_x and self.track_y:
                        self.current_pos.set_data([self.track_x[-1]], [self.track_y[-1]])
                        
                        # Auto-adjust plot limits to show all data
                        padding = 10  # meters
                        min_x, max_x = min(self.track_x), max(self.track_x)
                        min_y, max_y = min(self.track_y), max(self.track_y)
                        
                        x_range = max(20, max_x - min_x + 2*padding)
                        y_range = max(20, max_y - min_y + 2*padding)
                        
                        center_x = (min_x + max_x) / 2
                        center_y = (min_y + max_y) / 2
                        
                        self.ax.set_xlim(center_x - x_range/2, center_x + x_range/2)
                        self.ax.set_ylim(center_y - y_range/2, center_y + y_range/2)
        except Exception as e:
            print(f"Error updating map plot: {e}")
            
        return self.track_line, self.current_pos
    
    def gps_to_meters(self, lat, lon):
        """Convert GPS coordinates to meters from origin"""
        # Simple conversion (approximate for small distances)
        lat_origin, lon_origin = self.origin
        
        # Constants for conversion
        lat_meters = 111320  # meters per degree of latitude
        lon_meters = 111320 * np.cos(np.radians(lat_origin))  # meters per degree of longitude
        
        # Calculate meters from origin
        x = (lon - lon_origin) * lon_meters
        y = (lat - lat_origin) * lat_meters
        
        return x, y
    
    def add_gps_point(self, lat, lon):
        """Add a new GPS point to the queue"""
        try:
            self.data_queue.put_nowait((lat, lon))
        except queue.Full:
            # Queue is full, discard oldest point
            try:
                self.data_queue.get_nowait()
                self.data_queue.put_nowait((lat, lon))
            except Exception:
                pass


class SensorStatusWidget(QWidget):
    """Widget to display sensor connection status similar to web interface"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        
        # Create status indicators
        self.create_indicator("LiDAR", "lidar_status")
        self.create_indicator("Accel", "accel_status")
        self.create_indicator("GPS", "gps_status")
        self.create_indicator("Env", "env_status")
        
        # Set all to disconnected initially
        self.update_status("lidar_status", False)
        self.update_status("accel_status", False)
        self.update_status("gps_status", False)
        self.update_status("env_status", False)
        
    def create_indicator(self, name, obj_name):
        group = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 0, 5, 0)
        
        # Status indicator (circular color dot)
        indicator = QLabel()
        indicator.setFixedSize(10, 10)
        indicator.setObjectName(obj_name)
        indicator.setStyleSheet("background-color: #e74c3c; border-radius: 5px;")
        
        label = QLabel(name)
        
        layout.addWidget(indicator)
        layout.addWidget(label)
        group.setLayout(layout)
        
        self.layout.addWidget(group)
        
    def update_status(self, sensor_name, is_connected):
        indicator = self.findChild(QLabel, sensor_name)
        if indicator:
            color = "#2ecc71" if is_connected else "#e74c3c"  # Green if connected, red if not
            indicator.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
            

class DataVisualizer(QWidget):
    """Widget for visualizing road quality data with real-time charts"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # Create tabs for different visualizations
        self.tabs = QTabWidget()
        
        # Accelerometer tab with real-time chart
        self.accel_widget = QWidget()
        accel_layout = QVBoxLayout()
        self.accel_chart = AccelerometerChart()
        accel_layout.addWidget(self.accel_chart)
        self.accel_widget.setLayout(accel_layout)
        
        # LiDAR tab with real-time chart
        self.lidar_widget = QWidget()
        lidar_layout = QVBoxLayout()
        self.lidar_chart = LidarChart()
        lidar_layout.addWidget(self.lidar_chart)
        self.lidar_widget.setLayout(lidar_layout)
        
        # Map view tab with GPS track visualization
        self.map_widget = QWidget()
        map_layout = QVBoxLayout()
        self.map_chart = MapChart()
        map_layout.addWidget(self.map_chart)
        self.map_widget.setLayout(map_layout)
        
        # Events tab with road events panel
        self.events_widget = EventsPanel()
        
        # Add tabs
        self.tabs.addTab(self.accel_widget, "Accelerometer")
        self.tabs.addTab(self.lidar_widget, "LiDAR")
        self.tabs.addTab(self.map_widget, "Map View")
        self.tabs.addTab(self.events_widget, "Events")
        
        self.layout.addWidget(self.tabs)
        
        # Quality indicator
        quality_group = QGroupBox("Road Quality Score")
        quality_layout = QHBoxLayout()
        
        # Quality gauge
        self.quality_value = QLabel("--")
        self.quality_value.setStyleSheet("font-size: 32pt; font-weight: bold; color: #3498db;")
        self.quality_value.setAlignment(Qt.AlignCenter)
        
        self.quality_classification = QLabel("No Data")
        self.quality_classification.setStyleSheet("font-size: 14pt;")
        self.quality_classification.setAlignment(Qt.AlignCenter)
        
        quality_gauge_layout = QVBoxLayout()
        quality_gauge_layout.addWidget(self.quality_value)
        quality_gauge_layout.addWidget(self.quality_classification)
        
        # Quality status grid
        quality_status_layout = QGridLayout()
        
        # Add status indicators similar to web interface
        road_quality = QLabel("Road Quality")
        road_quality.setAlignment(Qt.AlignCenter)
        accelerometer = QLabel("Accelerometer")
        accelerometer.setAlignment(Qt.AlignCenter)
        lidar = QLabel("LiDAR")
        lidar.setAlignment(Qt.AlignCenter)
        
        quality_status_layout.addWidget(road_quality, 0, 0)
        quality_status_layout.addWidget(accelerometer, 0, 1)
        quality_status_layout.addWidget(lidar, 0, 2)
        
        quality_layout.addLayout(quality_gauge_layout, 1)
        quality_layout.addLayout(quality_status_layout, 2)
        
        quality_group.setLayout(quality_layout)
        
        self.layout.addWidget(quality_group)
        
    def update_accel_data(self, value, quality_score=None, classification=None):
        """Update accelerometer chart with new data"""
        self.accel_chart.add_data_point(value, quality_score, classification)
        
        # Also update quality indicators if provided
        if quality_score is not None:
            self.quality_value.setText(f"{quality_score:.1f}")
            self.quality_classification.setText(classification or "Unknown")
            
            # Update color based on quality
            if quality_score >= 75:  # Good
                self.quality_value.setStyleSheet("font-size: 32pt; font-weight: bold; color: #2ecc71;")
            elif 50 <= quality_score < 75:  # Fair
                self.quality_value.setStyleSheet("font-size: 32pt; font-weight: bold; color: #f39c12;")
            else:  # Poor
                self.quality_value.setStyleSheet("font-size: 32pt; font-weight: bold; color: #e74c3c;")
    
    def update_lidar_data(self, angle, distance):
        """Update LiDAR chart with new data point"""
        self.lidar_chart.add_data_point(angle, distance)
    
    def update_gps_data(self, lat, lon):
        """Update map with new GPS point"""
        self.map_chart.add_gps_point(lat, lon)


class ConfigEditor(QWidget):
    """Widget for editing configuration values"""
    config_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # Create tabs for different config categories
        self.tabs = QTabWidget()
        
        # Sensors config
        self.sensors_widget = QWidget()
        self.sensors_layout = QFormLayout()
        self.sensors_widget.setLayout(self.sensors_layout)
        
        # Data collection config
        self.data_widget = QWidget()
        self.data_layout = QFormLayout()
        self.data_widget.setLayout(self.data_layout)
        
        # System config
        self.system_widget = QWidget()
        self.system_layout = QFormLayout()
        self.system_widget.setLayout(self.system_layout)
        
        # Add the tabs
        self.tabs.addTab(self.sensors_widget, "Sensors")
        self.tabs.addTab(self.data_widget, "Data Collection")
        self.tabs.addTab(self.system_widget, "System")
        
        self.layout.addWidget(self.tabs)
        
        # Buttons for config actions
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save Changes")
        self.reload_button = QPushButton("Reload Defaults")
        
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.reload_button)
        
        self.layout.addLayout(button_layout)
        
        # Connect signals
        self.save_button.clicked.connect(self.save_config)
        self.reload_button.clicked.connect(self.reload_config)
        
        # Initialize with config values
        self.config_fields = {}
        self.load_config()
        
    def load_config(self):
        """Load configuration into the UI"""
        # Clear existing fields
        self.clear_layout(self.sensors_layout)
        self.clear_layout(self.data_layout)
        self.clear_layout(self.system_layout)
        
        self.config_fields = {}
        
        # Sort attributes into categories
        for attr in dir(Config):
            if not attr.isupper():
                continue
                
            value = getattr(Config, attr)
            
            # Create an appropriate widget based on value type
            if attr.startswith('LIDAR_') or attr.startswith('ACCEL_') or attr.startswith('GPS_'):
                layout = self.sensors_layout
            elif attr.startswith('DATA_') or attr.startswith('QUALITY_'):
                layout = self.data_layout
            else:
                layout = self.system_layout
                
            # Create appropriate editor widget based on type
            if isinstance(value, bool):
                field = QCheckBox()
                field.setChecked(value)
            elif isinstance(value, (int, float)):
                field = QLineEdit(str(value))
            elif isinstance(value, str):
                field = QLineEdit(value)
            else:
                # For complex types, use a non-editable field
                field = QLineEdit(str(value))
                field.setReadOnly(True)
                
            layout.addRow(attr, field)
            self.config_fields[attr] = field
            
    def save_config(self):
        """Save the configuration values"""
        # This is a placeholder - would need to implement actual config saving
        QMessageBox.information(self, "Configuration", "Configuration would be saved here")
        self.config_changed.emit()
        
    def reload_config(self):
        """Reload configuration from source"""
        self.load_config()
        
    def clear_layout(self, layout):
        """Clear all widgets from a layout"""
        if layout is None:
            return
            
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()


class LogViewer(QWidget):
    """Widget for displaying logs and events"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Controls
        controls = QHBoxLayout()
        self.log_level = QComboBox()
        self.log_level.addItems(["All", "Info", "Warning", "Error"])
        self.clear_button = QPushButton("Clear")
        
        controls.addWidget(QLabel("Log Level:"))
        controls.addWidget(self.log_level)
        controls.addWidget(self.clear_button)
        controls.addStretch()
        
        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        
        layout.addLayout(controls)
        layout.addWidget(self.log_text)
        
        # Connect signals
        self.clear_button.clicked.connect(self.log_text.clear)
        
    def append_log(self, message, level="Info"):
        """Add a new log message"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        color = {
            "Info": "black",
            "Warning": "#f39c12",
            "Error": "#e74c3c"
        }.get(level, "black")
        
        self.log_text.append(f'<span style="color:gray;">[{timestamp}]</span> <span style="color:{color};">{message}</span>')
        
    def load_log_file(self, file_path):
        """Load and display log file content"""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                self.log_text.setPlainText(content)
        except Exception as e:
            self.log_text.setPlainText(f"Error loading log file: {str(e)}")


class ExportDialog(QDialog):
    """Dialog for exporting road quality data in various formats"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Data")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # File format selection
        format_group = QGroupBox("Export Format")
        format_layout = QVBoxLayout()
        
        self.format_json = QRadioButton("JSON Format")
        self.format_json.setChecked(True)
        self.format_csv = QRadioButton("CSV Format")
        self.format_gpx = QRadioButton("GPX Format (for GPS tracks)")
        
        format_layout.addWidget(self.format_json)
        format_layout.addWidget(self.format_csv)
        format_layout.addWidget(self.format_gpx)
        format_group.setLayout(format_layout)
        
        # Data selection
        data_group = QGroupBox("Data to Export")
        data_layout = QVBoxLayout()
        
        self.data_accel = QCheckBox("Accelerometer Data")
        self.data_accel.setChecked(True)
        self.data_lidar = QCheckBox("LiDAR Data")
        self.data_lidar.setChecked(True)
        self.data_gps = QCheckBox("GPS Coordinates")
        self.data_gps.setChecked(True)
        self.data_events = QCheckBox("Road Events")
        self.data_events.setChecked(True)
        self.data_quality = QCheckBox("Road Quality Scores")
        self.data_quality.setChecked(True)
        
        data_layout.addWidget(self.data_accel)
        data_layout.addWidget(self.data_lidar)
        data_layout.addWidget(self.data_gps)
        data_layout.addWidget(self.data_events)
        data_layout.addWidget(self.data_quality)
        data_group.setLayout(data_layout)
        
        # Time range
        time_group = QGroupBox("Time Range")
        time_layout = QFormLayout()
        
        self.time_all = QRadioButton("All Data")
        self.time_all.setChecked(True)
        self.time_last = QRadioButton("Last")
        self.time_value = QSpinBox()
        self.time_value.setRange(1, 60)
        self.time_value.setValue(5)
        self.time_unit = QComboBox()
        self.time_unit.addItems(["Minutes", "Hours"])
        self.time_unit.setCurrentIndex(0)
        
        time_range_layout = QHBoxLayout()
        time_range_layout.addWidget(self.time_last)
        time_range_layout.addWidget(self.time_value)
        time_range_layout.addWidget(self.time_unit)
        
        time_layout.addRow(self.time_all)
        time_layout.addRow("", time_range_layout)
        time_group.setLayout(time_layout)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        # Add to main layout
        layout.addWidget(format_group)
        layout.addWidget(data_group)
        layout.addWidget(time_group)
        layout.addWidget(buttons)
        
    def accept(self):
        """Handle OK button click"""
        try:
            # Get the file save location
            file_filter = "JSON Files (*.json)" if self.format_json.isChecked() else \
                         "CSV Files (*.csv)" if self.format_csv.isChecked() else \
                         "GPX Files (*.gpx)"
            
            extension = ".json" if self.format_json.isChecked() else \
                       ".csv" if self.format_csv.isChecked() else \
                       ".gpx"
            
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Save Export File",
                f"road_quality_data{extension}",
                file_filter
            )
            
            if not filename:
                return  # User cancelled
                
            # Simulate export process
            self.parent().progress.setVisible(True)
            QApplication.processEvents()
            
            # TODO: Implement actual export functionality
            QTimer.singleShot(500, lambda: self.export_complete(filename))
            
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data: {str(e)}")
            self.parent().progress.setVisible(False)
    
    def export_complete(self, filename):
        """Handle export completion"""
        self.parent().progress.setVisible(False)
        self.parent().log_viewer.append_log(f"Data exported to {filename}", "Info")
        QMessageBox.information(self, "Export Complete", f"Data has been exported to:\n{filename}")
        super().accept()


class EventsPanel(QWidget):
    """Widget to display and manage road events similar to web interface"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Filter controls
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Filter:"))
        self.event_filter = QComboBox()
        self.event_filter.addItems(["All Events", "Potholes", "Bumps", "LiDAR Events", "Accelerometer Events"])
        self.event_filter.currentTextChanged.connect(self.filter_events)
        filter_layout.addWidget(self.event_filter)
        
        self.event_search = QLineEdit()
        self.event_search.setPlaceholderText("Search events...")
        self.event_search.textChanged.connect(self.filter_events)
        filter_layout.addWidget(self.event_search)
        
        layout.addLayout(filter_layout)
        
        # Events list
        self.events_list = QListWidget()
        self.events_list.setAlternatingRowColors(True)
        self.events_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.events_list.itemClicked.connect(self.show_event_details)
        layout.addWidget(self.events_list)
        
        # Export buttons
        export_layout = QHBoxLayout()
        
        export_json_btn = QPushButton("Export JSON")
        export_csv_btn = QPushButton("Export CSV")
        export_gpx_btn = QPushButton("Export GPX")
        
        export_json_btn.clicked.connect(self.export_to_json)
        export_csv_btn.clicked.connect(self.export_to_csv)
        export_gpx_btn.clicked.connect(self.export_to_gpx)
        
        export_layout.addWidget(export_json_btn)
        export_layout.addWidget(export_csv_btn)
        export_layout.addWidget(export_gpx_btn)
        export_layout.addStretch()
        
        layout.addLayout(export_layout)
        
        # Sample events data for testing
        self.events = [
            {"id": 1, "type": "Pothole", "severity": 8, "lat": 37.7749, "lon": -122.4194, "timestamp": "2025-04-10 14:23:45", "source": "LiDAR"},
            {"id": 2, "type": "Bump", "severity": 5, "lat": 37.7750, "lon": -122.4195, "timestamp": "2025-04-10 14:25:12", "source": "Accelerometer"},
            {"id": 3, "type": "Rough Surface", "severity": 6, "lat": 37.7751, "lon": -122.4196, "timestamp": "2025-04-10 14:27:30", "source": "LiDAR"}
        ]
        
        # Populate events list
        self.populate_events()
    
    def populate_events(self):
        """Populate the events list with event data"""
        self.events_list.clear()
        
        if not self.events:
            self.events_list.addItem("No road events detected")
            return
            
        for event in self.events:
            item_text = f"{event['type']} (Severity: {event['severity']}) - {event['source']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, event)
            
            # Set item colors based on severity
            if event['severity'] >= 8:
                item.setForeground(QColor("#e74c3c"))  # Red for high severity
            elif event['severity'] >= 5:
                item.setForeground(QColor("#f39c12"))  # Orange for medium severity
            else:
                item.setForeground(QColor("#2ecc71"))  # Green for low severity
                
            self.events_list.addItem(item)
    
    def filter_events(self):
        """Filter events based on selected filter and search text"""
        filter_text = self.event_filter.currentText()
        search_text = self.event_search.text().lower()
        
        self.events_list.clear()
        
        filtered_events = []
        for event in self.events:
            # Apply filter
            if filter_text == "All Events" or \
               (filter_text == "Potholes" and event['type'] == "Pothole") or \
               (filter_text == "Bumps" and event['type'] == "Bump") or \
               (filter_text == "LiDAR Events" and event['source'] == "LiDAR") or \
               (filter_text == "Accelerometer Events" and event['source'] == "Accelerometer"):
                
                # Apply search
                if search_text == "" or \
                   search_text in event['type'].lower() or \
                   search_text in event['source'].lower() or \
                   search_text in str(event['severity']):
                    filtered_events.append(event)
        
        # Show filtered events
        if not filtered_events:
            self.events_list.addItem("No matching events found")
            return
            
        for event in filtered_events:
            item_text = f"{event['type']} (Severity: {event['severity']}) - {event['source']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, event)
            
            # Set item colors based on severity
            if event['severity'] >= 8:
                item.setForeground(QColor("#e74c3c"))  # Red for high severity
            elif event['severity'] >= 5:
                item.setForeground(QColor("#f39c12"))  # Orange for medium severity
            else:
                item.setForeground(QColor("#2ecc71"))  # Green for low severity
                
            self.events_list.addItem(item)
    
    def show_event_details(self, item):
        """Show details for the selected event"""
        event = item.data(Qt.UserRole)
        if not event:
            return
            
        msg = QMessageBox()
        msg.setWindowTitle("Event Details")
        
        msg.setText(f"<b>{event['type']} Event</b>")
        
        details = f"""
        <table>
            <tr>
                <td><b>Severity:</b></td>
                <td>{event['severity']}/10</td>
            </tr>
            <tr>
                <td><b>Source:</b></td>
                <td>{event['source']}</td>
            </tr>
            <tr>
                <td><b>Location:</b></td>
                <td>{event['lat']:.6f}, {event['lon']:.6f}</td>
            </tr>
            <tr>
                <td><b>Timestamp:</b></td>
                <td>{event['timestamp']}</td>
            </tr>
        </table>
        """
        
        msg.setInformativeText(details)
        
        # Add action buttons
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Apply)
        msg.button(QMessageBox.Apply).setText("Show on Map")
        
        # Custom styling for the message box
        msg.setStyleSheet("QLabel{min-width: 300px;}")
        
        result = msg.exec_()
        if result == QMessageBox.Apply:
            # Show on map functionality would go here
            pass
    
    def add_event(self, event):
        """Add a new event to the list"""
        self.events.append(event)
        self.populate_events()
        
        # Show notification for important events
        if event['severity'] >= 7:
            self.show_notification(event)
    
    def show_notification(self, event):
        """Show a notification for a high-severity event"""
        msg = QMessageBox()
        msg.setWindowTitle("Road Event Detected")
        
        if event['type'].lower() == "pothole":
            msg.setIcon(QMessageBox.Warning)
            msg.setText(f"Pothole Detected (Severity: {event['severity']})")
        else:
            msg.setIcon(QMessageBox.Information)
            msg.setText(f"Road Event: {event['type']} (Severity: {event['severity']})")
        
        msg.setInformativeText(f"Location: {event['lat']:.6f}, {event['lon']:.6f}\nSource: {event['source']}")
        msg.setStandardButtons(QMessageBox.Ok)
        
        # Non-blocking notification
        QTimer.singleShot(0, msg.show)
    
    def export_to_json(self):
        """Export events data to JSON format"""
        if not self.events:
            QMessageBox.warning(self, "No Data", "No events data to export.")
            return
            
        filename, _ = QFileDialog.getSaveFileName(self, "Export JSON", "", "JSON Files (*.json)")
        if not filename:
            return
            
        try:
            with open(filename, 'w') as f:
                json.dump({"events": self.events}, f, indent=2)
                
            QMessageBox.information(self, "Export Successful", f"Events data exported to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data: {str(e)}")
    
    def export_to_csv(self):
        """Export events data to CSV format"""
        if not self.events:
            QMessageBox.warning(self, "No Data", "No events data to export.")
            return
            
        filename, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv)")
        if not filename:
            return
            
        try:
            with open(filename, 'w') as f:
                # Write header
                f.write("id,type,severity,latitude,longitude,timestamp,source\n")
                
                # Write data rows
                for event in self.events:
                    f.write(f"{event['id']},{event['type']},{event['severity']},{event['lat']},{event['lon']},{event['timestamp']},{event['source']}\n")
                
            QMessageBox.information(self, "Export Successful", f"Events data exported to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data: {str(e)}")
    
    def export_to_gpx(self):
        """Export events data to GPX format for GPS visualization"""
        if not self.events:
            QMessageBox.warning(self, "No Data", "No events data to export.")
            return
            
        filename, _ = QFileDialog.getSaveFileName(self, "Export GPX", "", "GPX Files (*.gpx)")
        if not filename:
            return
            
        try:
            with open(filename, 'w') as f:
                # Write GPX header
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write('<gpx version="1.1" creator="Road Quality App" xmlns="http://www.topografix.com/GPX/1/1">\n')
                
                # Write waypoints for each event
                for event in self.events:
                    f.write(f'  <wpt lat="{event["lat"]}" lon="{event["lon"]}">\n')
                    f.write(f'    <name>{event["type"]} (S{event["severity"]})</name>\n')
                    f.write(f'    <desc>Severity: {event["severity"]}, Source: {event["source"]}</desc>\n')
                    f.write(f'    <time>{event["timestamp"]}</time>\n')
                    f.write('  </wpt>\n')
                
                # Close GPX file
                f.write('</gpx>\n')
                
            QMessageBox.information(self, "Export Successful", f"Events data exported to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data: {str(e)}")


class SettingsDialog(QDialog):
    """Dialog for application settings"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Create tabs for different settings
        tabs = QTabWidget()
        
        # Display settings tab
        display_tab = QWidget()
        display_layout = QFormLayout()
        
        # Chart settings
        self.chart_smoothing = QSlider(Qt.Horizontal)
        self.chart_smoothing.setRange(0, 10)
        self.chart_smoothing.setValue(5)
        self.chart_smoothing.setTickPosition(QSlider.TicksBelow)
        
        # Update frequency
        self.update_frequency = QComboBox()
        self.update_frequency.addItems(["1 second", "2 seconds", "5 seconds"])
        self.update_frequency.setCurrentIndex(1)  # default to 2 seconds
        
        display_layout.addRow("Chart Smoothing:", self.chart_smoothing)
        display_layout.addRow("Update Frequency:", self.update_frequency)
        display_tab.setLayout(display_layout)
        
        # Notification settings tab
        notif_tab = QWidget()
        notif_layout = QVBoxLayout()
        
        self.notify_events = QCheckBox("Road Event Notifications")
        self.notify_events.setChecked(True)
        self.notify_sensors = QCheckBox("Sensor Status Changes")
        self.notify_quality = QCheckBox("Quality Score Changes")
        self.notify_quality.setChecked(True)
        
        notif_layout.addWidget(self.notify_events)
        notif_layout.addWidget(self.notify_sensors)
        notif_layout.addWidget(self.notify_quality)
        notif_layout.addStretch()
        notif_tab.setLayout(notif_layout)
        
        # Storage settings tab
        storage_tab = QWidget()
        storage_layout = QFormLayout()
        
        self.auto_export = QCheckBox("Auto-export data")
        self.export_path = QLineEdit()
        self.export_path.setPlaceholderText("Select data export path...")
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.select_export_path)
        
        self.storage_format = QComboBox()
        self.storage_format.addItems(["JSON", "CSV", "Both"])
        
        browse_layout = QHBoxLayout()
        browse_layout.addWidget(self.export_path, 1)
        browse_layout.addWidget(self.browse_btn)
        
        storage_layout.addRow("Auto-export:", self.auto_export)
        storage_layout.addRow("Export path:", browse_layout)
        storage_layout.addRow("Storage format:", self.storage_format)
        
        storage_tab.setLayout(storage_layout)
        
        # Add tabs
        tabs.addTab(display_tab, "Display")
        tabs.addTab(notif_tab, "Notifications")
        tabs.addTab(storage_tab, "Storage")
        layout.addWidget(tabs)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply_settings)
        layout.addWidget(buttons)
        
        # Load current settings
        self.load_settings()
        
    def load_settings(self):
        """Load settings from config"""
        # In a real app, you would load these from a settings file
        pass
        
    def apply_settings(self):
        """Apply settings without closing dialog"""
        self.save_settings()
        self.parent().log_viewer.append_log("Settings applied", "Info")
        
    def accept(self):
        """Handle OK button click"""
        self.save_settings()
        super().accept()
        
    def save_settings(self):
        """Save settings to config"""
        # In a real app, you would save these to a settings file
        smoothing = self.chart_smoothing.value() / 10.0
        update_freq = self.update_frequency.currentText()
        
        # Apply chart smoothing to existing charts
        self.parent().data_viz.accel_chart.ani.event_source.interval = int(update_freq.split()[0]) * 1000
        self.parent().data_viz.lidar_chart.ani.event_source.interval = int(update_freq.split()[0]) * 1000 * 2
        
    def select_export_path(self):
        """Open directory selection dialog for export path"""
        path = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if path:
            self.export_path.setText(path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Road Quality Measurement GUI")
        self.setGeometry(100, 100, 1200, 800)
        
        # Set application style to Fusion for a more modern look
        QApplication.setStyle(QStyleFactory.create('Fusion'))
        
        # Set up the status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # Set up the toolbar
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)
        
        # Add actions to toolbar with icons
        self.start_action = QAction(QIcon.fromTheme("media-playback-start", QIcon("icons/start.png")), "Start", self)
        self.start_action.triggered.connect(self.start_measurement)
        self.start_action.setShortcut("Ctrl+S")
        self.toolbar.addAction(self.start_action)
        
        self.stop_action = QAction(QIcon.fromTheme("media-playback-stop", QIcon("icons/stop.png")), "Stop", self)
        self.stop_action.triggered.connect(self.stop_measurement)
        self.stop_action.setShortcut("Ctrl+X")
        self.toolbar.addAction(self.stop_action)
        
        self.toolbar.addSeparator()
        
        self.theme_action = QAction(QIcon.fromTheme("preferences-desktop-theme", QIcon("icons/theme.png")), "Toggle Theme", self)
        self.theme_action.triggered.connect(self.toggle_theme)
        self.theme_action.setShortcut("Ctrl+T")
        self.toolbar.addAction(self.theme_action)
        
        # Add export actions
        self.toolbar.addSeparator()
        self.export_action = QAction(QIcon.fromTheme("document-save-as", QIcon("icons/export.png")), "Export Data", self)
        self.export_action.triggered.connect(self.export_data)
        self.toolbar.addAction(self.export_action)
        
        # Add settings action
        self.toolbar.addSeparator()
        self.settings_action = QAction(QIcon.fromTheme("preferences-system", QIcon("icons/settings.png")), "Settings", self)
        self.settings_action.triggered.connect(self.open_settings)
        self.toolbar.addAction(self.settings_action)
        
        # Add help action
        self.toolbar.addSeparator()
        self.help_action = QAction(QIcon.fromTheme("help-browser", QIcon("icons/help.png")), "Help", self)
        self.help_action.triggered.connect(self.show_help)
        self.help_action.setShortcut("F1")
        self.toolbar.addAction(self.help_action)
        
        # Central widget with tab interface
        self.central_tabs = QTabWidget()
        self.setCentralWidget(self.central_tabs)
        
        # Dashboard tab
        self.dashboard = QWidget()
        dashboard_layout = QVBoxLayout()
        
        # Top area with sensor status
        self.sensor_status = SensorStatusWidget()
        dashboard_layout.addWidget(self.sensor_status)
        
        # Data visualization area
        self.data_viz = DataVisualizer()
        dashboard_layout.addWidget(self.data_viz, 1)
        
        self.dashboard.setLayout(dashboard_layout)
        
        # Configuration tab
        self.config_editor = ConfigEditor()
        
        # Logs tab
        self.log_viewer = LogViewer()
        
        # Add tabs to main interface with icons
        self.central_tabs.addTab(self.dashboard, QIcon.fromTheme("view-grid", QIcon("icons/dashboard.png")), "Dashboard")
        self.central_tabs.addTab(self.config_editor, QIcon.fromTheme("preferences-system", QIcon("icons/settings.png")), "Configuration")
        self.central_tabs.addTab(self.log_viewer, QIcon.fromTheme("text-x-log", QIcon("icons/logs.png")), "Logs")
        
        # Connection status in status bar
        self.connection_status = QLabel("Not Connected")
        self.connection_status.setStyleSheet("color: #e74c3c;")
        self.statusBar.addPermanentWidget(self.connection_status)
        
        # Create sensor data reader thread
        self.sensor_reader = SensorDataReader()
        
        # Connect signals from sensor reader
        self.sensor_reader.accel_data_signal.connect(self.data_viz.update_accel_data)
        self.sensor_reader.lidar_data_signal.connect(self.data_viz.update_lidar_data)
        self.sensor_reader.gps_data_signal.connect(self.data_viz.update_gps_data)
        self.sensor_reader.sensor_status_signal.connect(self.sensor_status.update_status)
        self.sensor_reader.log_signal.connect(self.log_viewer.append_log)
        self.sensor_reader.env_data_signal.connect(self.update_env_data)
        
        # Flag for data collection state
        self.is_collecting = False
        
        # Add environmental data widgets
        self.env_temp_label = QLabel("--")
        self.env_humidity_label = QLabel("--")
        self.env_pressure_label = QLabel("--")
        self.env_altitude_label = QLabel("--")
        self.statusBar.addWidget(QLabel("Temp:"))
        self.statusBar.addWidget(self.env_temp_label)
        self.statusBar.addWidget(QLabel("Humidity:"))
        self.statusBar.addWidget(self.env_humidity_label)
        self.statusBar.addWidget(QLabel("Pressure:"))
        self.statusBar.addWidget(self.env_pressure_label)
        self.statusBar.addWidget(QLabel("Alt:"))
        self.statusBar.addWidget(self.env_altitude_label)
        
        # Add system info to status bar
        self.system_info = QLabel("CPU: -- | RAM: --")
        self.statusBar.addPermanentWidget(self.system_info)
        
        # Start system info update timer
        self.system_timer = QTimer()
        self.system_timer.timeout.connect(self.update_system_info)
        self.system_timer.start(5000)  # Update every 5 seconds
        
        # Add progress bar to show activity
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate progress
        self.progress.setFixedWidth(100)
        self.progress.setVisible(False)  # Only show when processing
        self.statusBar.addPermanentWidget(self.progress)
        
        # Apply initial theme
        self.dark_theme = False
        self.toggle_theme()
        
        # Add initial test log
        self.log_viewer.append_log("GUI initialized successfully")
        self.log_viewer.append_log("Real sensor data integration enabled")
        
    # Add new methods for the actions we added
    def export_data(self):
        """Show export options dialog"""
        export_dialog = ExportDialog(self)
        export_dialog.exec_()
    
    def open_settings(self):
        """Open settings dialog"""
        settings_dialog = SettingsDialog(self)
        settings_dialog.exec_()
    
    def show_help(self):
        """Show help information"""
        QMessageBox.information(
            self, 
            "Road Quality Measurement Help",
            "Road Quality Measurement Tool\n\n"
            "This application allows you to collect and analyze road quality data using sensors:\n\n"
            "- Start/Stop: Begin or end data collection\n"
            "- Dashboard: View real-time sensor data and quality scores\n"
            "- Configuration: Adjust system settings\n"
            "- Logs: View system messages and events\n\n"
            "For more information, visit the documentation."
        )
    
    def update_system_info(self):
        """Update system information in the status bar"""
        try:
            # This is a simplified version - in a real app you'd use psutil or similar
            cpu_usage = "25%"  # Placeholder
            ram_usage = "512MB"  # Placeholder
            self.system_info.setText(f"CPU: {cpu_usage} | RAM: {ram_usage}")
        except Exception as e:
            self.log_viewer.append_log(f"Error updating system info: {str(e)}", "Error")
        
    def toggle_theme(self):
        """Toggle between light and dark themes"""
        self.dark_theme = not self.dark_theme
        
        if self.dark_theme:
            # Set dark theme
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.WindowText, Qt.white)
            palette.setColor(QPalette.Base, QColor(25, 25, 25))
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ToolTipBase, Qt.white)
            palette.setColor(QPalette.ToolTipText, Qt.white)
            palette.setColor(QPalette.Text, Qt.white)
            palette.setColor(QPalette.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ButtonText, Qt.white)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, Qt.black)
            self.setPalette(palette)
            self.log_viewer.append_log("Dark theme enabled")
        else:
            # Set light theme (default)
            self.setPalette(QApplication.style().standardPalette())
            self.log_viewer.append_log("Light theme enabled")
    
    def update_env_data(self, env_data):
        """Update environmental data displays"""
        if env_data['temperature'] is not None:
            self.env_temp_label.setText(f"{env_data['temperature']:.1f}°C")
        
        if env_data['humidity'] is not None:
            self.env_humidity_label.setText(f"{env_data['humidity']:.1f}%")
            
        if env_data['pressure'] is not None:
            self.env_pressure_label.setText(f"{env_data['pressure']:.1f} hPa")
            
        if env_data['altitude'] is not None:
            self.env_altitude_label.setText(f"{env_data['altitude']:.1f} m")

    def start_measurement(self):
        """Start sensor data collection"""
        if self.is_collecting:
            QMessageBox.warning(self, "Already Running", "Measurement is already running.")
            return
        
        try:
            # Start the sensor reader thread
            self.log_viewer.append_log("Starting sensor data collection...")
            
            # Start in safe mode if we're running without hardware
            self.sensor_reader.safe_mode = True  # Set to False to use real hardware if available
            
            # Start the thread
            self.sensor_reader.start()
            self.is_collecting = True
            
            # Update connection status
            self.connection_status.setText("Connected - Collecting Data")
            self.connection_status.setStyleSheet("color: #2ecc71;")
            
        except Exception as e:
            self.log_viewer.append_log(f"Failed to start measurement: {str(e)}", "Error")
            QMessageBox.warning(self, "Error", f"Failed to start measurement: {e}")

    def stop_measurement(self):
        """Stop sensor data collection"""
        if not self.is_collecting:
            QMessageBox.information(self, "Not Running", "Measurement is not running.")
            return
        
        try:
            # Stop the sensor reader thread
            self.log_viewer.append_log("Stopping sensor data collection...")
            self.sensor_reader.stop()
            self.is_collecting = False
            
            # Update connection status
            self.connection_status.setText("Not Connected")
            self.connection_status.setStyleSheet("color: #e74c3c;")
            
        except Exception as e:
            self.log_viewer.append_log(f"Error stopping measurement: {str(e)}", "Error")
            QMessageBox.warning(self, "Error", f"Error stopping measurement: {e}")
    
    def closeEvent(self, event):
        """Handle application close event"""
        if self.is_collecting:
            self.stop_measurement()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Show splash screen
    splash = SplashScreen()
    splash.show()
    
    # Simulate loading stages
    for i, message in enumerate([
        "Initializing application...",
        "Loading configuration...",
        "Preparing user interface...",
        "Connecting to sensors...",
        "Starting system..."
    ]):
        # Update splash message
        splash.show_message(message)
        # Process events to update UI
        app.processEvents()
        # Simulate work being done
        time.sleep(0.5)
    
    # Create and show main window
    window = MainWindow()
    
    # Finish splash and show main window
    splash.finish(window)
    window.show()
    
    # Start the application
    sys.exit(app.exec_())