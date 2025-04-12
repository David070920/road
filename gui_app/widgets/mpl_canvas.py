import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtCore import QSize

class MplCanvas(FigureCanvas):
    """Canvas for matplotlib figures"""
    def __init__(self, fig):
        self.fig = fig
        super(MplCanvas, self).__init__(self.fig)
        
        # Configure for responsive sizing
        self.setMinimumSize(300, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Enable figure to adjust with window size
        self.fig.tight_layout()
        
        # Set higher DPI for better appearance on high-resolution displays
        self.fig.set_dpi(100)  # Higher DPI for sharper rendering

    def sizeHint(self):
        """Provide size hint for better layout management"""
        return QSize(600, 400)
        
    def handle_resize(self):
        """Handle resize events explicitly"""
        # Update the figure size to match the canvas size
        width, height = self.get_width_height()
        # Apply DPI-aware sizing
        self.fig.set_size_inches(width/self.fig.get_dpi(), height/self.fig.get_dpi())
        # Readjust the layout
        self.fig.tight_layout()
        self.draw()
        
    def get_width_height(self):
        """Get the width and height in pixels"""
        return self.width(), self.height()