import folium
import os
import logging
import webbrowser
from folium.plugins import HeatMap, PolyLineOffset
from collections import defaultdict

logger = logging.getLogger("SensorFusion")

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
                
            # Add road quality trail (heatmap) if history exists
            if hasattr(analyzer, 'gps_quality_history') and analyzer.gps_quality_history:
                # Extract points for heatmap - format is [[lat, lon, intensity], ...]
                heatmap_data = []
                for point in analyzer.gps_quality_history:
                    # Convert quality score to intensity (reverse scale: lower quality = higher intensity)
                    intensity = (100 - point['quality']) / 30  # Scale to reasonable heatmap intensity
                    heatmap_data.append([point['lat'], point['lon'], intensity])
                
                # Add heatmap layer if we have enough points
                if len(heatmap_data) >= 5:
                    HeatMap(
                        heatmap_data,
                        radius=15,
                        max_zoom=18,
                        blur=10,
                        gradient={0.4: 'green', 0.65: 'yellow', 0.9: 'orange', 1: 'red'}
                    ).add_to(m)
                    
                # Add quality-colored path
                # Group points by quality category for coloring
                quality_segments = defaultdict(list)
                last_quality_cat = None
                current_segment = []
                
                for point in analyzer.gps_quality_history:
                    # Determine quality category
                    if point['quality'] >= 75:
                        quality_cat = "good"
                        color = "green"
                    elif point['quality'] >= 50:
                        quality_cat = "fair"
                        color = "orange"
                    else:
                        quality_cat = "poor"
                        color = "red"
                    
                    # If category changed, start a new segment
                    if quality_cat != last_quality_cat and current_segment:
                        quality_segments[last_quality_cat].extend(current_segment)
                        current_segment = []
                    
                    current_segment.append([point['lat'], point['lon']])
                    last_quality_cat = quality_cat
                
                # Add the last segment
                if current_segment and last_quality_cat:
                    quality_segments[last_quality_cat].extend(current_segment)
                
                # Add each quality segment with appropriate color
                for quality_cat, points in quality_segments.items():
                    if len(points) >= 2:  # Need at least 2 points for a line
                        if quality_cat == "good":
                            color = "green"
                        elif quality_cat == "fair":
                            color = "orange"
                        else:
                            color = "poor"
                            color = "red"
                        
                        folium.PolyLine(
                            points,
                            color=color,
                            weight=5,
                            opacity=0.8,
                            tooltip=f"{quality_cat.title()} Road Quality"
                        ).add_to(m)
        
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
        
        # Add legend for quality colors
        legend_html = '''
        <div style="position: fixed; 
                    bottom: 50px; right: 50px; width: 150px; height: 120px; 
                    border:2px solid grey; z-index:9999; font-size:14px;
                    background-color:white; padding: 8px;
                    border-radius: 5px;">
          <p><b>Road Quality</b></p>
          <div style="margin-bottom:4px;">
            <div style="width:12px; height:12px; display:inline-block; background-color:green; margin-right:5px;"></div>
            Good (75-100)
          </div>
          <div style="margin-bottom:4px;">
            <div style="width:12px; height:12px; display:inline-block; background-color:orange; margin-right:5px;"></div>
            Fair (50-75)
          </div>
          <div>
            <div style="width:12px; height:12px; display:inline-block; background-color:red; margin-right:5px;"></div>
            Poor (0-50)
          </div>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))
        
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
