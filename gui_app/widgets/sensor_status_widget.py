from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout

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