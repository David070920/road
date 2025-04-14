import os
from pathlib import Path

class Config:
    # General settings
    MAX_DATA_POINTS = 100  # Maximum data points to store in memory
    GPS_MAP_UPDATE_INTERVAL = 10   # GPS map update interval in seconds
    GPS_QUALITY_LOG_INTERVAL = 2.0  # GPS quality logging interval in seconds
    GPS_QUALITY_LOG_FILE = "road_quality_map.csv"  # Default filename for quality log
    
    # Visualization performance settings
    LIDAR_UPDATE_INTERVAL = 10  # LiDAR visualization update interval in ms
    ACCEL_UPDATE_INTERVAL = 300  # Accelerometer visualization update interval in ms
    MAX_FRAME_SKIP = 2     # Maximum number of frames to skip for smoother rendering
    
    # LiDAR visualization fine-tuning
    LIDAR_CHART_UPDATE_INTERVAL = 0.01  # Time between visual refreshes in seconds (was hardcoded as 0.2)
    LIDAR_CHART_CHECK_INTERVAL = 10   # How often to check for updates in ms (was hardcoded as 100)
    LIDAR_DATA_BATCH_INTERVAL = 0.01    # Time between data batch updates in seconds (was hardcoded as 0.2)
    LIDAR_MAX_POINTS = 120            # Maximum number of points to display (was hardcoded as 120)
    
    # Visualization settings
    ENABLE_VISUALIZATION = True  # Master switch to enable/disable all visualization graphs
    ENABLE_LIDAR_GRAPH = True    # Enable/disable LiDAR visualization
    ENABLE_ACCEL_GRAPH = True    # Enable/disable accelerometer visualization
    
    # Web/GUI Mode control
    USE_WEB_VISUALIZATION = False  # If True, optimizes for web. If False, optimizes for GUI
    OPTIMIZE_RESOURCES = True      # If True, reduces update frequency when not in active view
    
    # Resource optimization settings
    BACKGROUND_UPDATE_MULTIPLIER = 5  # Multiply update interval by this when in background
    WEB_ACTIVE_UPDATE_INTERVAL = 200  # Update interval when web is primary visualization (ms)
    WEB_BACKGROUND_UPDATE_INTERVAL = 1000  # Update interval when web is secondary (ms)
    GUI_BACKGROUND_UPDATE_INTERVAL = 2000  # Update interval for GUI when in background (ms)
    
    # User and system information
    USER_LOGIN = "David070920"
    SYSTEM_START_TIME = "2025-03-29 11:17:21"
    
    # LiDAR settings
    LIDAR_PORT = '/dev/ttyUSB0'
    LIDAR_SCAN_MODE = 0    # Scan mode (0-2)
    
    # LiDAR angle settings for road quality analysis
    LIDAR_MIN_ANGLE = -15# Minimum display angle (converted from 315° to -45° for polar plot)
    LIDAR_MAX_ANGLE = 15  # Maximum display angle
    LIDAR_FILTER_ANGLES = [(0, 15), (345, 360)]  # Angles to keep (min, max)
    
    # GPS settings
    GPS_PORT = '/dev/ttyACM0'
    GPS_BAUD_RATE = 9600
    GPS_TIMEOUT = 0.5
    
    # ICM20948 settings
    ICM20948_ADDRESS = 0x69
    ICM20948_WHO_AM_I = 0x00
    ICM20948_PWR_MGMT_1 = 0x06
    ICM20948_ACCEL_ZOUT_H = 0x31
    
    # Folium map settings
    ENABLE_GPS_MAP = False  # Disable external GPS map HTML file
    MAP_ZOOM_START = 15
    
    # Web server settings
    WEB_SERVER_HOST = '0.0.0.0'  # Listen on all interfaces
    WEB_SERVER_PORT = 8080       # Default port (will try next available if busy)
    WEB_UPDATE_INTERVAL = 200    # Update interval in milliseconds (legacy setting)
    
    # Web server advanced options
    WEB_CONNECTION_TIMEOUT = 30  # Socket connection timeout in seconds
    WEB_MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload size
    
    # Ngrok remote access settings
    ENABLE_NGROK = True  # Enable by default
    NGROK_AUTH_TOKEN = "1kHCNihdSF75RXdZOaII8jNdwLr_2F83BK8kuB8vBP4otk8Y7"  # Your ngrok auth token if you have one
    NGROK_REGION = "eu"  # Ngrok region: us, eu, ap, au, sa, jp, in
    NGROK_RETRY_COUNT = 3  # Number of times to retry starting ngrok
    NGROK_RETRY_DELAY = 2  # Seconds to wait between retries
    
    # AHT21 Temperature/Humidity sensor settings
    AHT21_ADDRESS = 0x38
    AHT21_INIT_COMMAND = [0xBE, 0x08, 0x00]
    AHT21_MEASURE_COMMAND = [0xAC, 0x33, 0x00]
    AHT21_RESET_COMMAND = 0xBA
    
    # BMX280 Pressure/Temperature sensor settings
    BMX280_ADDRESS = 0x77  # Can be 0x76 or 0x77, check your specific module
    BMX280_RESET_REGISTER = 0xE0
    BMX280_RESET_VALUE = 0xB6
    BMX280_CTRL_MEAS_REGISTER = 0xF4
    BMX280_CONFIG_REGISTER = 0xF5
    BMX280_PRESSURE_REGISTER = 0xF7
    BMX280_TEMP_REGISTER = 0xFA
    BMX280_CALIB_REGISTER = 0x88
    
    # Environmental data update interval (in seconds)
    ENV_UPDATE_INTERVAL = 2.0  # Update every 2 seconds to avoid unnecessary frequent readings
    
    # Road event detection settings
    MIN_ACCEL_EVENT_MAGNITUDE = 0.6  # Minimum accelerometer magnitude (in g) to detect an event
    MIN_LIDAR_EVENT_MAGNITUDE = 10.0  # Minimum LiDAR deviation (in mm) to detect an event
    MIN_EVENT_SEVERITY = 30  # Minimum severity score (0-100) for an event to be recorded
    EVENT_DETECTION_ENABLED = True  # Master switch to enable/disable event detection