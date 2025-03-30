import time
import folium
import os
import logging
import webbrowser

logger = logging.getLogger("SensorFusion")

def read_byte(i2c_bus, addr, reg):
    """Read a byte from the I2C device"""
    retries = 3
    for _ in range(retries):
        try:
            return i2c_bus.read_byte_data(addr, reg)
        except Exception as e:
            logger.debug(f"Error reading byte from address 0x{addr:02x}, register 0x{reg:02x}: {e}")
            time.sleep(0.01)
    logger.warning(f"Failed to read from address 0x{addr:02x}, register 0x{reg:02x} after {retries} retries")
    return None

def read_word(i2c_bus, addr, reg):
    """Read a word from the I2C device"""
    high = read_byte(i2c_bus, addr, reg)
    low = read_byte(i2c_bus, addr, reg + 1)
    if high is not None and low is not None:
        val = (high << 8) + low
        return val
    else:
        return None

def read_word_2c(i2c_bus, addr, reg):
    """Read a 2's complement word from the I2C device"""
    val = read_word(i2c_bus, addr, reg)
    if val is not None:
        if val >= 0x8000:
            return -((65535 - val) + 1)
        else:
            return val
    else:
        return None

def get_accel_data(i2c_bus, config):
    """Get accelerometer data from ICM20948"""
    accel_z = read_word_2c(i2c_bus, config.ICM20948_ADDRESS, config.ICM20948_ACCEL_ZOUT_H)
    if accel_z is not None:
        return accel_z / 16384.0  # Convert to g
    return None

def update_gps_map(gps_data, config, analyzer=None):
    """Update the GPS position on a Folium map and save as HTML"""
    try:
        with gps_data["lock"]:
            lat = gps_data["lat"]
            lon = gps_data["lon"]
            alt = gps_data["alt"]
            sats = gps_data["sats"]
            timestamp = gps_data["timestamp"]
        
        # Skip if we don't have valid coordinates yet
        if lat == 0 and lon == 0:
            logger.warning("No valid GPS coordinates yet, skipping map update")
            return
                
        # Create a map centered at the GPS coordinates
        m = folium.Map(location=[lat, lon], zoom_start=config.MAP_ZOOM_START)
        
        # Add road quality info if available
        quality_info = ""
        marker_color = "blue"
        
        if analyzer:
            # Use LiDAR-based quality score instead of accelerometer-based
            quality_score = analyzer.lidar_quality_score
            road_class = analyzer.get_road_classification()
            quality_info = f"""
            <b>Road Quality (LiDAR)</b><br>
            Score: {quality_score:.1f}/100<br>
            Classification: {road_class}<br>
            <hr>
            """
            
            # Set marker color based on quality
            if quality_score >= 75:
                marker_color = "green"
            elif quality_score >= 50:
                marker_color = "orange"
            else:
                marker_color = "red"
        
        # Add a marker for the current position
        popup_text = f"""
        <b>GPS Data</b><br>
        Latitude: {lat:.6f}°<br>
        Longitude: {lon:.6f}°<br>
        Altitude: {alt} m<br>
        Satellites: {sats}<br>
        Time: {timestamp}<br>
        {quality_info}
        <hr>
        User: {config.USER_LOGIN}<br>
        Session: {config.SYSTEM_START_TIME}
        """
        
        folium.Marker(
            [lat, lon], 
            popup=folium.Popup(popup_text, max_width=300),
            icon=folium.Icon(color=marker_color)
        ).add_to(m)
        
        # Add a circle to show accuracy (just for visualization)
        folium.Circle(
            location=[lat, lon],
            radius=10,  # 10 meters radius
            color=marker_color,
            fill=True,
            fill_opacity=0.2
        ).add_to(m)
        
        # Add road events if analyzer is available
        if analyzer and hasattr(analyzer, 'events'):
            for event in analyzer.get_recent_events(count=10):
                if 'lat' in event and 'lon' in event and event['lat'] != 0:
                    # Set icon and color based on event type and severity
                    icon_color = "red" if event['severity'] > 70 else "orange"
                    icon_type = "warning" if "Pothole" in event['type'] else "info-sign"
                    
                    event_html = f"""
                    <b>{event['type']} Detected</b><br>
                    Severity: {event['severity']}/100<br>
                    Magnitude: {event['magnitude']:.3f}g<br>
                    Time: {event['timestamp']}<br>
                    """
                    
                    folium.Marker(
                        [event['lat'], event['lon']], 
                        popup=folium.Popup(event_html, max_width=200),
                        icon=folium.Icon(color=icon_color, icon=icon_type)
                    ).add_to(m)
        
        # Save the map to an HTML file
        m.save(config.MAP_HTML_PATH)
        logger.info(f"GPS map updated at {config.MAP_HTML_PATH}")
        
        # Verify the file exists
        if os.path.exists(config.MAP_HTML_PATH):
            logger.info(f"GPS map file successfully created")
        else:
            logger.error(f"Failed to create GPS map file")
            
    except Exception as e:
        logger.error(f"Error updating GPS map: {e}")

def create_default_map(config):
    """Create a default map if no GPS data is available yet"""
    try:
        # Create a map centered at a default location (0, 0 or another predefined location)
        m = folium.Map(location=[0, 0], zoom_start=2)
        
        # Add explanatory text with user and session information
        popup_text = f"""
        <b>Waiting for GPS data...</b><br>
        <hr>
        User: {config.USER_LOGIN}<br>
        Session: {config.SYSTEM_START_TIME}
        """
        
        folium.Marker(
            [0, 0], 
            popup=folium.Popup(popup_text, max_width=300),
            icon=folium.Icon(color='red')
        ).add_to(m)
        
        # Save the map
        m.save(config.MAP_HTML_PATH)
        logger.info(f"Default map created at {config.MAP_HTML_PATH}")
        
    except Exception as e:
        logger.error(f"Error creating default map: {e}")
