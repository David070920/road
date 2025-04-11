from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                            QTabWidget, QPushButton, QLineEdit, QCheckBox, QMessageBox)
from PyQt5.QtCore import pyqtSignal

from quality.config import Config

class ConfigEditor(QWidget):
    """Widget for editing configuration values"""
    config_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # Create tabs for different config categories
        self.tabs = QTabWidget()
        
        # Sensors config
        self.sensors_widget = QWidget()
        self.sensors_layout = QFormLayout()
        self.sensors_widget.setLayout(self.sensors_layout)
        
        # Data collection config
        self.data_widget = QWidget()
        self.data_layout = QFormLayout()
        self.data_widget.setLayout(self.data_layout)
        
        # System config
        self.system_widget = QWidget()
        self.system_layout = QFormLayout()
        self.system_widget.setLayout(self.system_layout)
        
        # Add the tabs
        self.tabs.addTab(self.sensors_widget, "Sensors")
        self.tabs.addTab(self.data_widget, "Data Collection")
        self.tabs.addTab(self.system_widget, "System")
        
        self.layout.addWidget(self.tabs)
        
        # Buttons for config actions
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save Changes")
        self.reload_button = QPushButton("Reload Defaults")
        
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.reload_button)
        
        self.layout.addLayout(button_layout)
        
        # Connect signals
        self.save_button.clicked.connect(self.save_config)
        self.reload_button.clicked.connect(self.reload_config)
        
        # Initialize with config values
        self.config_fields = {}
        self.load_config()
        
    def load_config(self):
        """Load configuration into the UI"""
        # Clear existing fields
        self.clear_layout(self.sensors_layout)
        self.clear_layout(self.data_layout)
        self.clear_layout(self.system_layout)
        
        self.config_fields = {}
        
        # Sort attributes into categories
        for attr in dir(Config):
            if not attr.isupper():
                continue
                
            value = getattr(Config, attr)
            
            # Create an appropriate widget based on value type
            if attr.startswith('LIDAR_') or attr.startswith('ACCEL_') or attr.startswith('GPS_'):
                layout = self.sensors_layout
            elif attr.startswith('DATA_') or attr.startswith('QUALITY_'):
                layout = self.data_layout
            else:
                layout = self.system_layout
                
            # Create appropriate editor widget based on type
            if isinstance(value, bool):
                field = QCheckBox()
                field.setChecked(value)
            elif isinstance(value, (int, float)):
                field = QLineEdit(str(value))
            elif isinstance(value, str):
                field = QLineEdit(value)
            else:
                # For complex types, use a non-editable field
                field = QLineEdit(str(value))
                field.setReadOnly(True)
                
            layout.addRow(attr, field)
            self.config_fields[attr] = field
            
    def save_config(self):
        """Save the configuration values"""
        # This is a placeholder - would need to implement actual config saving
        QMessageBox.information(self, "Configuration", "Configuration would be saved here")
        self.config_changed.emit()
        
    def reload_config(self):
        """Reload configuration from source"""
        self.load_config()
        
    def clear_layout(self, layout):
        """Clear all widgets from a layout"""
        if layout is None:
            return
            
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()