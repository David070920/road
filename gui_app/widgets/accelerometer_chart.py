import numpy as np
import queue
import threading
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from quality.config import Config
from gui_app.widgets.mpl_canvas import MplCanvas

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