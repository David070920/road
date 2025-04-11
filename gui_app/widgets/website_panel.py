import os
import requests
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QGroupBox, QLineEdit, QFormLayout)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QImage

class WebsitePanel(QWidget):
    """Widget for displaying web server links and QR codes"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # Local URL section
        local_group = QGroupBox("Local Access")
        local_layout = QVBoxLayout()
        
        self.local_url_label = QLineEdit()
        self.local_url_label.setReadOnly(True)
        self.local_url_label.setText("Loading local URL...")
        
        local_button_layout = QHBoxLayout()
        open_local_button = QPushButton("Open in Browser")
        open_local_button.clicked.connect(self.open_local_url)
        copy_local_button = QPushButton("Copy URL")
        copy_local_button.clicked.connect(lambda: self.copy_to_clipboard(self.local_url_label.text()))
        
        local_button_layout.addWidget(open_local_button)
        local_button_layout.addWidget(copy_local_button)
        
        local_layout.addWidget(QLabel("Local network access URL:"))
        local_layout.addWidget(self.local_url_label)
        local_layout.addLayout(local_button_layout)
        local_group.setLayout(local_layout)
        
        # Remote URL section
        remote_group = QGroupBox("Remote Access (Ngrok)")
        remote_layout = QVBoxLayout()
        
        self.remote_status_label = QLabel("Remote access status: Checking...")
        self.remote_url_label = QLineEdit()
        self.remote_url_label.setReadOnly(True)
        self.remote_url_label.setText("Loading remote URL...")
        
        remote_button_layout = QHBoxLayout()
        open_remote_button = QPushButton("Open in Browser")
        open_remote_button.clicked.connect(self.open_remote_url)
        copy_remote_button = QPushButton("Copy URL")
        copy_remote_button.clicked.connect(lambda: self.copy_to_clipboard(self.remote_url_label.text()))
        
        remote_button_layout.addWidget(open_remote_button)
        remote_button_layout.addWidget(copy_remote_button)
        
        # QR Code
        qr_layout = QHBoxLayout()
        self.qr_label = QLabel("QR Code will appear here")
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumSize(200, 200)
        self.qr_label.setStyleSheet("background-color: white;")
        qr_layout.addWidget(self.qr_label)
        
        remote_layout.addWidget(self.remote_status_label)
        remote_layout.addWidget(QLabel("Remote access URL:"))
        remote_layout.addWidget(self.remote_url_label)
        remote_layout.addLayout(remote_button_layout)
        remote_layout.addWidget(QLabel("Scan with mobile device:"))
        remote_layout.addLayout(qr_layout)
        remote_group.setLayout(remote_layout)
        
        # Refresh button
        refresh_layout = QHBoxLayout()
        refresh_button = QPushButton("Refresh Status")
        refresh_button.clicked.connect(self.refresh_status)
        refresh_layout.addStretch()
        refresh_layout.addWidget(refresh_button)
        
        # Main layout
        self.layout.addWidget(local_group)
        self.layout.addWidget(remote_group)
        self.layout.addLayout(refresh_layout)
        self.layout.addStretch(1)
        
        # Start auto refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_status)
        self.refresh_timer.start(10000)  # Refresh every 10 seconds
        
        # Initial status check
        self.refresh_status()
        
    def refresh_status(self):
        """Refresh the status of local and remote URLs"""
        try:
            # Check if web server is running before attempting to get status
            if self.is_server_running():
                # Get web server status
                response = requests.get('http://localhost:8080/remote_access', timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Update local URL
                    local_url = data.get('local_url', 'Not available')
                    self.local_url_label.setText(local_url)
                    
                    # Update remote URL and QR code
                    remote_status = data.get('status', 'inactive')
                    remote_url = data.get('tunnel_url', 'Not available')
                    
                    if remote_status == 'active':
                        self.remote_status_label.setText("Remote access status: Active")
                        self.remote_status_label.setStyleSheet("color: green;")
                        self.remote_url_label.setText(remote_url)
                        
                        # Generate and display QR code
                        qr_url = f"https://chart.googleapis.com/chart?cht=qr&chs=200x200&chl={remote_url}"
                        self.update_qr_code(qr_url)
                    else:
                        self.remote_status_label.setText("Remote access status: Inactive")
                        self.remote_status_label.setStyleSheet("color: red;")
                        self.remote_url_label.setText("Not available")
                        self.qr_label.setText("QR Code not available")
            else:
                # Server is not running, update UI to indicate
                self.local_url_label.setText("Server not running - Toggle Web Visualization first")
                self.remote_status_label.setText("Remote access status: Server not running")
                self.remote_status_label.setStyleSheet("color: orange;")
                self.remote_url_label.setText("Not available")
                self.qr_label.setText("Web server not running.\nClick 'Toggle Web Visualization' in toolbar to start.")
                        
        except Exception as e:
            self.local_url_label.setText("Server not running")
            self.remote_status_label.setText(f"Error: {str(e)}")
            self.remote_status_label.setStyleSheet("color: red;")
            self.remote_url_label.setText("Not available")
            self.qr_label.setText("QR Code not available")
    
    def update_qr_code(self, qr_url):
        """Download and display the QR code"""
        try:
            response = requests.get(qr_url)
            if response.status_code == 200:
                qr_image = QImage.fromData(response.content)
                qr_pixmap = QPixmap.fromImage(qr_image)
                self.qr_label.setPixmap(qr_pixmap.scaled(200, 200, Qt.KeepAspectRatio))
            else:
                self.qr_label.setText(f"QR Error: {response.status_code}")
        except Exception as e:
            self.qr_label.setText(f"QR Error: {str(e)}")
    
    def open_local_url(self):
        """Open the local URL in a web browser"""
        url = self.local_url_label.text()
        if url and url != "Loading local URL..." and url != "Server not running":
            import webbrowser
            webbrowser.open(url)
    
    def open_remote_url(self):
        """Open the remote URL in a web browser"""
        url = self.remote_url_label.text()
        if url and url != "Loading remote URL..." and url != "Not available":
            import webbrowser
            webbrowser.open(url)
    
    def copy_to_clipboard(self, text):
        """Copy the URL to clipboard"""
        if text and text != "Loading local URL..." and text != "Loading remote URL..." and text != "Not available" and text != "Server not running":
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
    
    def toggle_server(self, enable=True):
        """Toggle the web server on or off to save resources"""
        try:
            # Determine the endpoint based on desired action
            endpoint = 'start_server' if enable else 'stop_server'
            
            # Send request to control server state
            response = requests.post(f'http://localhost:8080/{endpoint}', timeout=2)
            if response.status_code == 200:
                if enable:
                    self.server_status_label = QLabel("Server Status: Starting...")
                    self.server_status_label.setStyleSheet("color: orange;")
                    # Schedule a refresh to update status after server starts
                    QTimer.singleShot(3000, self.refresh_status)
                else:
                    self.server_status_label = QLabel("Server Status: Stopping...")
                    self.server_status_label.setStyleSheet("color: orange;")
                    # Update UI immediately
                    self.local_url_label.setText("Server not running (resources saved)")
                    self.remote_status_label.setText("Remote access status: Inactive")
                    self.remote_status_label.setStyleSheet("color: red;")
                    self.remote_url_label.setText("Not available")
                    self.qr_label.setText("Web server disabled to save resources")
                
                return True
        except Exception as e:
            if enable:
                self.local_url_label.setText(f"Error starting server: {str(e)}")
            else:
                self.local_url_label.setText("Server may already be stopped")
            return False
            
    def is_server_running(self):
        """Check if the web server is currently running"""
        try:
            response = requests.get('http://localhost:8080/status', timeout=1)
            return response.status_code == 200
        except:
            return False