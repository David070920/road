import numpy as np
import queue
import threading
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from quality.config import Config
from gui_app.widgets.mpl_canvas import MplCanvas

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