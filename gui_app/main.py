import sys
import os
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QLabel, QHBoxLayout, QMessageBox, QTabWidget, 
                            QProgressBar, QToolBar, QAction, QStatusBar, QStyleFactory)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QColor, QPalette

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import our modular components
from gui_app.utils.splash_screen import SplashScreen
from gui_app.core.sensor_data_reader import SensorDataReader
from gui_app.widgets.sensor_status_widget import SensorStatusWidget
from gui_app.widgets.data_visualizer import DataVisualizer
from gui_app.widgets.config_editor import ConfigEditor
from gui_app.widgets.log_viewer import LogViewer
from gui_app.widgets.website_panel import WebsitePanel
from gui_app.dialogs.export_dialog import ExportDialog
from gui_app.dialogs.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Road Quality Measurement GUI")
        self.setGeometry(100, 100, 1200, 800)
        
        # Set application style to Fusion for a more modern look
        QApplication.setStyle(QStyleFactory.create('Fusion'))
        
        # Set up the status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # Set up the toolbar
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)
        
        # Add actions to toolbar with icons
        self.start_action = QAction(QIcon.fromTheme("media-playback-start", QIcon("icons/start.png")), "Start", self)
        self.start_action.triggered.connect(self.start_measurement)
        self.start_action.setShortcut("Ctrl+S")
        self.toolbar.addAction(self.start_action)
        
        self.stop_action = QAction(QIcon.fromTheme("media-playback-stop", QIcon("icons/stop.png")), "Stop", self)
        self.stop_action.triggered.connect(self.stop_measurement)
        self.stop_action.setShortcut("Ctrl+X")
        self.toolbar.addAction(self.stop_action)
        
        self.toolbar.addSeparator()
        
        self.theme_action = QAction(QIcon.fromTheme("preferences-desktop-theme", QIcon("icons/theme.png")), "Toggle Theme", self)
        self.theme_action.triggered.connect(self.toggle_theme)
        self.theme_action.setShortcut("Ctrl+T")
        self.toolbar.addAction(self.theme_action)
        
        # Add export actions
        self.toolbar.addSeparator()
        self.export_action = QAction(QIcon.fromTheme("document-save-as", QIcon("icons/export.png")), "Export Data", self)
        self.export_action.triggered.connect(self.export_data)
        self.toolbar.addAction(self.export_action)
        
        # Add settings action
        self.toolbar.addSeparator()
        self.settings_action = QAction(QIcon.fromTheme("preferences-system", QIcon("icons/settings.png")), "Settings", self)
        self.settings_action.triggered.connect(self.open_settings)
        self.toolbar.addAction(self.settings_action)
        
        # Add help action
        self.toolbar.addSeparator()
        self.help_action = QAction(QIcon.fromTheme("help-browser", QIcon("icons/help.png")), "Help", self)
        self.help_action.triggered.connect(self.show_help)
        self.help_action.setShortcut("F1")
        self.toolbar.addAction(self.help_action)
        
        # Central widget with tab interface
        self.central_tabs = QTabWidget()
        self.setCentralWidget(self.central_tabs)
        
        # Dashboard tab
        self.dashboard = QWidget()
        dashboard_layout = QVBoxLayout()
        
        # Top area with sensor status
        self.sensor_status = SensorStatusWidget()
        dashboard_layout.addWidget(self.sensor_status)
        
        # Data visualization area
        self.data_viz = DataVisualizer()
        dashboard_layout.addWidget(self.data_viz, 1)
        
        self.dashboard.setLayout(dashboard_layout)
        
        # Configuration tab
        self.config_editor = ConfigEditor()
        
        # Logs tab
        self.log_viewer = LogViewer()
        
        # Website tab
        self.website_panel = WebsitePanel()
        
        # Add tabs to main interface with icons
        self.central_tabs.addTab(self.dashboard, QIcon.fromTheme("view-grid", QIcon("icons/dashboard.png")), "Dashboard")
        self.central_tabs.addTab(self.config_editor, QIcon.fromTheme("preferences-system", QIcon("icons/settings.png")), "Configuration")
        self.central_tabs.addTab(self.log_viewer, QIcon.fromTheme("text-x-log", QIcon("icons/logs.png")), "Logs")
        self.central_tabs.addTab(self.website_panel, QIcon.fromTheme("internet-web-browser", QIcon("icons/website.png")), "Website")
        
        # Connection status in status bar
        self.connection_status = QLabel("Not Connected")
        self.connection_status.setStyleSheet("color: #e74c3c;")
        self.statusBar.addPermanentWidget(self.connection_status)
        
        # Create sensor data reader thread
        self.sensor_reader = SensorDataReader()
        
        # Connect signals from sensor reader
        self.sensor_reader.accel_data_signal.connect(self.data_viz.update_accel_data)
        self.sensor_reader.lidar_data_signal.connect(self.data_viz.update_lidar_data)
        self.sensor_reader.gps_data_signal.connect(self.data_viz.update_gps_data)
        self.sensor_reader.sensor_status_signal.connect(self.sensor_status.update_status)
        self.sensor_reader.log_signal.connect(self.log_viewer.append_log)
        self.sensor_reader.env_data_signal.connect(self.update_env_data)
        
        # Flag for data collection state
        self.is_collecting = False
        
        # Add environmental data widgets
        self.env_temp_label = QLabel("--")
        self.env_humidity_label = QLabel("--")
        self.env_pressure_label = QLabel("--")
        self.env_altitude_label = QLabel("--")
        self.statusBar.addWidget(QLabel("Temp:"))
        self.statusBar.addWidget(self.env_temp_label)
        self.statusBar.addWidget(QLabel("Humidity:"))
        self.statusBar.addWidget(self.env_humidity_label)
        self.statusBar.addWidget(QLabel("Pressure:"))
        self.statusBar.addWidget(self.env_pressure_label)
        self.statusBar.addWidget(QLabel("Alt:"))
        self.statusBar.addWidget(self.env_altitude_label)
        
        # Add system info to status bar
        self.system_info = QLabel("CPU: -- | RAM: --")
        self.statusBar.addPermanentWidget(self.system_info)
        
        # Start system info update timer
        self.system_timer = QTimer()
        self.system_timer.timeout.connect(self.update_system_info)
        self.system_timer.start(5000)  # Update every 5 seconds
        
        # Add progress bar to show activity
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate progress
        self.progress.setFixedWidth(100)
        self.progress.setVisible(False)  # Only show when processing
        self.statusBar.addPermanentWidget(self.progress)
        
        # Apply initial theme
        self.dark_theme = False
        self.toggle_theme()
        
        # Add initial test log
        self.log_viewer.append_log("GUI initialized successfully")
        self.log_viewer.append_log("Real sensor data integration enabled")
        
    # Add new methods for the actions we added
    def export_data(self):
        """Show export options dialog"""
        export_dialog = ExportDialog(self)
        export_dialog.exec_()
    
    def open_settings(self):
        """Open settings dialog"""
        settings_dialog = SettingsDialog(self)
        settings_dialog.exec_()
    
    def show_help(self):
        """Show help information"""
        QMessageBox.information(
            self, 
            "Road Quality Measurement Help",
            "Road Quality Measurement Tool\n\n"
            "This application allows you to collect and analyze road quality data using sensors:\n\n"
            "- Start/Stop: Begin or end data collection\n"
            "- Dashboard: View real-time sensor data and quality scores\n"
            "- Configuration: Adjust system settings\n"
            "- Logs: View system messages and events\n\n"
            "For more information, visit the documentation."
        )
    
    def update_system_info(self):
        """Update system information in the status bar"""
        try:
            # This is a simplified version - in a real app you'd use psutil or similar
            cpu_usage = "25%"  # Placeholder
            ram_usage = "512MB"  # Placeholder
            self.system_info.setText(f"CPU: {cpu_usage} | RAM: {ram_usage}")
        except Exception as e:
            self.log_viewer.append_log(f"Error updating system info: {str(e)}", "Error")
        
    def toggle_theme(self):
        """Toggle between light and dark themes"""
        self.dark_theme = not self.dark_theme
        
        if self.dark_theme:
            # Set dark theme
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.WindowText, Qt.white)
            palette.setColor(QPalette.Base, QColor(25, 25, 25))
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ToolTipBase, Qt.white)
            palette.setColor(QPalette.ToolTipText, Qt.white)
            palette.setColor(QPalette.Text, Qt.white)
            palette.setColor(QPalette.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ButtonText, Qt.white)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, Qt.black)
            self.setPalette(palette)
            self.log_viewer.append_log("Dark theme enabled")
        else:
            # Set light theme (default)
            self.setPalette(QApplication.style().standardPalette())
            self.log_viewer.append_log("Light theme enabled")
    
    def update_env_data(self, env_data):
        """Update environmental data displays"""
        if env_data['temperature'] is not None:
            self.env_temp_label.setText(f"{env_data['temperature']:.1f}°C")
        
        if env_data['humidity'] is not None:
            self.env_humidity_label.setText(f"{env_data['humidity']:.1f}%")
            
        if env_data['pressure'] is not None:
            self.env_pressure_label.setText(f"{env_data['pressure']:.1f} hPa")
            
        if env_data['altitude'] is not None:
            self.env_altitude_label.setText(f"{env_data['altitude']:.1f} m")

    def start_measurement(self):
        """Start sensor data collection"""
        if self.is_collecting:
            QMessageBox.warning(self, "Already Running", "Measurement is already running.")
            return
        
        try:
            # Start the sensor reader thread
            self.log_viewer.append_log("Starting sensor data collection...")
            
            # Start in safe mode if we're running without hardware
            self.sensor_reader.safe_mode = True  # Set to False to use real hardware if available
            
            # Start the thread
            self.sensor_reader.start()
            self.is_collecting = True
            
            # Update connection status
            self.connection_status.setText("Connected - Collecting Data")
            self.connection_status.setStyleSheet("color: #2ecc71;")
            
        except Exception as e:
            self.log_viewer.append_log(f"Failed to start measurement: {str(e)}", "Error")
            QMessageBox.warning(self, "Error", f"Failed to start measurement: {e}")

    def stop_measurement(self):
        """Stop sensor data collection"""
        if not self.is_collecting:
            QMessageBox.information(self, "Not Running", "Measurement is not running.")
            return
        
        try:
            # Stop the sensor reader thread
            self.log_viewer.append_log("Stopping sensor data collection...")
            self.sensor_reader.stop()
            self.is_collecting = False
            
            # Update connection status
            self.connection_status.setText("Not Connected")
            self.connection_status.setStyleSheet("color: #e74c3c;")
            
        except Exception as e:
            self.log_viewer.append_log(f"Error stopping measurement: {str(e)}", "Error")
            QMessageBox.warning(self, "Error", f"Error stopping measurement: {e}")
    
    def closeEvent(self, event):
        """Handle application close event"""
        if self.is_collecting:
            self.stop_measurement()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Show splash screen
    splash = SplashScreen()
    splash.show()
    
    # Simulate loading stages
    for i, message in enumerate([
        "Initializing application...",
        "Loading configuration...",
        "Preparing user interface...",
        "Connecting to sensors...",
        "Starting system..."
    ]):
        # Update splash message
        splash.show_message(message)
        # Process events to update UI
        app.processEvents()
        # Simulate work being done
        time.sleep(0.5)
    
    # Create and show main window
    window = MainWindow()
    
    # Finish splash and show main window
    splash.finish(window)
    window.show()
    
    # Start the application
    sys.exit(app.exec_())