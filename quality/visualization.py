import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import logging
from datetime import datetime
import time  # For measuring update performance

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

def setup_visualization(lidar_data, lidar_data_lock, accel_data, accel_data_lock, config, analyzer=None, analysis_lock=None):
    """Set up matplotlib figures and animations with optimized performance"""
    # Set the matplotlib backend properties to allow window management
    # This works across different backends
    plt.rcParams['figure.raise_window'] = False
    
    # Set additional optimization parameters for matplotlib
    plt.rcParams['figure.dpi'] = 80  # Lower DPI for faster rendering
    plt.rcParams['figure.autolayout'] = True  # Faster than tight_layout()
    plt.rcParams['path.simplify'] = True  # Optimize line drawing
    plt.rcParams['path.simplify_threshold'] = 0.8  # More aggressive simplification
    
    # User info text for plot titles
    user_info = f"User: {config.USER_LOGIN} | Session: {config.SYSTEM_START_TIME}"
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # LiDAR visualization
    fig_lidar, ax_lidar = plt.subplots(subplot_kw={'polar': True}, figsize=(8, 8))
    fig_lidar.canvas.manager.set_window_title('LiDAR Data - SensorFusion')
    
    # Make figure minimizable - using a cross-platform approach
    try:
        # Different backends might have different window management methods
        # Some might use 'window' attribute, others might not
        plt.rcParams['figure.figsize'] = [8, 8]
        plt.rcParams['figure.dpi'] = 80  # Reduce DPI for better performance
        
        # Try to detect Qt backend and handle it properly
        if hasattr(fig_lidar.canvas.manager, 'window'):
            backend = plt.get_backend().lower()
            if 'qt' in backend:
                # For Qt backends
                fig_lidar.canvas.manager.window.setWindowFlags(
                    fig_lidar.canvas.manager.window.windowFlags() & ~0x00000020
                )
            elif 'tk' in backend:
                # For Tk backends 
                fig_lidar.canvas.manager.window.wm_attributes("-topmost", 0)
            # For other backends, we rely on the default behavior
        
        logger.info(f"Configured LiDAR visualization window using backend: {plt.get_backend()}")
    except Exception as e:
        logger.warning(f"Could not configure window manager for LiDAR plot: {e}")
    
    line = ax_lidar.scatter([0, 0], [0, 0], s=5, c=[0, 0], cmap=plt.cm.Greys_r, lw=0)
    
    ax_lidar.set_rmax(1000)  # Set maximum distance to display
    
    # Set the angle limits to show our 90-degree field of view
    ax_lidar.set_thetamin(config.LIDAR_MIN_ANGLE)
    ax_lidar.set_thetamax(config.LIDAR_MAX_ANGLE)
    
    ax_lidar.grid(True)
    ax_lidar.set_title(f"LiDAR Data (90° FOV: 315°-360° and 0°-45°)\n{user_info}")
    
    # Increase animation interval to reduce CPU usage (use config values)
    lidar_ani = animation.FuncAnimation(
        fig_lidar, 
        update_lidar_plot,
        fargs=(line, lidar_data, lidar_data_lock, config), 
        interval=config.LIDAR_UPDATE_INTERVAL,  # Use config value
        blit=True,
        cache_frame_data=False
    )
    
    # Accelerometer visualization with reduced update frequency
    fig_accel, ax_accel = plt.subplots(figsize=(10, 4))
    fig_accel.canvas.manager.set_window_title('Accelerometer Data - SensorFusion')
    
    # Make figure minimizable - similar approach for accelerometer plot
    try:
        plt.rcParams['figure.figsize'] = [10, 4]
        
        if hasattr(fig_accel.canvas.manager, 'window'):
            backend = plt.get_backend().lower()
            if 'qt' in backend:
                fig_accel.canvas.manager.window.setWindowFlags(
                    fig_accel.canvas.manager.window.windowFlags() & ~0x00000020
                )
            elif 'tk' in backend:
                fig_accel.canvas.manager.window.wm_attributes ("-topmost", 0)
        
        logger.info(f"Configured accelerometer visualization window")
    except Exception as e:
        logger.warning(f"Could not configure window manager for accelerometer plot: {e}")
    
    # Initialize with empty data
    accel_line, = ax_accel.plot(
        np.arange(config.MAX_DATA_POINTS),
        np.zeros(config.MAX_DATA_POINTS),
        'b-', 
        label='Acceleration (Z)'
    )
    
    ax_accel.set_xlim(0, config.MAX_DATA_POINTS - 1)
    ax_accel.set_ylim(-2, 2)
    
    title = "Accelerometer Data"
    if analyzer:
        title += f" | Road Quality: {analyzer.current_quality_score:.1f}/100 ({analyzer.get_road_classification()})"
    
    ax_accel.set_title(f"{title}\n{user_info}")
    ax_accel.set_xlabel("Sample")
    ax_accel.set_ylabel("Acceleration (g)")
    ax_accel.grid(True)
    ax_accel.legend(loc='upper right')
    
    # Add a second y-axis for road quality score if analyzer is available
    if analyzer:
        ax_quality = ax_accel.twinx()
        ax_quality.set_ylabel("Road Quality Score")
        ax_quality.set_ylim(0, 100)
        ax_quality.spines['right'].set_color('green')
        ax_quality.tick_params(axis='y', colors='green')
        ax_quality.yaxis.label.set_color('green')
    
    # Add user info text in the lower right corner
    fig_accel.text(0.99, 0.01, f"{user_info} | Current time: {current_time}", 
                   horizontalalignment='right',
                   verticalalignment='bottom',
                   transform=fig_accel.transFigure,
                   fontsize=8, alpha=0.7)
    
    # Increase animation interval for accelerometer plot too
    accel_ani = animation.FuncAnimation(
        fig_accel, 
        update_accel_plot, 
        fargs=(accel_line, accel_data, accel_data_lock, config, analyzer, analysis_lock),
        interval=config.ACCEL_UPDATE_INTERVAL,  # Use config value
        blit=True,
        cache_frame_data=False
    )
    
    # Log performance settings
    logger.info(f"Visualization initialized with optimized performance settings")
    logger.info(f"LiDAR update interval: {config.LIDAR_UPDATE_INTERVAL}ms, Accelerometer update interval: {config.ACCEL_UPDATE_INTERVAL}ms")
    
    return fig_lidar, fig_accel, lidar_ani, accel_ani
