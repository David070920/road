import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import logging
from datetime import datetime

from .lidar_plots import update_lidar_plot
from .accel_plots import update_accel_plot

logger = logging.getLogger("SensorFusion")

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
    
    # Initialize variables
    fig_lidar = None
    fig_accel = None
    lidar_ani = None
    accel_ani = None
    
    # LiDAR visualization - only if enabled
    if getattr(config, 'ENABLE_LIDAR_GRAPH', True):
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
        
        ax_lidar.set_rmax(1200)  # Set maximum distance to display
        
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
            interval=config.LIDAR_UPDATE_INTERVAL,
            blit=True,
            cache_frame_data=False
        )
    else:
        logger.info("LiDAR visualization disabled in configuration")
    
    # Accelerometer visualization - only if enabled
    if getattr(config, 'ENABLE_ACCEL_GRAPH', True):
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
                    fig_accel.canvas.manager.window.wm_attributes("-topmost", 0)
            
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
            interval=config.ACCEL_UPDATE_INTERVAL,
            blit=True,
            cache_frame_data=False
        )
    else:
        logger.info("Accelerometer visualization disabled in configuration")
    
    # Log performance settings
    logger.info(f"Visualization initialized with optimized performance settings")
    logger.info(f"LiDAR graph: {getattr(config, 'ENABLE_LIDAR_GRAPH', True)}, Accelerometer graph: {getattr(config, 'ENABLE_ACCEL_GRAPH', True)}")
    
    return fig_lidar, fig_accel, lidar_ani, accel_ani
