from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QWidget,
                         QFormLayout, QSlider, QComboBox, QCheckBox,
                         QLineEdit, QPushButton, QHBoxLayout, QFileDialog,
                         QDialogButtonBox)
from PyQt5.QtCore import Qt

class SettingsDialog(QDialog):
    """Dialog for application settings"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Create tabs for different settings
        tabs = QTabWidget()
        
        # Display settings tab
        display_tab = QWidget()
        display_layout = QFormLayout()
        
        # Chart settings
        self.chart_smoothing = QSlider(Qt.Horizontal)
        self.chart_smoothing.setRange(0, 10)
        self.chart_smoothing.setValue(5)
        self.chart_smoothing.setTickPosition(QSlider.TicksBelow)
        
        # Update frequency
        self.update_frequency = QComboBox()
        self.update_frequency.addItems(["1 second", "2 seconds", "5 seconds"])
        self.update_frequency.setCurrentIndex(1)  # default to 2 seconds
        
        display_layout.addRow("Chart Smoothing:", self.chart_smoothing)
        display_layout.addRow("Update Frequency:", self.update_frequency)
        display_tab.setLayout(display_layout)
        
        # Notification settings tab
        notif_tab = QWidget()
        notif_layout = QVBoxLayout()
        
        self.notify_events = QCheckBox("Road Event Notifications")
        self.notify_events.setChecked(True)
        self.notify_sensors = QCheckBox("Sensor Status Changes")
        self.notify_quality = QCheckBox("Quality Score Changes")
        self.notify_quality.setChecked(True)
        
        notif_layout.addWidget(self.notify_events)
        notif_layout.addWidget(self.notify_sensors)
        notif_layout.addWidget(self.notify_quality)
        notif_layout.addStretch()
        notif_tab.setLayout(notif_layout)
        
        # Storage settings tab
        storage_tab = QWidget()
        storage_layout = QFormLayout()
        
        self.auto_export = QCheckBox("Auto-export data")
        self.export_path = QLineEdit()
        self.export_path.setPlaceholderText("Select data export path...")
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.select_export_path)
        
        self.storage_format = QComboBox()
        self.storage_format.addItems(["JSON", "CSV", "Both"])
        
        browse_layout = QHBoxLayout()
        browse_layout.addWidget(self.export_path, 1)
        browse_layout.addWidget(self.browse_btn)
        
        storage_layout.addRow("Auto-export:", self.auto_export)
        storage_layout.addRow("Export path:", browse_layout)
        storage_layout.addRow("Storage format:", self.storage_format)
        
        storage_tab.setLayout(storage_layout)
        
        # Add tabs
        tabs.addTab(display_tab, "Display")
        tabs.addTab(notif_tab, "Notifications")
        tabs.addTab(storage_tab, "Storage")
        layout.addWidget(tabs)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply_settings)
        layout.addWidget(buttons)
        
        # Load current settings
        self.load_settings()
        
    def load_settings(self):
        """Load settings from config"""
        # In a real app, you would load these from a settings file
        pass
        
    def apply_settings(self):
        """Apply settings without closing dialog"""
        self.save_settings()
        self.parent().log_viewer.append_log("Settings applied", "Info")
        
    def accept(self):
        """Handle OK button click"""
        self.save_settings()
        super().accept()
        
    def save_settings(self):
        """Save settings to config"""
        # In a real app, you would save these to a settings file
        smoothing = self.chart_smoothing.value() / 10.0
        update_freq = self.update_frequency.currentText()
        
        # Apply chart smoothing to existing charts
        try:
            self.parent().data_viz.accel_chart.ani.event_source.interval = int(update_freq.split()[0]) * 1000
            self.parent().data_viz.lidar_chart.ani.event_source.interval = int(update_freq.split()[0]) * 1000 * 2
        except Exception as e:
            print(f"Error applying settings: {e}")
        
    def select_export_path(self):
        """Open directory selection dialog for export path"""
        path = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if path:
            self.export_path.setText(path)