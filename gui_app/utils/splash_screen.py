from PyQt5.QtWidgets import QSplashScreen
from PyQt5.QtGui import QPixmap, QColor, QFont
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

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