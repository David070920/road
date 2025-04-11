import datetime
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QTextEdit

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