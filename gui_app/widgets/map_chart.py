import numpy as np
import queue
import threading
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from gui_app.widgets.mpl_canvas import MplCanvas

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