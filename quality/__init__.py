"""
Road Quality Analysis System
----------------------------
A package for measuring road quality using various sensors.
"""

# Import main functionality for easier access
from .core.sensor_fusion import SensorFusion
from .config import Config
from .analysis.road_quality_analyzer import RoadQualityAnalyzer

__version__ = "1.1.0"
