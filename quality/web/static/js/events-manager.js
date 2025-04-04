/**
 * Events and Settings Manager for Road Quality Dashboard
 * Handles event filtering/display and settings management
 */
document.addEventListener('DOMContentLoaded', function() {
    // Initialize socket connection or use the existing one
    const socket = window.socket || io();
    
    // Keep track of all events for filtering
    let allEvents = [];
    let eventStatsChart = null;
    
    // Initialize event listeners
    initEventListeners();
    initSettingsControls();
    
    // Initialize event listeners for filtering and searching
    function initEventListeners() {
        // Event filtering
        const eventFilter = document.getElementById('event-filter');
        if (eventFilter) {
            eventFilter.addEventListener('change', filterEvents);
        }
        
        // Event searching
        const eventSearch = document.getElementById('event-search');
        if (eventSearch) {
            eventSearch.addEventListener('input', filterEvents);
        }
        
        // Data export buttons
        const exportJson = document.getElementById('export-json');
        if (exportJson) {
            exportJson.addEventListener('click', exportToJson);
        }
        
        const exportCsv = document.getElementById('export-csv');
        if (exportCsv) {
            exportCsv.addEventListener('click', exportToCsv);
        }
        
        const exportGpx = document.getElementById('export-gpx');
        if (exportGpx) {
            exportGpx.addEventListener('click', exportToGpx);
        }
    }
    
    // Initialize settings controls
    function initSettingsControls() {
        // Chart smoothing slider
        const chartSmoothing = document.getElementById('chart-smoothing');
        if (chartSmoothing) {
            // Load saved value if exists
            const savedSmoothing = localStorage.getItem('chart-smoothing');
            if (savedSmoothing) {
                chartSmoothing.value = savedSmoothing;
                applyChartSmoothing(savedSmoothing);
            }
            
            chartSmoothing.addEventListener('input', function() {
                applyChartSmoothing(this.value);
                localStorage.setItem('chart-smoothing', this.value);
            });
        }
        
        // Update frequency selector
        const updateFrequency = document.getElementById('update-frequency');
        if (updateFrequency) {
            // Load saved value if exists
            const savedFrequency = localStorage.getItem('update-frequency');
            if (savedFrequency) {
                updateFrequency.value = savedFrequency;
                applyUpdateFrequency(savedFrequency);
            }
            
            updateFrequency.addEventListener('change', function() {
                applyUpdateFrequency(this.value);
                localStorage.setItem('update-frequency', this.value);
            });
        }
        
        // Notification settings
        const notifyEvents = document.getElementById('notify-events');
        if (notifyEvents) {
            // Load saved value if exists
            const savedNotifyEvents = localStorage.getItem('notify-events');
            if (savedNotifyEvents !== null) {
                notifyEvents.checked = savedNotifyEvents === 'true';
            }
            
            notifyEvents.addEventListener('change', function() {
                localStorage.setItem('notify-events', this.checked);
                
                // Request notification permission if enabled
                if (this.checked && Notification.permission !== 'granted') {
                    Notification.requestPermission();
                }
            });
        }
        
        const notifySensors = document.getElementById('notify-sensors');
        if (notifySensors) {
            // Load saved value if exists
            const savedNotifySensors = localStorage.getItem('notify-sensors');
            if (savedNotifySensors !== null) {
                notifySensors.checked = savedNotifySensors === 'true';
            }
            
            notifySensors.addEventListener('change', function() {
                localStorage.setItem('notify-sensors', this.checked);
            });
        }
    }
    
    // Apply chart smoothing 
    function applyChartSmoothing(value) {
        // Find the accelChart object from dashboard.js
        if (window.accelChart) {
            window.accelChart.options.elements.line.tension = value / 10;
            window.accelChart.update();
        }
    }
    
    // Apply update frequency
    function applyUpdateFrequency(value) {
        // This will be picked up by the socket handler in dashboard.js
        window.updateFrequency = parseInt(value);
    }
    
    // Filter events based on selected options
    function filterEvents() {
        const filterValue = document.getElementById('event-filter').value;
        const searchValue = document.getElementById('event-search').value.toLowerCase();
        const eventsContainer = document.getElementById('events-list-full');
        
        if (!eventsContainer || !allEvents.length) {
            return;
        }
        
        // Clear events container
        eventsContainer.innerHTML = '';
        
        // Filter events
        const filteredEvents = allEvents.filter(event => {
            // Apply type filter
            if (filterValue !== 'all') {
                if (filterValue === 'pothole' && event.type.toLowerCase() !== 'pothole') {
                    return false;
                }
                if (filterValue === 'bump' && event.type.toLowerCase() !== 'bump') {
                    return false;
                }
                if (filterValue === 'lidar' && event.source !== 'LiDAR') {
                    return false;
                }
                if (filterValue === 'accel' && event.source !== 'Accelerometer') {
                    return false;
                }
            }
            
            // Apply search filter
            if (searchValue) {
                return (
                    event.type.toLowerCase().includes(searchValue) ||
                    event.severity.toString().includes(searchValue) ||
                    (event.location && event.location.toLowerCase().includes(searchValue))
                );
            }
            
            return true;
        });
        
        // Display filtered events
        if (filteredEvents.length > 0) {
            filteredEvents.forEach(event => {
                const eventItem = createEventElement(event);
                eventsContainer.appendChild(eventItem);
            });
        } else {
            eventsContainer.innerHTML = '<div class="no-events">No events match the selected filters</div>';
        }
        
        // Update the chart
        updateEventStatsChart(filteredEvents);
    }
    
    // Create an event element
    function createEventElement(event) {
        const eventItem = document.createElement('div');
        eventItem.className = `event-item event-${event.type.toLowerCase()}`;
        
        // Add source class if available
        if (event.source) {
            eventItem.classList.add(`event-source-${event.source.toLowerCase()}`);
        }
        
        eventItem.setAttribute('data-timestamp', event.timestamp);
        
        const timestamp = new Date(event.timestamp).toLocaleString();
        let icon = event.type === 'Pothole' ? 'fa-triangle-exclamation' : 'fa-hill-rockslide';
        
        // Build event details
        let eventDetails = `
            <div class="event-magnitude">Magnitude: ${event.magnitude.toFixed(3)} ${event.source === 'LiDAR' ? 'mm' : 'g'}</div>
            <div class="event-location">Location: ${event.location || 'Unknown'}</div>
            <div class="event-time">Time: ${timestamp}</div>
        `;
        
        // Add LiDAR-specific details if available
        if (event.source === 'LiDAR' && event.angle !== undefined) {
            eventDetails += `<div class="event-angle">Angle: ${event.angle.toFixed(1)}°</div>`;
        }
        
        // Source indicator
        const sourceIndicator = event.source ? `<span class="event-source">${event.source}</span>` : '';
        
        eventItem.innerHTML = `
            <div class="event-title">
                <i class="fas ${icon}"></i> ${event.type} (Severity: ${event.severity}) ${sourceIndicator}
            </div>
            <div class="event-details">
                ${eventDetails}
            </div>
        `;
        
        return eventItem;
    }
    
    // Update the event statistics chart
    function updateEventStatsChart(events) {
        const canvas = document.getElementById('eventStatsChart');
        if (!canvas) return;
        
        // Count events by type and source
        const eventTypes = {};
        const eventSources = {};
        
        events.forEach(event => {
            // Count by type
            if (!eventTypes[event.type]) {
                eventTypes[event.type] = 0;
            }
            eventTypes[event.type]++;
            
            // Count by source
            if (event.source) {
                if (!eventSources[event.source]) {
                    eventSources[event.source] = 0;
                }
                eventSources[event.source]++;
            }
        });
        
        // Create or update chart
        if (eventStatsChart) {
            // Update existing chart
            eventStatsChart.data.labels = Object.keys(eventTypes);
            eventStatsChart.data.datasets[0].data = Object.values(eventTypes);
            eventStatsChart.update();
        } else {
            // Create new chart
            eventStatsChart = new Chart(canvas, {
                type: 'bar',
                data: {
                    labels: Object.keys(eventTypes),
                    datasets: [{
                        label: 'Event Types',
                        data: Object.values(eventTypes),
                        backgroundColor: [
                            '#e74c3c',  // Red for potholes
                            '#f39c12'   // Orange for bumps
                        ],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                precision: 0
                            }
                        }
                    }
                }
            });
        }
    }
    
    // Export data to JSON format
    function exportToJson() {
        if (allEvents.length === 0) {
            showNotification('No data to export', 'warning');
            return;
        }
        
        const dataStr = JSON.stringify({
            events: allEvents,
            road_quality: {
                average: document.getElementById('avg-quality')?.textContent || 'N/A',
                trip_info: {
                    distance: document.getElementById('distance-traveled')?.textContent || 'N/A',
                    duration: document.getElementById('trip-duration')?.textContent || 'N/A',
                    avg_speed: document.getElementById('avg-speed')?.textContent || 'N/A'
                },
                timestamp: new Date().toISOString()
            }
        }, null, 2);
        
        downloadFile(dataStr, 'road_quality_data.json', 'application/json');
        showNotification('JSON data exported successfully');
    }
    
    // Export data to CSV format
    function exportToCsv() {
        if (allEvents.length === 0) {
            showNotification('No data to export', 'warning');
            return;
        }
        
        // Create CSV header
        let csv = 'Type,Severity,Magnitude,Latitude,Longitude,Source,Timestamp\n';
        
        // Add events data
        allEvents.forEach(event => {
            csv += `${event.type},${event.severity},${event.magnitude},`;
            csv += `${event.lat || ''},${event.lon || ''},`;
            csv += `${event.source || ''},${event.timestamp}\n`;
        });
        
        downloadFile(csv, 'road_quality_events.csv', 'text/csv');
        showNotification('CSV data exported successfully');
    }
    
    // Export data to GPX format for GPS apps
    function exportToGpx() {
        if (allEvents.length === 0) {
            showNotification('No data to export', 'warning');
            return;
        }
        
        // Create GPX header
        let gpx = `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Road Quality Measurement System">
  <metadata>
    <name>Road Quality Data</name>
    <time>${new Date().toISOString()}</time>
  </metadata>
  <trk>
    <name>Road Quality Path</name>
    <trkseg>
`;
        
        // Add events as waypoints
        allEvents.forEach(event => {
            if (event.lat && event.lon) {
                gpx += `      <trkpt lat="${event.lat}" lon="${event.lon}">
        <ele>${event.altitude || 0}</ele>
        <time>${event.timestamp}</time>
        <desc>${event.type} - Severity: ${event.severity}, Magnitude: ${event.magnitude}</desc>
      </trkpt>\n`;
            }
        });
        
        // Close GPX file
        gpx += `    </trkseg>
  </trk>
</gpx>`;
        
        downloadFile(gpx, 'road_quality_path.gpx', 'application/gpx+xml');
        showNotification('GPX data exported successfully');
    }
    
    // Helper function to download a file
    function downloadFile(content, fileName, contentType) {
        const a = document.createElement('a');
        const file = new Blob([content], {type: contentType});
        a.href = URL.createObjectURL(file);
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
    
    // Show notification in browser
    function showNotification(message, type = 'success') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}"></i>
            <span>${message}</span>
        `;
        
        // Append to body
        document.body.appendChild(notification);
        
        // Show notification
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);
        
        // Remove after animation
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 500);
        }, 3000);
    }
    
    // Update event list when new data comes in
    socket.on('data_update', function(data) {
        if (data.events && data.events.length > 0) {
            // Store all events
            allEvents = data.events;
            
            // Update filtered view if on events tab
            if (document.getElementById('events').style.display !== 'none') {
                filterEvents();
            }
            
            // Show browser notification for new events if enabled
            if (localStorage.getItem('notify-events') === 'true' && Notification.permission === 'granted') {
                const latestEvent = data.events[0];
                new Notification('Road Event Detected', {
                    body: `${latestEvent.type} detected with severity ${latestEvent.severity}`,
                    icon: '/static/img/favicon.ico'
                });
            }
        }
    });
    
    // Listen for sensor status changes
    socket.on('sensor_status', function(data) {
        // Show browser notification for sensor status changes if enabled
        if (localStorage.getItem('notify-sensors') === 'true' && Notification.permission === 'granted') {
            if (data.changed) {
                new Notification('Sensor Status Changed', {
                    body: `${data.sensor} is now ${data.status ? 'connected' : 'disconnected'}`,
                    icon: '/static/img/favicon.ico'
                });
            }
        }
    });
});