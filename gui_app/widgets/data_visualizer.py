from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QGroupBox, QHBoxLayout, QGridLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt, QSize

from gui_app.widgets.accelerometer_chart import AccelerometerChart
from gui_app.widgets.lidar_chart import LidarChart
from gui_app.widgets.map_chart import MapChart
from gui_app.widgets.events_panel import EventsPanel

class DataVisualizer(QWidget):
    """Widget for visualizing road quality data with real-time charts"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # Enable size policy to make the widget scale properly
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Create tabs for different visualizations
        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Accelerometer tab with real-time chart
        self.accel_widget = QWidget()
        self.accel_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        accel_layout = QVBoxLayout()
        self.accel_chart = AccelerometerChart()
        self.accel_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        accel_layout.addWidget(self.accel_chart)
        self.accel_widget.setLayout(accel_layout)
        
        # LiDAR tab with real-time chart
        self.lidar_widget = QWidget()
        self.lidar_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lidar_layout = QVBoxLayout()
        self.lidar_chart = LidarChart()
        self.lidar_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lidar_layout.addWidget(self.lidar_chart)
        self.lidar_widget.setLayout(lidar_layout)
        
        # Map view tab with GPS track visualization
        self.map_widget = QWidget()
        self.map_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        map_layout = QVBoxLayout()
        self.map_chart = MapChart()
        self.map_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        map_layout.addWidget(self.map_chart)
        self.map_widget.setLayout(map_layout)
        
        # Events tab with road events panel
        self.events_widget = EventsPanel()
        self.events_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Add tabs
        self.tabs.addTab(self.accel_widget, "Accelerometer")
        self.tabs.addTab(self.lidar_widget, "LiDAR")
        self.tabs.addTab(self.map_widget, "Map View")
        self.tabs.addTab(self.events_widget, "Events")
        
        self.layout.addWidget(self.tabs)
        
        # Quality indicator
        quality_group = QGroupBox("Road Quality Score")
        quality_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
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
        
        # Make quality group height fixed to prevent it from taking too much space
        quality_group.setMaximumHeight(150)
        
        self.layout.addWidget(quality_group)
        
    def sizeHint(self):
        """Provide size hint for proper scaling"""
        return QSize(800, 600)  # Default recommended size
        
    def minimumSizeHint(self):
        """Provide minimum size hint for proper scaling"""
        return QSize(400, 300)  # Minimum usable size
        
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
    
    def update_lidar_data(self, data):
        """Update LiDAR chart with new data - can handle both single points and batches"""
        if isinstance(data, tuple) and len(data) == 2:
            # Legacy mode - single point (angle, distance)
            angle, distance = data
            self.lidar_chart.add_data_point(angle, distance)
        else:
            # New batch mode - data is a list of points
            self.lidar_chart.add_data_batch(data)
    
    def update_gps_data(self, lat, lon):
        """Update map with new GPS point"""
        self.map_chart.add_gps_point(lat, lon)
        
    def resizeEvent(self, event):
        """Handle resize events to adjust chart sizes"""
        super().resizeEvent(event)
        
        # Notify charts to adjust their sizes if they have a resize method
        if hasattr(self.accel_chart, 'handle_resize'):
            self.accel_chart.handle_resize()
            
        if hasattr(self.lidar_chart, 'handle_resize'):
            self.lidar_chart.handle_resize()
            
        if hasattr(self.map_chart, 'handle_resize'):
            self.map_chart.handle_resize()