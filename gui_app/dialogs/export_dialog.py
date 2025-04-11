from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QGroupBox, QHBoxLayout,
                         QRadioButton, QCheckBox, QFormLayout, QSpinBox, 
                         QComboBox, QDialogButtonBox, QFileDialog, QMessageBox)
from PyQt5.QtCore import QTimer

class ExportDialog(QDialog):
    """Dialog for exporting road quality data in various formats"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Data")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # File format selection
        format_group = QGroupBox("Export Format")
        format_layout = QVBoxLayout()
        
        self.format_json = QRadioButton("JSON Format")
        self.format_json.setChecked(True)
        self.format_csv = QRadioButton("CSV Format")
        self.format_gpx = QRadioButton("GPX Format (for GPS tracks)")
        
        format_layout.addWidget(self.format_json)
        format_layout.addWidget(self.format_csv)
        format_layout.addWidget(self.format_gpx)
        format_group.setLayout(format_layout)
        
        # Data selection
        data_group = QGroupBox("Data to Export")
        data_layout = QVBoxLayout()
        
        self.data_accel = QCheckBox("Accelerometer Data")
        self.data_accel.setChecked(True)
        self.data_lidar = QCheckBox("LiDAR Data")
        self.data_lidar.setChecked(True)
        self.data_gps = QCheckBox("GPS Coordinates")
        self.data_gps.setChecked(True)
        self.data_events = QCheckBox("Road Events")
        self.data_events.setChecked(True)
        self.data_quality = QCheckBox("Road Quality Scores")
        self.data_quality.setChecked(True)
        
        data_layout.addWidget(self.data_accel)
        data_layout.addWidget(self.data_lidar)
        data_layout.addWidget(self.data_gps)
        data_layout.addWidget(self.data_events)
        data_layout.addWidget(self.data_quality)
        data_group.setLayout(data_layout)
        
        # Time range
        time_group = QGroupBox("Time Range")
        time_layout = QFormLayout()
        
        self.time_all = QRadioButton("All Data")
        self.time_all.setChecked(True)
        self.time_last = QRadioButton("Last")
        self.time_value = QSpinBox()
        self.time_value.setRange(1, 60)
        self.time_value.setValue(5)
        self.time_unit = QComboBox()
        self.time_unit.addItems(["Minutes", "Hours"])
        self.time_unit.setCurrentIndex(0)
        
        time_range_layout = QHBoxLayout()
        time_range_layout.addWidget(self.time_last)
        time_range_layout.addWidget(self.time_value)
        time_range_layout.addWidget(self.time_unit)
        
        time_layout.addRow(self.time_all)
        time_layout.addRow("", time_range_layout)
        time_group.setLayout(time_layout)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        # Add to main layout
        layout.addWidget(format_group)
        layout.addWidget(data_group)
        layout.addWidget(time_group)
        layout.addWidget(buttons)
        
    def accept(self):
        """Handle OK button click"""
        try:
            # Get the file save location
            file_filter = "JSON Files (*.json)" if self.format_json.isChecked() else \
                         "CSV Files (*.csv)" if self.format_csv.isChecked() else \
                         "GPX Files (*.gpx)"
            
            extension = ".json" if self.format_json.isChecked() else \
                       ".csv" if self.format_csv.isChecked() else \
                       ".gpx"
            
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Save Export File",
                f"road_quality_data{extension}",
                file_filter
            )
            
            if not filename:
                return  # User cancelled
                
            # Simulate export process
            self.parent().progress.setVisible(True)
            
            # TODO: Implement actual export functionality
            QTimer.singleShot(500, lambda: self.export_complete(filename))
            
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data: {str(e)}")
            self.parent().progress.setVisible(False)
    
    def export_complete(self, filename):
        """Handle export completion"""
        self.parent().progress.setVisible(False)
        self.parent().log_viewer.append_log(f"Data exported to {filename}", "Info")
        QMessageBox.information(self, "Export Complete", f"Data has been exported to:\n{filename}")
        super().accept()