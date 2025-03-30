import numpy as np
import logging

logger = logging.getLogger("SensorFusion")

# Performance tracking variable
_frame_skip_counter = 0

def update_accel_plot(frame, accel_line, accel_data, accel_data_lock, config, analyzer=None, analysis_lock=None):
    """Update function for accelerometer animation with optimized performance"""
    global _frame_skip_counter
    
    # Skip frames to reduce CPU usage
    _frame_skip_counter += 1
    if _frame_skip_counter < config.MAX_FRAME_SKIP:
        return accel_line,
    else:
        _frame_skip_counter = 0
    
    # Check if there's data before acquiring the lock
    with accel_data_lock:
        has_data = len(accel_data) > 0
        if not has_data:
            return accel_line,
    
        # Make a copy of the data while holding the lock
        data_array = np.array(accel_data)
    
    # Update the plot with current data - moved outside lock
    accel_line.set_ydata(data_array)
    
    # Adjust x-axis for proper scrolling effect - optimized to use length directly
    x_data = np.arange(len(data_array))
    accel_line.set_xdata(x_data)
    
    # Add road quality info if analyzer is available - using minimal locking
    if analyzer and analysis_lock:
        # Only acquire analysis lock if we need to update title or colors
        if frame % 5 == 0:  # Update text less frequently (every 5 frames)
            with analysis_lock:
                # Use LiDAR-based quality score instead of accelerometer-based
                quality_score = analyzer.lidar_quality_score
                road_class = analyzer.get_road_classification()
                
                # Update the title with quality information
                ax = accel_line.axes
                ax.set_title(f"Sensor Data | Road Quality (LiDAR): {quality_score:.1f}/100 ({road_class})")
                
                # Color the line based on quality - only change if different
                if quality_score >= 75 and accel_line.get_color() != 'green':  # Good
                    accel_line.set_color('green')
                elif 50 <= quality_score < 75 and accel_line.get_color() != 'orange':  # Fair
                    accel_line.set_color('orange')
                elif quality_score < 50 and accel_line.get_color() != 'red':  # Poor
                    accel_line.set_color('red')
        
    return accel_line,
