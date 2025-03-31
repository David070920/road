"""
Helper module for system monitoring functionality
"""
import time
import logging
from datetime import datetime

logger = logging.getLogger("WebServer")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    logger.warning("psutil module not found. System monitoring will use mock data.")
    HAS_PSUTIL = False

def get_system_status():
    """Get system status information including CPU, memory, disk usage"""
    try:
        if not HAS_PSUTIL:
            return get_mock_system_status()
            
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Get memory usage
        ram = psutil.virtual_memory()
        
        # Get disk usage for the root filesystem
        disk = psutil.disk_usage('/')
        
        # Get uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        
        # Format uptime as hours and minutes
        uptime_hours = uptime.total_seconds() // 3600
        uptime_minutes = (uptime.total_seconds() % 3600) // 60
        
        # Get network information
        try:
            net_connections = len(psutil.net_connections())
            net_status = 'Connected' if net_connections > 0 else 'Disconnected'
        except (psutil.AccessDenied, PermissionError):
            # On some systems, we might not have permission to get connections
            net_io = psutil.net_io_counters()
            net_status = 'Connected' if net_io.bytes_sent > 0 or net_io.bytes_recv > 0 else 'Disconnected'
            net_connections = 0
        
        # Get platform information
        import platform
        platform_info = platform.platform()
        
        return {
            'cpu_usage': f"{cpu_percent:.1f}%",
            'memory_usage': f"{ram.percent:.1f}%",
            'disk_usage': f"{disk.percent:.1f}%",
            'network': {
                'status': net_status,
                'connections': net_connections
            },
            'uptime': f"{int(uptime_hours)}h {int(uptime_minutes)}m",
            'platform': platform_info,
            'has_real_data': True
        }
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return get_mock_system_status()

def get_mock_system_status():
    """Return mock system status when real data can't be obtained"""
    return {
        'cpu_usage': '25.0%',
        'memory_usage': '45.0%',
        'disk_usage': '32.0%',
        'network': {
            'status': 'Connected',
            'connections': 3
        },
        'uptime': '3h 15m',
        'platform': 'Linux',
        'has_real_data': False
    }
