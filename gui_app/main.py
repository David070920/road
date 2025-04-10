import sys
import os
import subprocess
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QHBoxLayout, QFileDialog, QMessageBox, QScrollArea
from PyQt5.QtCore import Qt

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from quality.config import Config

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Road Quality Measurement GUI")
        self.setGeometry(100, 100, 1200, 800)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layouts
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)

        # Left panel: Visualization placeholder
        self.visualization_label = QLabel("Visualization will appear here")
        self.visualization_label.setAlignment(Qt.AlignCenter)
        self.visualization_label.setStyleSheet("background-color: #ddd; border: 1px solid #aaa;")
        main_layout.addWidget(self.visualization_label, 3)

        # Right panel: Config controls
        right_panel = QVBoxLayout()
        main_layout.addLayout(right_panel, 1)

        self.load_config_button = QPushButton("Reload Config")
        self.save_config_button = QPushButton("Save Config (not implemented)")
        self.start_button = QPushButton("Start Measurement")
        self.stop_button = QPushButton("Stop Measurement")

        right_panel.addWidget(self.load_config_button)
        right_panel.addWidget(self.save_config_button)
        right_panel.addWidget(self.start_button)
        right_panel.addWidget(self.stop_button)

        # Scroll area for config display
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        right_panel.addWidget(scroll_area, 1)

        self.config_widget = QWidget()
        self.config_layout = QVBoxLayout()
        self.config_widget.setLayout(self.config_layout)
        scroll_area.setWidget(self.config_widget)

        right_panel.addStretch()

        # Connect buttons
        self.load_config_button.clicked.connect(self.load_config)
        self.save_config_button.clicked.connect(self.save_config)
        self.start_button.clicked.connect(self.start_measurement)
        self.stop_button.clicked.connect(self.stop_measurement)

        # Measurement subprocess handle
        self.measurement_process = None

        # Load config on startup
        self.load_config()

    def load_config(self):
        # Clear existing config display
        for i in reversed(range(self.config_layout.count())):
            widget = self.config_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # Display all Config class attributes
        for attr in dir(Config):
            if attr.isupper():
                value = getattr(Config, attr)
                label = QLabel(f"{attr}: {value}")
                label.setStyleSheet("font-family: monospace;")
                self.config_layout.addWidget(label)

    def save_config(self):
        QMessageBox.information(self, "Save Config", "Save config not implemented yet.")

    def start_measurement(self):
        if self.measurement_process and self.measurement_process.poll() is None:
            QMessageBox.warning(self, "Already Running", "Measurement is already running.")
            return

        try:
            run_py_path = os.path.join(project_root, "run.py")
            self.measurement_process = subprocess.Popen(
                [sys.executable, run_py_path],
                cwd=project_root
            )
            QMessageBox.information(self, "Started", "Measurement started.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to start measurement: {e}")

    def stop_measurement(self):
        if self.measurement_process and self.measurement_process.poll() is None:
            try:
                self.measurement_process.terminate()
                self.measurement_process.wait(timeout=5)
                QMessageBox.information(self, "Stopped", "Measurement stopped.")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error stopping measurement: {e}")
        else:
            QMessageBox.information(self, "Not Running", "Measurement is not running.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())