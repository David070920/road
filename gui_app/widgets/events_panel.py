import json
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                            QComboBox, QListWidget, QPushButton, QListWidgetItem, 
                            QMessageBox, QFileDialog, QAbstractItemView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

class EventsPanel(QWidget):
    """Widget to display and manage road events similar to web interface"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Filter controls
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Filter:"))
        self.event_filter = QComboBox()
        self.event_filter.addItems(["All Events", "Potholes", "Bumps", "LiDAR Events", "Accelerometer Events"])
        self.event_filter.currentTextChanged.connect(self.filter_events)
        filter_layout.addWidget(self.event_filter)
        
        self.event_search = QLineEdit()
        self.event_search.setPlaceholderText("Search events...")
        self.event_search.textChanged.connect(self.filter_events)
        filter_layout.addWidget(self.event_search)
        
        layout.addLayout(filter_layout)
        
        # Events list
        self.events_list = QListWidget()
        self.events_list.setAlternatingRowColors(True)
        self.events_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.events_list.itemClicked.connect(self.show_event_details)
        layout.addWidget(self.events_list)
        
        # Export buttons
        export_layout = QHBoxLayout()
        
        export_json_btn = QPushButton("Export JSON")
        export_csv_btn = QPushButton("Export CSV")
        export_gpx_btn = QPushButton("Export GPX")
        
        export_json_btn.clicked.connect(self.export_to_json)
        export_csv_btn.clicked.connect(self.export_to_csv)
        export_gpx_btn.clicked.connect(self.export_to_gpx)
        
        export_layout.addWidget(export_json_btn)
        export_layout.addWidget(export_csv_btn)
        export_layout.addWidget(export_gpx_btn)
        export_layout.addStretch()
        
        layout.addLayout(export_layout)
        
        # Sample events data for testing
        self.events = [
            {"id": 1, "type": "Pothole", "severity": 8, "lat": 37.7749, "lon": -122.4194, "timestamp": "2025-04-10 14:23:45", "source": "LiDAR"},
            {"id": 2, "type": "Bump", "severity": 5, "lat": 37.7750, "lon": -122.4195, "timestamp": "2025-04-10 14:25:12", "source": "Accelerometer"},
            {"id": 3, "type": "Rough Surface", "severity": 6, "lat": 37.7751, "lon": -122.4196, "timestamp": "2025-04-10 14:27:30", "source": "LiDAR"}
        ]
        
        # Populate events list
        self.populate_events()
    
    def populate_events(self):
        """Populate the events list with event data"""
        self.events_list.clear()
        
        if not self.events:
            self.events_list.addItem("No road events detected")
            return
            
        for event in self.events:
            item_text = f"{event['type']} (Severity: {event['severity']}) - {event['source']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, event)
            
            # Set item colors based on severity
            if event['severity'] >= 8:
                item.setForeground(QColor("#e74c3c"))  # Red for high severity
            elif event['severity'] >= 5:
                item.setForeground(QColor("#f39c12"))  # Orange for medium severity
            else:
                item.setForeground(QColor("#2ecc71"))  # Green for low severity
                
            self.events_list.addItem(item)
    
    def filter_events(self):
        """Filter events based on selected filter and search text"""
        filter_text = self.event_filter.currentText()
        search_text = self.event_search.text().lower()
        
        self.events_list.clear()
        
        filtered_events = []
        for event in self.events:
            # Apply filter
            if filter_text == "All Events" or \
               (filter_text == "Potholes" and event['type'] == "Pothole") or \
               (filter_text == "Bumps" and event['type'] == "Bump") or \
               (filter_text == "LiDAR Events" and event['source'] == "LiDAR") or \
               (filter_text == "Accelerometer Events" and event['source'] == "Accelerometer"):
                
                # Apply search
                if search_text == "" or \
                   search_text in event['type'].lower() or \
                   search_text in event['source'].lower() or \
                   search_text in str(event['severity']):
                    filtered_events.append(event)
        
        # Show filtered events
        if not filtered_events:
            self.events_list.addItem("No matching events found")
            return
            
        for event in filtered_events:
            item_text = f"{event['type']} (Severity: {event['severity']}) - {event['source']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, event)
            
            # Set item colors based on severity
            if event['severity'] >= 8:
                item.setForeground(QColor("#e74c3c"))  # Red for high severity
            elif event['severity'] >= 5:
                item.setForeground(QColor("#f39c12"))  # Orange for medium severity
            else:
                item.setForeground(QColor("#2ecc71"))  # Green for low severity
                
            self.events_list.addItem(item)
    
    def show_event_details(self, item):
        """Show details for the selected event"""
        event = item.data(Qt.UserRole)
        if not event:
            return
            
        msg = QMessageBox()
        msg.setWindowTitle("Event Details")
        
        msg.setText(f"<b>{event['type']} Event</b>")
        
        details = f"""
        <table>
            <tr>
                <td><b>Severity:</b></td>
                <td>{event['severity']}/10</td>
            </tr>
            <tr>
                <td><b>Source:</b></td>
                <td>{event['source']}</td>
            </tr>
            <tr>
                <td><b>Location:</b></td>
                <td>{event['lat']:.6f}, {event['lon']:.6f}</td>
            </tr>
            <tr>
                <td><b>Timestamp:</b></td>
                <td>{event['timestamp']}</td>
            </tr>
        </table>
        """
        
        msg.setInformativeText(details)
        
        # Add action buttons
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Apply)
        msg.button(QMessageBox.Apply).setText("Show on Map")
        
        # Custom styling for the message box
        msg.setStyleSheet("QLabel{min-width: 300px;}")
        
        result = msg.exec_()
        if result == QMessageBox.Apply:
            # Show on map functionality would go here
            pass
    
    def add_event(self, event):
        """Add a new event to the list"""
        self.events.append(event)
        self.populate_events()
        
        # Show notification for important events
        if event['severity'] >= 7:
            self.show_notification(event)
    
    def show_notification(self, event):
        """Show a notification for a high-severity event"""
        msg = QMessageBox()
        msg.setWindowTitle("Road Event Detected")
        
        if event['type'].lower() == "pothole":
            msg.setIcon(QMessageBox.Warning)
            msg.setText(f"Pothole Detected (Severity: {event['severity']})")
        else:
            msg.setIcon(QMessageBox.Information)
            msg.setText(f"Road Event: {event['type']} (Severity: {event['severity']})")
        
        msg.setInformativeText(f"Location: {event['lat']:.6f}, {event['lon']:.6f}\nSource: {event['source']}")
        msg.setStandardButtons(QMessageBox.Ok)
        
        msg.exec_()
    
    def export_to_json(self):
        """Export events data to JSON format"""
        if not self.events:
            QMessageBox.warning(self, "No Data", "No events data to export.")
            return
            
        filename, _ = QFileDialog.getSaveFileName(self, "Export JSON", "", "JSON Files (*.json)")
        if not filename:
            return
            
        try:
            with open(filename, 'w') as f:
                json.dump({"events": self.events}, f, indent=2)
                
            QMessageBox.information(self, "Export Successful", f"Events data exported to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data: {str(e)}")
    
    def export_to_csv(self):
        """Export events data to CSV format"""
        if not self.events:
            QMessageBox.warning(self, "No Data", "No events data to export.")
            return
            
        filename, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv)")
        if not filename:
            return
            
        try:
            with open(filename, 'w') as f:
                # Write header
                f.write("id,type,severity,latitude,longitude,timestamp,source\n")
                
                # Write data rows
                for event in self.events:
                    f.write(f"{event['id']},{event['type']},{event['severity']},{event['lat']},{event['lon']},{event['timestamp']},{event['source']}\n")
                
            QMessageBox.information(self, "Export Successful", f"Events data exported to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data: {str(e)}")
    
    def export_to_gpx(self):
        """Export events data to GPX format for GPS visualization"""
        if not self.events:
            QMessageBox.warning(self, "No Data", "No events data to export.")
            return
            
        filename, _ = QFileDialog.getSaveFileName(self, "Export GPX", "", "GPX Files (*.gpx)")
        if not filename:
            return
            
        try:
            with open(filename, 'w') as f:
                # Write GPX header
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write('<gpx version="1.1" creator="Road Quality App" xmlns="http://www.topografix.com/GPX/1/1">\n')
                
                # Write waypoints for each event
                for event in self.events:
                    f.write(f'  <wpt lat="{event["lat"]}" lon="{event["lon"]}">\n')
                    f.write(f'    <name>{event["type"]} (S{event["severity"]})</name>\n')
                    f.write(f'    <desc>Severity: {event["severity"]}, Source: {event["source"]}</desc>\n')
                    f.write(f'    <time>{event["timestamp"]}</time>\n')
                    f.write('  </wpt>\n')
                
                # Close GPX file
                f.write('</gpx>\n')
                
            QMessageBox.information(self, "Export Successful", f"Events data exported to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data: {str(e)}")