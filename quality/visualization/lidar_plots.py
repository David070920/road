import numpy as np
import time
import logging

logger = logging.getLogger("SensorFusion")

# Add performance tracking variables
_last_update_time = 0
_update_interval_multiplier = 1.0
_frame_skip_counter = 0

def update_lidar_plot(num, line, lidar_data, lidar_data_lock, config):
    """Update function for LiDAR animation with optimized performance"""
    global _last_update_time, _update_interval_multiplier, _frame_skip_counter
    
    # Skip frames if we're updating too frequently to reduce CPU load
    _frame_skip_counter += 1
    if _frame_skip_counter < config.MAX_FRAME_SKIP:
        return line,
    else:
        _frame_skip_counter = 0
    
    # Measure update time to adaptively adjust frequency
    start_time = time.time()
    
    # Check if there's new data to process before acquiring lock
    # This minimizes lock contention
    has_data = False
    with lidar_data_lock:
        has_data = len(lidar_data) > 0
        
        if not has_data:
            return line,
    
        # Process the data for visualization only if we have data
        # Separate the lock acquisition to minimize time held
    with lidar_data_lock:
        # Make a shallow copy to release lock faster
        lidar_snapshot = list(lidar_data)
            
    # Process the data without holding the lock
    # Convert angles to the format expected by the polar plot
    polar_data = []
    for point in lidar_snapshot:
        angle_deg = point[0]
        distance = point[1]
        
        # Convert 315-360 degrees to -45-0 degrees for the polar plot
        if angle_deg >= 315 and angle_deg <= 360:
            angle_deg = angle_deg - 360
        
        # Only include angles in our desired range
        if -45 <= angle_deg <= 45:
            polar_data.append((np.radians(angle_deg), distance))
    
    if not polar_data:
        return line,
        
    # Convert data to numpy arrays for faster processing
    angles = np.array([point[0] for point in polar_data])
    distances = np.array([point[1] for point in polar_data])
    
    # Update the plot
    offsets = np.column_stack((angles, distances))
    line.set_offsets(offsets)
    
    # Color points based on distance from expected model - optimized calculation
    # First estimate the LiDAR height (distance at angle ≈ 0)
    if len(angles) > 0:
        center_idx = np.argmin(np.abs(angles))
        est_height = distances[center_idx]
        
        # Calculate expected distances based on cosine model
        cos_values = np.cos(angles)
        cos_values = np.maximum(cos_values, 0.1)  # Prevent division by zero
        expected = est_height / cos_values
        
        # Calculate deviations as intensity - simplified calculation
        deviations = np.abs(distances - expected)
        max_dev = max(20, np.max(deviations))  # At least 20mm scale for stability
        intensity = deviations / max_dev * 50  # Scale to colormap range
        
        line.set_array(intensity)
    
    # Measure and adjust update rate dynamically
    update_time = time.time() - start_time
    
    # If update takes too long, increase the interval multiplier
    if update_time > 0.05:  # 50ms threshold
        _update_interval_multiplier = min(3.0, _update_interval_multiplier * 1.1)
    else:
        # Gradually decrease multiplier if updates are fast
        _update_interval_multiplier = max(1.0, _update_interval_multiplier * 0.95)
    
    _last_update_time = time.time()
    return line,
