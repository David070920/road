import numpy as np
import threading
import time
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import QTimer

# Remove unnecessary NavigationToolbar to improve performance
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg

from quality.config import Config
from gui_app.widgets.mpl_canvas import MplCanvas

class LidarChart(QWidget):
    """Widget for LiDAR data visualization with optimized rendering - displays one set at a time"""
    def __init__(self, parent=None):
        super(LidarChart, self).__init__(parent)
        
        # Setup layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Create matplotlib figure (polar) with explicit DPI for better performance
        self.fig = Figure(figsize=(5, 5), dpi=80)
        self.ax = self.fig.add_subplot(111, polar=True)
        
        # Setup the plot - initially empty
        # Changed point size to 5 (from 3) and made them red
        self.scatter = self.ax.scatter([], [], s=5, color='red', lw=0)
        
        # Configure axis
        min_angle = -45 if not hasattr(Config, 'LIDAR_MIN_ANGLE') else Config.LIDAR_MIN_ANGLE
        max_angle = 45 if not hasattr(Config, 'LIDAR_MAX_ANGLE') else Config.LIDAR_MAX_ANGLE
        self.ax.set_thetamin(min_angle)
        self.ax.set_thetamax(max_angle)
        
        # Set maximum distance to 1000mm as requested
        self.max_distance = 1000  # Store as a property for use in processing
        self.ax.set_rmax(self.max_distance)
        
        # Simplify grid for better performance
        self.ax.grid(True, alpha=0.5, linestyle='-', linewidth=0.5)
        self.ax.set_title("LiDAR Data")
        
        # Reduce number of radial ticks for performance
        self.ax.set_yticks([0, 250, 500, 750, 1000])
        
        # Set background color to improve contrast and reduce flickering
        self.fig.patch.set_facecolor('#F0F0F0')
        
        # Canvas - use direct FigureCanvasQTAgg instead of MplCanvas wrapper for better performance
        self.canvas = FigureCanvasQTAgg(self.fig)
        
        # Remove navigation toolbar completely to improve performance
        
        # Add to layout - just the canvas now
        layout.addWidget(self.canvas)
        
        # Tight layout to maximize visualization area
        self.fig.tight_layout()
        
        # Latest measurement data
        self.data_lock = threading.RLock()
        self.latest_data = []  # Will hold the latest complete measurement set
        self.new_data_available = False
        self.last_update_time = time.time()
        
        # Use config values instead of hardcoded ones
        self.update_interval = Config.LIDAR_CHART_UPDATE_INTERVAL  # Time between updates in seconds
        
        # Data processing flags
        self.running = True
        self.paused = False
        
        # Use QTimer for rendering - faster than animation
        self.render_timer = QTimer()
        self.render_timer.timeout.connect(self._check_update)
        
        # Use config value for check interval
        self.render_timer.start(Config.LIDAR_CHART_CHECK_INTERVAL)
        
        # For compatibility with existing code
        self.ani = self  # Make self.ani.pause() work
        
    def pause(self):
        """Pause the visualization"""
        self.paused = True
        self.render_timer.stop()
        
    def resume(self):
        """Resume the visualization"""
        self.paused = False
        self.render_timer.start(Config.LIDAR_CHART_CHECK_INTERVAL)  # Use config value
    
    def _check_update(self):
        """Check if it's time to update the display based on the update interval"""
        current_time = time.time()
        if (not self.paused and 
            self.new_data_available and 
            (current_time - self.last_update_time) >= self.update_interval):
            self._update_display()
            self.last_update_time = current_time
    
    def _update_display(self):
        """Update the display with the latest complete measurement set"""
        if self.paused or not self.new_data_available:
            return
            
        try:
            with self.data_lock:
                if self.latest_data and len(self.latest_data) > 0:
                    # Process data for polar plot
                    angles = []
                    distances = []
                    
                    # Since this is a performance-critical section, use list comprehension instead of loops
                    # Also clamp distances to self.max_distance to enforce y-axis limit
                    processed_data = [(np.radians(angle_deg - 360 if angle_deg >= 315 and angle_deg <= 360 else angle_deg), 
                                      min(distance, self.max_distance))  # Clamp distance to max value
                                     for angle_deg, distance in self.latest_data 
                                     if (0 <= angle_deg <= 45) or (315 <= angle_deg <= 360)]
                    
                    # Only continue if we have data after filtering
                    if processed_data:
                        angles, distances = zip(*processed_data)
                        
                        # Clear previous data
                        self.scatter.remove()
                        
                        # Create new scatter plot with bigger point size and red color
                        self.scatter = self.ax.scatter(
                            angles, 
                            distances, 
                            s=5,  # Increased point size from 3 to 5
                            color='red',  # Set all points to red color
                            lw=0,
                            alpha=0.9  # Slightly more opaque for better visibility
                        )
                        
                        # Ensure rmax is enforced every time
                        self.ax.set_rmax(self.max_distance)
                        
                        # Reset flag
                        self.new_data_available = False
                        
                        # Minimal redraw - use draw_idle for better performance
                        self.fig.canvas.draw_idle()
        except Exception as e:
            print(f"Error updating LiDAR display: {e}")
    
    def add_data_point(self, angle, distance):
        """Legacy method for compatibility - adds a single point"""
        try:
            with self.data_lock:
                if not self.latest_data:
                    self.latest_data = []
                
                # Store original data (don't clamp here - we'll clamp when displaying)
                self.latest_data.append((angle, distance))
                self.new_data_available = True
                
                # Limit points to prevent performance issues
                # Use config value for max points
                if len(self.latest_data) > Config.LIDAR_MAX_POINTS:
                    self.latest_data = self.latest_data[-Config.LIDAR_MAX_POINTS:]
        except Exception as e:
            print(f"Error adding single LiDAR point: {e}")
    
    def add_data_batch(self, points):
        """Add a batch of data points as a complete measurement set"""
        try:
            # Skip processing if we've updated very recently
            current_time = time.time()
            if (current_time - self.last_update_time) < (self.update_interval * 0.5):
                return
                
            with self.data_lock:
                # If points is too large, sample it to improve performance
                if len(points) > Config.LIDAR_MAX_POINTS:  # Use config value
                    step = len(points) // Config.LIDAR_MAX_POINTS
                    self.latest_data = points[::step][:Config.LIDAR_MAX_POINTS]
                else:
                    self.latest_data = points
                self.new_data_available = True
        except Exception as e:
            print(f"Error adding LiDAR data batch: {e}")
            
    def handle_resize(self):
        """Handle widget resize events"""
        self.fig.tight_layout()
        
    def closeEvent(self, event):
        """Clean up resources when widget is closed"""
        self.running = False
        self.render_timer.stop()
        super().closeEvent(event)