import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

class MplCanvas(FigureCanvas):
    """Canvas for matplotlib figures"""
    def __init__(self, fig):
        self.fig = fig
        super(MplCanvas, self).__init__(self.fig)
        self.setMinimumSize(400, 300)