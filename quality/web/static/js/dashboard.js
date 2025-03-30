document.addEventListener('DOMContentLoaded', function() {
    // Initialize charts and connect to WebSocket
    const socket = io({
        reconnectionAttempts: 5,
        reconnectionDelay: 1000,
        timeout: 20000
    });
    
    let accelChart = null;
    let qualityGauge = null;
    let connectionStatus = 'connecting';
    let lastUpdateTime = Date.now();
    let dataUpdateCount = 0;
    
    // Add connection status indicator to the UI
    const statusBar = document.createElement('div');
    statusBar.className = 'connection-status connecting';
    statusBar.innerHTML = 'Connecting to server...';
    document.querySelector('header').appendChild(statusBar);
    
    // Initialize the quality gauge
    function initQualityGauge() {
        const ctx = document.getElementById('qualityGauge').getContext('2d');
        qualityGauge = new Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [0, 100],
                    backgroundColor: [
                        '#3498db',
                        '#ecf0f1'
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                circumference: 180,
                rotation: 270,
                cutout: '80%',
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        enabled: false
                    }
                },
                animation: {
                    duration: 1000
                }
            }
        });
    }
    
    // Initialize the accelerometer chart
    function initAccelChart() {
        const ctx = document.getElementById('accelChart').getContext('2d');
        accelChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: Array(50).fill(''),
                datasets: [{
                    label: 'Acceleration (Z)',
                    data: Array(50).fill(0),
                    borderColor: '#3498db',
                    backgroundColor: 'rgba(52, 152, 219, 0.2)',
                    borderWidth: 2,
                    tension: 0.2,
                    pointRadius: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: false,
                        min: -2,
                        max: 2,
                        title: {
                            display: true,
                            text: 'Acceleration (g)'
                        }
                    },
                    x: {
                        display: false
                    }
                },
                animation: {
                    duration: 0
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }
    
    // Handle incoming WebSocket data
    socket.on('data_update', function(data) {
        dataUpdateCount++;
        lastUpdateTime = Date.now();
        
        // Update status indicator if needed
        if (connectionStatus !== 'connected') {
            connectionStatus = 'connected';
            statusBar.className = 'connection-status connected';
            statusBar.innerHTML = 'Connected - Receiving Data';
            setTimeout(() => {
                statusBar.classList.add('fade-out');
            }, 3000);
        }
        
        // Update quality score
        const qualityValue = document.getElementById('quality-value');
        const qualityClass = document.getElementById('quality-classification');
        
        if (data.lidar_quality) {
            qualityValue.textContent = data.lidar_quality.toFixed(1) + '/100';
            qualityClass.textContent = data.classification;
            
            // Set color based on quality
            if (data.lidar_quality >= 75) {
                qualityValue.style.color = '#2ecc71';
                qualityGauge.data.datasets[0].backgroundColor[0] = '#2ecc71';
            } else if (data.lidar_quality >= 50) {
                qualityValue.style.color = '#f39c12';
                qualityGauge.data.datasets[0].backgroundColor[0] = '#f39c12';
            } else {
                qualityValue.style.color = '#e74c3c';
                qualityGauge.data.datasets[0].backgroundColor[0] = '#e74c3c';
            }
            
            // Update gauge chart
            qualityGauge.data.datasets[0].data[0] = data.lidar_quality;
            qualityGauge.data.datasets[0].data[1] = 100 - data.lidar_quality;
            qualityGauge.update('none'); // Use 'none' mode for smoother updates
        }
        
        // Update accelerometer chart
        if (data.accel_data && data.accel_data.length > 0) {
            accelChart.data.datasets[0].data = data.accel_data;
            accelChart.data.labels = Array(data.accel_data.length).fill('');
            
            // Update chart color based on quality
            if (data.lidar_quality >= 75) {
                accelChart.data.datasets[0].borderColor = '#2ecc71';
                accelChart.data.datasets[0].backgroundColor = 'rgba(46, 204, 113, 0.2)';
            } else if (data.lidar_quality >= 50) {
                accelChart.data.datasets[0].borderColor = '#f39c12';
                accelChart.data.datasets[0].backgroundColor = 'rgba(243, 156, 18, 0.2)';
            } else {
                accelChart.data.datasets[0].borderColor = '#e74c3c';
                accelChart.data.datasets[0].backgroundColor = 'rgba(231, 76, 60, 0.2)';
            }
            
            accelChart.update('none'); // Use 'none' mode for smoother updates
        }
        
        // Update GPS coordinates
        if (data.gps && data.gps.lat !== 0 && data.gps.lon !== 0) {
            document.getElementById('lat').textContent = data.gps.lat.toFixed(6);
            document.getElementById('lon').textContent = data.gps.lon.toFixed(6);
        }
        
        // Update events immediately instead of waiting for interval
        updateEvents();
    });
    
    // Connection status events
    socket.on('connect', function() {
        console.log('Connected to server');
        connectionStatus = 'connected';
        statusBar.className = 'connection-status connected';
        statusBar.innerHTML = 'Connected to server';
    });
    
    socket.on('connection_status', function(data) {
        console.log('Connection status:', data);
        // Additional handling for connection status updates from server
    });
    
    socket.on('disconnect', function() {
        console.log('Disconnected from server');
        connectionStatus = 'disconnected';
        statusBar.className = 'connection-status disconnected';
        statusBar.innerHTML = 'Disconnected - Trying to reconnect...';
    });
    
    socket.on('connect_error', function(error) {
        console.log('Connection error:', error);
        connectionStatus = 'error';
        statusBar.className = 'connection-status error';
        statusBar.innerHTML = 'Connection error - Retrying...';
    });
    
    socket.on('reconnect_attempt', function(attemptNumber) {
        console.log('Reconnection attempt:', attemptNumber);
        statusBar.innerHTML = `Reconnecting... (Attempt ${attemptNumber})`;
    });
    
    socket.on('pong', function(data) {
        console.log('Received pong:', data);
        // Could update UI to show latency if desired
    });
    
    // Ping the server periodically to check connection
    setInterval(function() {
        if (socket.connected) {
            socket.emit('ping');
        }
    }, 30000);
    
    // Check for stale data (no updates in a while)
    setInterval(function() {
        const timeSinceLastUpdate = Date.now() - lastUpdateTime;
        if (connectionStatus === 'connected' && timeSinceLastUpdate > 10000) {
            // No updates for 10 seconds while supposedly connected
            statusBar.className = 'connection-status stale';
            statusBar.innerHTML = 'Connection stale - Data not updating';
            statusBar.classList.remove('fade-out');
        }
    }, 5000);
    
    // Fetch road events from API
    function updateEvents() {
        fetch('/api/data')
            .then(response => response.json())
            .then(data => {
                const eventsList = document.getElementById('events-list');
                
                if (data.events && data.events.length > 0) {
                    // Clear the "no events" message
                    eventsList.innerHTML = '';
                    
                    // Add each event
                    data.events.forEach(event => {
                        const eventItem = document.createElement('div');
                        eventItem.className = `event-item event-${event.type.toLowerCase()}`;
                        
                        const timestamp = new Date(event.timestamp).toLocaleTimeString();
                        eventItem.innerHTML = `
                            <div class="event-title">${event.type} (Severity: ${event.severity})</div>
                            <div class="event-details">
                                Magnitude: ${event.magnitude.toFixed(3)}g<br>
                                Time: ${timestamp}
                            </div>
                        `;
                        
                        eventsList.appendChild(eventItem);
                    });
                } else {
                    eventsList.innerHTML = '<div class="no-events">No events detected</div>';
                }
            })
            .catch(error => {
                console.error('Error fetching events:', error);
            });
    }
    
    // Initialize charts
    initQualityGauge();
    initAccelChart();
    
    // Initial events load
    updateEvents();
    
    // Handle responsive behavior
    function resizeCharts() {
        if (accelChart) {
            accelChart.resize();
        }
        if (qualityGauge) {
            qualityGauge.resize();
        }
    }
    
    window.addEventListener('resize', resizeCharts);
    
    // Display connection and update statistics in console periodically
    setInterval(function() {
        console.log(`Connection status: ${connectionStatus}, Updates received: ${dataUpdateCount}`);
    }, 60000);
});
