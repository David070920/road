/**
 * Map View for Road Quality Dashboard
 * Displays the road quality data on an interactive map
 */
document.addEventListener('DOMContentLoaded', function() {
    // Check if Leaflet library is loaded
    if (typeof L === 'undefined') {
        loadLeaflet();
    } else {
        initializeMap();
    }

    // Initialize socket connection or use the existing one
    const socket = window.socket || io();
    
    // Store the road quality data points for the map
    let roadQualityData = [];
    let currentPosition = null;
    let map = null;
    let heatmapLayer = null;
    let positionMarker = null;
    let qualityPath = null;
    let showHeatmap = false;
    
    // Trip statistics
    let tripStartTime = new Date();
    let totalDistance = 0;
    let lastPosition = null;
    let qualitySum = 0;
    let qualityCount = 0;
    
    // Load Leaflet library if it's not already loaded
    function loadLeaflet() {
        // Load CSS
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
        document.head.appendChild(link);
        
        // Load JS
        const script = document.createElement('script');
        script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
        script.onload = function() {
            // After Leaflet loads, load heatmap plugin
            const heatScript = document.createElement('script');
            heatScript.src = 'https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js';
            heatScript.onload = initializeMap;
            document.head.appendChild(heatScript);
        };
        document.head.appendChild(script);
    }
    
    // Initialize the map
    function initializeMap() {
        // Initialize with a default location (will be updated with GPS data)
        map = L.map('quality-map').setView([0, 0], 16);
        
        // Add tile layer (map background)
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
        }).addTo(map);
        
        // Create a position marker
        const carIcon = L.divIcon({
            html: '<i class="fas fa-car" style="color:#3559e0; font-size:24px;"></i>',
            className: 'car-marker-icon',
            iconSize: [24, 24],
            iconAnchor: [12, 12]
        });
        
        positionMarker = L.marker([0, 0], {icon: carIcon}).addTo(map);
        
        // Create path layer for the quality track
        qualityPath = L.polyline([], {
            color: '#3559e0',
            weight: 5,
            opacity: 0.7
        }).addTo(map);
        
        // Set up button event listeners
        document.getElementById('center-map').addEventListener('click', centerMap);
        document.getElementById('toggle-heatmap').addEventListener('click', toggleHeatmap);
        
        // Start listening for data updates
        socket.on('data_update', handleDataUpdate);
    }
    
    // Handle incoming data updates
    function handleDataUpdate(data) {
        if (!map) return;
        
        // Check if we have GPS data
        if (data.gps && data.gps.lat !== 0 && data.gps.lon !== 0) {
            currentPosition = [data.gps.lat, data.gps.lon];
            
            // Update marker position
            positionMarker.setLatLng(currentPosition);
            
            // Update the path
            const pathPoints = qualityPath.getLatLngs();
            pathPoints.push(currentPosition);
            qualityPath.setLatLngs(pathPoints);
            
            // Update trip statistics
            updateTripStatistics(data);
            
            // Add quality data point for heatmap
            if (data.lidar_quality !== undefined) {
                // Calculate color intensity based on quality
                let intensity = 1 - (data.lidar_quality / 100); // Reverse scale (lower quality = higher intensity for heatmap)
                roadQualityData.push([data.gps.lat, data.gps.lon, intensity]);
                
                // Update the heatmap if it's visible
                if (showHeatmap && heatmapLayer) {
                    heatmapLayer.setLatLngs(roadQualityData);
                }
                
                // Color the path based on quality
                colorPath(data.lidar_quality);
            }
            
            // Auto-center the map if this is the first position fix
            if (pathPoints.length === 1) {
                map.setView(currentPosition, 16);
            }
        }
    }
    
    // Center the map on current position
    function centerMap() {
        if (map && currentPosition) {
            map.setView(currentPosition, 16);
        }
    }
    
    // Toggle the heatmap display
    function toggleHeatmap() {
        showHeatmap = !showHeatmap;
        
        if (showHeatmap) {
            // Create heatmap layer if it doesn't exist
            if (!heatmapLayer) {
                heatmapLayer = L.heatLayer(roadQualityData, {
                    radius: 20,
                    blur: 15,
                    maxZoom: 17,
                    gradient: {
                        0.0: '#2ecc71',  // Good quality (green)
                        0.25: '#f39c12', // Medium quality (yellow)
                        0.5: '#e74c3c'   // Poor quality (red)
                    }
                }).addTo(map);
            } else {
                map.addLayer(heatmapLayer);
            }
            
            // Change button text
            document.getElementById('toggle-heatmap').innerHTML = '<i class="fas fa-layer-group"></i> Hide Heatmap';
        } else {
            // Remove heatmap layer
            if (heatmapLayer) {
                map.removeLayer(heatmapLayer);
            }
            
            // Change button text
            document.getElementById('toggle-heatmap').innerHTML = '<i class="fas fa-fire"></i> Show Heatmap';
        }
    }
    
    // Color the path based on road quality
    function colorPath(quality) {
        if (qualityPath && qualityPath.getLatLngs().length > 1) {
            const lastIndex = qualityPath.getLatLngs().length - 1;
            const newSegment = [
                qualityPath.getLatLngs()[lastIndex - 1],
                qualityPath.getLatLngs()[lastIndex]
            ];
            
            // Determine color based on quality
            let color;
            if (quality >= 75) {
                color = '#2ecc71'; // Good - green
            } else if (quality >= 50) {
                color = '#f39c12'; // Medium - yellow/orange
            } else {
                color = '#e74c3c'; // Poor - red
            }
            
            // Add a colored segment
            L.polyline(newSegment, {
                color: color,
                weight: 5,
                opacity: 0.7
            }).addTo(map);
        }
    }
    
    // Update trip statistics
    function updateTripStatistics(data) {
        // Update distance traveled
        if (lastPosition && currentPosition) {
            const distance = calculateDistance(lastPosition[0], lastPosition[1], currentPosition[0], currentPosition[1]);
            totalDistance += distance;
            document.getElementById('distance-traveled').textContent = (totalDistance).toFixed(2);
        }
        
        // Update trip duration
        const now = new Date();
        const duration = (now - tripStartTime) / 1000; // duration in seconds
        document.getElementById('trip-duration').textContent = formatDuration(duration);
        
        // Update average speed (km/h)
        const hours = duration / 3600;
        const avgSpeed = hours > 0 ? totalDistance / hours : 0;
        document.getElementById('avg-speed').textContent = avgSpeed.toFixed(1);
        
        // Update average quality
        if (data.lidar_quality !== undefined) {
            qualitySum += data.lidar_quality;
            qualityCount++;
            const avgQuality = qualityCount > 0 ? qualitySum / qualityCount : 0;
            document.getElementById('avg-quality').textContent = avgQuality.toFixed(1);
        }
        
        // Save the current position for next calculation
        lastPosition = currentPosition;
    }
    
    // Calculate distance between two coordinates in km (haversine formula)
    function calculateDistance(lat1, lon1, lat2, lon2) {
        const R = 6371; // Radius of the earth in km
        const dLat = deg2rad(lat2 - lat1);
        const dLon = deg2rad(lon2 - lon1);
        const a = 
            Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(deg2rad(lat1)) * Math.cos(deg2rad(lat2)) * 
            Math.sin(dLon/2) * Math.sin(dLon/2); 
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a)); 
        const d = R * c; // Distance in km
        return d;
    }
    
    function deg2rad(deg) {
        return deg * (Math.PI/180);
    }
    
    function formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else if (minutes > 0) {
            return `${minutes}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    }
    
    // Export functions to the global scope
    window.mapController = {
        centerMap,
        toggleHeatmap
    };
});