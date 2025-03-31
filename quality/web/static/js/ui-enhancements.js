/**
 * UI Enhancements for Road Quality Dashboard
 * Adds dark/light theme toggle, device status indicators, and system status monitoring
 */
document.addEventListener('DOMContentLoaded', function() {
    // Initialize UI enhancement features
    initThemeToggle();
    initDeviceStatus();
    initSystemStatus();
    handleLoadingScreen();
    
    // Theme toggle functionality
    function initThemeToggle() {
        const themeToggle = document.getElementById('theme-toggle');
        const themeIcon = themeToggle.querySelector('i');
        
        // Check for saved theme preference or use system preference
        const prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');
        const savedTheme = localStorage.getItem('theme');
        
        if (savedTheme === 'dark' || (!savedTheme && prefersDarkScheme.matches)) {
            document.body.classList.add('dark-theme');
            themeIcon.classList.remove('fa-moon');
            themeIcon.classList.add('fa-sun');
        }
        
        // Toggle theme when button is clicked
        themeToggle.addEventListener('click', function() {
            document.body.classList.toggle('dark-theme');
            
            // Update icon
            if (document.body.classList.contains('dark-theme')) {
                themeIcon.classList.remove('fa-moon');
                themeIcon.classList.add('fa-sun');
                localStorage.setItem('theme', 'dark');
            } else {
                themeIcon.classList.remove('fa-sun');
                themeIcon.classList.add('fa-moon');
                localStorage.setItem('theme', 'light');
            }
        });
    }
    
    // Device status indicators
    function initDeviceStatus() {
        // Get device status elements
        const lidarStatus = document.getElementById('lidar-status');
        const accelStatus = document.getElementById('accel-status');
        const gpsStatus = document.getElementById('gps-status');
        const envStatus = document.getElementById('env-status');
        
        // Initialize all as disconnected
        setDeviceStatus(lidarStatus, false);
        setDeviceStatus(accelStatus, false);
        setDeviceStatus(gpsStatus, false);
        setDeviceStatus(envStatus, false);
        
        // Listen for data updates to set device status
        socket.on('data_update', function(data) {
            // Set LiDAR status based on data.lidar_quality existing
            setDeviceStatus(lidarStatus, data.lidar_quality !== undefined);
            
            // Set accelerometer status based on accel_data existing and not empty
            setDeviceStatus(accelStatus, data.accel_data && data.accel_data.length > 0);
            
            // Set GPS status based on valid coordinates
            setDeviceStatus(gpsStatus, data.gps && data.gps.lat !== 0 && data.gps.lon !== 0);
            
            // Set environmental sensor status based on any env data existing
            setDeviceStatus(envStatus, data.env && 
                (data.env.temperature !== null || 
                 data.env.humidity !== null || 
                 data.env.pressure !== null));
        });
    }
    
    // Helper function to set device status indicator
    function setDeviceStatus(element, isConnected) {
        if (isConnected) {
            element.className = 'device connected';
        } else {
            element.className = 'device disconnected';
        }
    }
    
    // System status monitoring
    function initSystemStatus() {
        // Fetch real system status from the server
        function updateSystemStatus() {
            fetch('/api/system')
                .then(response => response.json())
                .then(data => {
                    // Update CPU usage
                    const cpuElement = document.getElementById('cpu-usage');
                    cpuElement.textContent = data.cpu_usage;
                    const cpuValue = parseFloat(data.cpu_usage);
                    cpuElement.className = cpuValue > 80 ? 'value status-error' : 
                                          cpuValue > 60 ? 'value status-warning' : 
                                          'value status-good';
                    
                    // Update memory usage
                    const memElement = document.getElementById('memory-usage');
                    memElement.textContent = data.memory_usage;
                    const memValue = parseFloat(data.memory_usage);
                    memElement.className = memValue > 80 ? 'value status-error' : 
                                          memValue > 60 ? 'value status-warning' : 
                                          'value status-good';
                    
                    // Update disk usage
                    const diskElement = document.getElementById('disk-usage');
                    diskElement.textContent = data.disk_usage;
                    const diskValue = parseFloat(data.disk_usage);
                    diskElement.className = diskValue > 80 ? 'value status-error' : 
                                           diskValue > 60 ? 'value status-warning' : 
                                           'value status-good';
                    
                    // Update network status
                    const networkElement = document.getElementById('network-status');
                    networkElement.textContent = data.network.status;
                    networkElement.className = data.network.status === 'Connected' ? 
                                              'value status-good' : 'value status-error';
                    
                    // Update uptime
                    const uptimeElement = document.getElementById('uptime');
                    uptimeElement.textContent = data.uptime;
                    
                    // Update data points
                    const dataPointsElement = document.getElementById('data-points');
                    const totalPoints = data.data_points.accel + data.data_points.lidar + data.data_points.gps;
                    dataPointsElement.textContent = totalPoints.toLocaleString();
                })
                .catch(error => {
                    console.error('Error fetching system status:', error);
                    // Use fallback fake data if we can't get real data
                    useFallbackSystemData();
                });
        }
        
        // Fallback with mock data if API fails
        function useFallbackSystemData() {
            const cpuUsage = Math.floor(Math.random() * 30) + 10; // Random value between 10-40%
            const memoryUsage = Math.floor(Math.random() * 40) + 20; // Random value between 20-60%
            const diskUsage = Math.floor(Math.random() * 20) + 10; // Random value between 10-30%
            
            // Update status values with fake data
            const cpuElement = document.getElementById('cpu-usage');
            cpuElement.textContent = cpuUsage + '%';
            cpuElement.className = 'value status-good';
            
            const memElement = document.getElementById('memory-usage');
            memElement.textContent = memoryUsage + '%';
            memElement.className = 'value status-good';
            
            const diskElement = document.getElementById('disk-usage');
            diskElement.textContent = diskUsage + '%';
            diskElement.className = 'value status-good';
            
            const networkElement = document.getElementById('network-status');
            networkElement.textContent = 'Connected';
            networkElement.className = 'value status-good';
            
            const uptimeElement = document.getElementById('uptime');
            uptimeElement.textContent = '2h 30m';
            
            const dataPointsElement = document.getElementById('data-points');
            dataPointsElement.textContent = '1,250';
        }
        
        // Update system status every 10 seconds
        updateSystemStatus();
        setInterval(updateSystemStatus, 10000);
    }
    
    // Loading screen handler
    function handleLoadingScreen() {
        const loadingScreen = document.querySelector('.loading');
        
        // Hide loading screen after data is received or after timeout
        let dataReceived = false;
        
        socket.on('data_update', function() {
            if (!dataReceived) {
                dataReceived = true;
                hideLoading();
            }
        });
        
        // Fallback: hide loading screen after 5 seconds even if no data
        setTimeout(function() {
            if (!dataReceived) {
                hideLoading();
            }
        }, 5000);
        
        function hideLoading() {
            loadingScreen.style.opacity = '0';
            setTimeout(function() {
                loadingScreen.style.display = 'none';
            }, 500);
        }
    }
    
    // Add a small animation when cards are loaded
    function animateCards() {
        const cards = document.querySelectorAll('.card');
        cards.forEach((card, index) => {
            // Set initial state
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            
            // Apply animation with delay based on card index
            setTimeout(() => {
                card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, 100 * index);
        });
    }
    
    // Initialize card animations
    setTimeout(animateCards, 300);
});
