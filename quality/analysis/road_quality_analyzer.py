import numpy as np
import logging
from scipy.signal import find_peaks
from collections import deque
from datetime import datetime
import time
import os

logger = logging.getLogger("SensorFusion")

class RoadQualityAnalyzer:
    def __init__(self, config, sensor_fusion=None):
        self.config = config
        self.sensor_fusion = sensor_fusion  # Store reference to SensorFusion instance
        
        # Store detected events with timestamps and GPS coordinates
        self.events = []
        
        # Quality metrics
        self.current_quality_score = 100  # 0-100 scale, 100 is perfect
        self.segment_scores = deque(maxlen=10)  # Store recent segment scores
        
        # Bump detection variables
        self.accel_baseline = 0
        self.accel_threshold = 0.5  # Starting threshold in g
        self.calibration_samples = []
        self.is_calibrated = False
        
        # Spectral analysis variables
        self.fft_window = deque(maxlen=128)  # Power of 2 for efficient FFT
        self.dominant_frequencies = deque(maxlen=5)  # Track recent dominant frequencies
        self.road_texture_score = 50  # 0-100 scale (smooth to rough)
        
        # LiDAR road analysis variables - With fixed values instead of calibration
        self.lidar_distance_history = deque(maxlen=50)  # Store recent measurements
        self.lidar_quality_score = 80  # Initialize with a reasonable default value
        self.lidar_segment_scores = deque(maxlen=10)
        
        # Add performance tracking
        self.processing_times = deque(maxlen=50)
        self.enable_profiling = True  # Set to False in production
        
        # Cache for pre-computed values
        self._angle_cache = {}  # Cache for angle conversions
        self._last_quality_calculation = 0  # Timestamp of last calculation
        self._quality_calculation_interval = 0.1  # Minimum seconds between recalculations
        
        # Combined quality score
        self.combined_quality_score = 100  # Initialize with perfect score
        self.last_quality_scores = deque(maxlen=5)  # Track recent combined scores
        self.quality_change_rate = 0  # Rate of change in combined quality score
        self.transition_detector = deque(maxlen=8)  # For detecting quality transitions
        
        # Environmental calibration factors
        self.temp_calibration_factor = 1.0
        self.pressure_calibration_factor = 1.0
        
        logger.debug("Road Quality Analyzer initialized")
        self.event_confidence_threshold = 0.8  # Minimum confidence to report events
        self.recent_event_locations = {}  # Track recent events by location to avoid duplicates
        
    # ...existing methods...

    def get_recent_events(self, count=5):
        """Get the most recent road events"""
        return self.events[-count:] if self.events else []
        
    def quality_to_color(self, quality_score):
        """Convert a quality score (0-100) to a color in hex format.
        
        0   = Red   (#FF0000)
        50  = Yellow (#FFFF00)
        100 = Green (#00FF00)
        
        Other values create a gradient between these colors.
        
        Args:
            quality_score (float): Road quality score from 0-100
            
        Returns:
            str: Hex color code in format #RRGGBB
        """
        # Ensure the quality score is within bounds
        quality_score = max(0, min(100, quality_score))
        
        # For scores from 0-50 (red to yellow)
        if quality_score <= 50:
            # Red stays at FF, green increases from 00 to FF
            red = 255
            green = int((quality_score / 50) * 255)
            blue = 0
        # For scores from 50-100 (yellow to green)
        else:
            # Red decreases from FF to 00, green stays at FF
            red = int(((100 - quality_score) / 50) * 255)
            green = 255
            blue = 0
            
        # Convert to hex format
        hex_color = f"#{red:02X}{green:02X}{blue:02X}"
        return hex_color
        
    def log_gps_quality_color(self, gps_data, output_file=None):
        """Log the GPS coordinates and road quality color to a CSV file.
        
        Args:
            gps_data (dict): Dictionary containing GPS data with lat and lon
            output_file (str): File name for the CSV output. If None, uses config.
            
        Returns:
            bool: True if log was successful, False otherwise
        """
        try:
            # Use config value for output file if not specified
            if output_file is None:
                # Use measurements folder path
                measurements_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                                             "gui_app", "measurements")
                
                # Create measurements directory if it doesn't exist
                if not os.path.exists(measurements_dir):
                    os.makedirs(measurements_dir)
                    logger.info(f"Created measurements directory: {measurements_dir}")
                
                # Set the output file path in the measurements directory
                output_file = os.path.join(measurements_dir, 
                                          getattr(self.config, 'GPS_QUALITY_LOG_FILE', "road_quality_map.csv"))
            
            # Get the current quality score
            quality_score = self.combined_quality_score
            
            # Convert quality score to color
            color = self.quality_to_color(quality_score)
            
            # Get the latitude and longitude
            lat = gps_data.get("lat", 0)
            lon = gps_data.get("lon", 0)
            
            # Always log data, even when GPS coordinates are 0
            # Check if file exists to write header
            file_exists = os.path.isfile(output_file)
            
            # Write to CSV file
            with open(output_file, "a") as f:
                # Write header if file doesn't exist
                if not file_exists:
                    f.write("latitude,longitude,color,quality_score,timestamp\n")
                
                # Write data row
                timestamp = datetime.now().isoformat()
                f.write(f"{lat},{lon},{color},{quality_score},{timestamp}\n")
                
            logger.debug(f"Logged road quality: lat={lat}, lon={lon}, quality={quality_score}, color={color}")
            return True
            
        except Exception as e:
            logger.error(f"Error logging road quality data: {e}")
            return False

    def get_road_classification_from_score(self, score):
        """Get a textual classification based on a quality score"""
        if score >= 90:
            return "Excellent"
        elif score >= 75:
            return "Good"
        elif score >= 60:
            return "Fair"
        elif score >= 40:
            return "Poor"
        else:
            return "Very Poor"
    
    def get_road_classification(self):
        """Get a textual classification of the current road quality"""
        # Use LiDAR-based score instead of accelerometer-based score
        return self.get_road_classification_from_score(self.lidar_quality_score)
        
    def get_combined_road_classification(self):
        """Get a textual classification based on the combined road quality score"""
        return self.get_road_classification_from_score(self.combined_quality_score)
        
    def calculate_lidar_road_quality(self, lidar_data, temp_data=None, pressure_data=None):
        """Calculate road quality score based on LiDAR data with enhanced responsiveness.
        
        Args:
            lidar_data (list): List of LiDAR data points
            temp_data (list, optional): Temperature data
            pressure_data (list, optional): Pressure data
            
        Returns:
            float: The calculated LiDAR road quality score
        """
        # Early return if no data is available
        if not lidar_data:
            logger.debug("No LiDAR data available for road quality calculation")
            return self.lidar_quality_score
            
        # Rate limiting to avoid excessive calculations but allow for rapid change detection
        current_time = time.time()
        time_since_last = current_time - self._last_quality_calculation
        
        # Dynamic rate limiting - calculate more frequently during rapid changes
        if time_since_last < self._quality_calculation_interval:
            # Check if we're in a period of rapid change
            if hasattr(self, 'quality_change_rate') and self.quality_change_rate < 15:
                # If not changing rapidly, maintain rate limiting
                return self.lidar_quality_score
        
        self._last_quality_calculation = current_time
        
        # Start timing if profiling is enabled
        start_time = time.time() if self.enable_profiling else 0
                
        # Extract valid points for analysis
        valid_points = []
        angles_deg = []
        distances = []
        
        # Process all points in a single pass to avoid multiple iterations
        for point in lidar_data:
            angle_deg = point[0]
            distance = point[1]
            
            # Use cached angle conversions when possible
            if angle_deg in self._angle_cache:
                converted_angle = self._angle_cache[angle_deg]
            else:
                # Convert 315-360 degrees to -45-0 degrees
                converted_angle = angle_deg - 360 if angle_deg >= 315 and angle_deg <= 360 else angle_deg
                self._angle_cache[angle_deg] = converted_angle
                
            # Use a wider angle range for road profile analysis (-35 to 35 degrees)
            if -35 <= converted_angle <= 35:
                valid_points.append((converted_angle, distance))
                angles_deg.append(converted_angle)
                distances.append(distance)
        
        if len(valid_points) < 8:
            logger.debug(f"Not enough valid LiDAR points for analysis: {len(valid_points)} (need 8+)")
            return self.lidar_quality_score
            
        # Convert to numpy arrays for faster processing
        angles_deg = np.array(angles_deg)
        distances = np.array(distances)
        
        # Apply pressure calibration to distances if available
        if hasattr(self, 'pressure_calibration_factor') and self.pressure_calibration_factor != 1.0:
            distances = distances * self.pressure_calibration_factor
        
        # Convert angles to radians - do once for all calculations
        angles_rad = np.radians(angles_deg)
        
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Analyzing road quality with {len(valid_points)} LiDAR points")
        
        # Direct height estimation without relying on calibration
        # Step 1: Estimate d₀ (LiDAR height from ground) 
        center_mask = np.abs(angles_deg) < 5
        if np.any(center_mask):
            estimated_height = np.median(distances[center_mask])
        else:
            # If no center points available, estimate height using min distance
            estimated_height = np.min(distances) * 1.05  # Add 5% margin
        
        # Step 2: Calculate expected distances for a flat road using cosine model
        cos_values = np.cos(angles_rad)
        # Use vectorized maximum to avoid loops
        cos_values = np.maximum(cos_values, 0.1)  # Prevent values too close to zero
        expected_distances = estimated_height / cos_values
        
        # Step 3: Calculate deviations from the expected distances (residuals)
        residuals = distances - expected_distances
        
        # Step 4: Determine if the surface is convex or concave (road crown or dip)
        adjusted_residuals = residuals
        if len(angles_deg) >= 5:  # Need at least 5 points for a meaningful fit
            try:
                # Try quadratic fit to handle road crown/camber
                quad_coeffs = np.polyfit(angles_deg, residuals, min(2, len(angles_deg) - 1))
                quad_fit = np.polyval(quad_coeffs, angles_deg)
                # Remove the quadratic component from residuals
                adjusted_residuals = residuals - quad_fit
            except:
                adjusted_residuals = residuals
        
        # Calculate quality metrics on adjusted residuals - all vectorized operations
        mean_abs_deviation = np.mean(np.abs(adjusted_residuals))
        max_deviation = np.max(np.abs(adjusted_residuals))
        residual_std = np.std(adjusted_residuals)
        
        # Calculate R² equivalent with adjusted model
        ss_res = np.sum(adjusted_residuals**2)
        mean_distance = np.mean(distances)
        ss_tot = np.sum((distances - mean_distance)**2)
        r_squared = 1 - (ss_res / ss_tot if ss_tot > 0 else 0)
        
        # Adaptive scaling: determine reasonable thresholds based on the data
        measurement_scale = max(5.0, np.median(distances) * 0.001)  # 0.1% of median, min 5mm
        
        # Calculate quality score with simplified calculations
        base_score = 98
        linearity_penalty = (1 - r_squared) * 20
        std_scale = max(10.0, measurement_scale * 1.5)
        std_penalty = min(25, (residual_std / std_scale) * 25)
        max_dev_scale = max(30.0, measurement_scale * 3)
        max_penalty = min(30, (max_deviation / max_dev_scale) * 30)
        quality_score = max(0, base_score - linearity_penalty - std_penalty - max_penalty)
        
        # Boost scores for very good roads
        if quality_score > 90:
            quality_score = min(100, 90 + (quality_score - 90) * 2)
        
        # Detect and track quality transitions for responsive updates
        self.transition_detector.append(quality_score)
        if len(self.transition_detector) >= 3:
            recent_scores = list(self.transition_detector)[-3:]
            # Calculate the rate of change over the last measurements
            self.quality_change_rate = abs(recent_scores[-1] - recent_scores[0])
        
        # More responsive smoothing based on rate of change
        # Alpha (blend factor) increases during rapid changes for faster response
        alpha = min(0.8, max(0.2, self.quality_change_rate / 50))
        
        # Update quality score with exponential smoothing for faster response
        self.lidar_quality_score = (1 - alpha) * self.lidar_quality_score + alpha * quality_score
        
        # Also keep segment scores for trend analysis
        self.lidar_segment_scores.append(quality_score)
        
        # Conditional logging based on level
        if self.enable_profiling:
            processing_time = time.time() - start_time
            self.processing_times.append(processing_time)
            if len(self.processing_times) % 10 == 0:
                avg_time = np.mean(self.processing_times) * 1000  # Convert to ms
                logger.debug(f"LiDAR quality calculation avg time: {avg_time:.2f}ms")
        
        # Only log detailed quality metrics if debug is enabled
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Road quality: r²={r_squared:.3f}, std={residual_std:.2f}mm, max_dev={max_deviation:.2f}mm")
            logger.debug(f"Quality score: {quality_score:.1f} → smoothed: {self.lidar_quality_score:.1f} (alpha={alpha:.2f})")
        
        return self.lidar_quality_score
        
    def detect_road_events(self, accel_data, gps_data):
        """Detect bumps, potholes and other road events from accelerometer data"""
        # Skip detection if disabled in config
        if not getattr(self.config, 'EVENT_DETECTION_ENABLED', True):
            return []
            
        if not self.is_calibrated:
            if not self.calibrate(accel_data):
                return []
        
        if len(accel_data) < 10:  # Need some data to analyze
            return []
            
        # Get recent samples
        samples = list(accel_data)[-20:]
        
        # Convert to numpy array and remove baseline
        signal = np.array(samples) - self.accel_baseline
        
        # Get minimum magnitude threshold from config
        min_magnitude = getattr(self.config, 'MIN_ACCEL_EVENT_MAGNITUDE', 0.5)
        
        # Improved detection: Use adaptive threshold based on recent signal variance
        local_variance = np.var(signal)
        adaptive_threshold = max(min_magnitude, self.accel_threshold * (1 + 0.5 * np.sqrt(local_variance)))
        
        # Find peaks (both positive and negative) with the adaptive threshold
        pos_peaks, _ = find_peaks(signal, height=adaptive_threshold)
        neg_peaks, _ = find_peaks(-signal, height=adaptive_threshold)
        
        # Combine peaks and sort by time
        all_peaks = [(idx, signal[idx]) for idx in pos_peaks] + [(idx, signal[idx]) for idx in neg_peaks]
        all_peaks.sort(key=lambda x: x[0])
        
        # Analyze peaks for events
        new_events = []
        min_severity = getattr(self.config, 'MIN_EVENT_SEVERITY', 30)
        
        for idx, magnitude in all_peaks:
            # Improved algorithm: Check for isolated peaks (not part of a sequence)
            is_isolated = True
            for other_idx, _ in all_peaks:
                if other_idx != idx and abs(other_idx - idx) <= 2:
                    is_isolated = False
                    break
            
            # Only consider peaks that exceed our threshold and are isolated
            if abs(magnitude) > adaptive_threshold and is_isolated:
                event_type = "Pothole" if magnitude < 0 else "Bump"
                
                # Improved severity calculation: Use logarithmic scale for more differentiation
                severity = min(100, int(40 * np.log10(1 + abs(magnitude) / min_magnitude)))
                
                # Only record events that meet the minimum severity threshold
                if severity >= min_severity:
                    # Create event with GPS data
                    event = {
                        "type": event_type,
                        "severity": severity,
                        "magnitude": float(magnitude),
                        "source": "Accelerometer",
                        "timestamp": datetime.now().isoformat(),
                        "lat": gps_data["lat"],
                        "lon": gps_data["lon"]
                    }
                    
                    new_events.append(event)
        
        # Add to master event list
        self.events.extend(new_events)
        
        return new_events
        
    def calibrate(self, accel_data):
        """Calibrate the analyzer with current accelerometer data and environmental data"""
        if len(accel_data) < 50:  # Need enough samples to calibrate
            return False
            
        # Calculate the baseline (average) and noise level
        samples = list(accel_data)[-50:]
        self.accel_baseline = np.mean(samples)
        std_dev = np.std(samples)
        
        # Set threshold at 2.5x standard deviation - can be adjusted
        self.accel_threshold = max(0.3, 2.5 * std_dev)  # Minimum 0.3g threshold
        
        # Get temperature data if available
        temp_data = None
        if hasattr(self.sensor_fusion, 'env_data'):
            temp_data = self.sensor_fusion.env_data.get('temperature')
            
        # Get pressure data if available
        pressure_data = None
        if hasattr(self.sensor_fusion, 'env_data'):
            pressure_data = self.sensor_fusion.env_data.get('pressure')
        
        # Adjust calibration based on temperature if available
        if temp_data is not None:
            # Temperature can affect sensor sensitivity
            current_temp = float(temp_data)
            # Reference temperature (20°C/68°F is typical)
            reference_temp = getattr(self.config, 'REFERENCE_TEMPERATURE', 20.0)
            # Adjust threshold based on temperature difference (±0.5% per °C)
            temp_diff = current_temp - reference_temp
            self.temp_calibration_factor = 1.0 + (temp_diff * 0.005)
            # Apply temperature calibration
            self.accel_threshold *= self.temp_calibration_factor
            
        # Adjust calibration based on pressure if available
        if pressure_data is not None:
            # Barometric pressure can affect LiDAR readings
            current_pressure = float(pressure_data)
            # Reference pressure (1013.25 hPa is standard at sea level)
            reference_pressure = getattr(self.config, 'REFERENCE_PRESSURE', 1013.25)
            # Adjust factor based on pressure difference (±0.1% per 10 hPa)
            pressure_diff = current_pressure - reference_pressure
            self.pressure_calibration_factor = 1.0 + (pressure_diff * 0.0001)
            
        self.is_calibrated = True
        logger.debug(f"Calibrated: baseline={self.accel_baseline:.3f}g, threshold={self.accel_threshold:.3f}g, "
                     f"temp_factor={self.temp_calibration_factor:.3f}, pressure_factor={self.pressure_calibration_factor:.3f}")
        return True
        
    def analyze_frequency_spectrum(self, accel_data):
        """Analyze the frequency spectrum of vibrations to classify road texture - Optimized version"""
        if len(accel_data) < 10:
            return self.road_texture_score
        
        # Only update FFT periodically rather than with every analyze call
        current_time = time.time()
        if hasattr(self, '_last_fft_time') and current_time - self._last_fft_time < 0.5:
            return self.road_texture_score
            
        self._last_fft_time = current_time
            
        # Start timing if profiling is enabled
        start_time = time.time() if self.enable_profiling else 0
        
        # Extend the FFT window with new data (more efficient than replacing)
        self.fft_window.extend(list(accel_data)[-10:])
        
        if len(self.fft_window) < 64:  # Need sufficient data for FFT
            return self.road_texture_score
        
        # Optimize: Pre-calculate the Hanning window once
        if not hasattr(self, '_hanning_window') or len(self._hanning_window) != len(self.fft_window):
            self._hanning_window = np.hanning(len(self.fft_window))
        
        # Perform FFT on the window - optimize with pre-computed values
        signal_array = np.array(self.fft_window)
        signal = signal_array - np.mean(signal_array)  # Remove DC component
        
        # Apply window function and perform FFT in one optimized step
        fft_result = np.abs(np.fft.rfft(signal * self._hanning_window))
        
        # Get frequency bins - only compute if we need to update dominant frequencies
        if fft_result.size > 1:  # Make sure we have meaningful results
            freq_bins = np.fft.rfftfreq(len(signal), d=0.1)  # Assuming 10Hz sampling
            
            # Optimize: Use simplified peak finding for performance
            peak_indices, _ = find_peaks(fft_result[1:], height=np.max(fft_result[1:]) * 0.3)
            peak_indices = peak_indices + 1  # Adjust for the DC offset
            
            if len(peak_indices) > 0:
                # Optimize: Use numpy's argmax instead of sorting
                if len(peak_indices) > 1:
                    peak_amplitudes = fft_result[peak_indices]
                    max_peak_idx = peak_indices[np.argmax(peak_amplitudes)]
                else:
                    max_peak_idx = peak_indices[0]
                
                dominant_freq = freq_bins[max_peak_idx]
                self.dominant_frequencies.append(dominant_freq)
                
                # Classify road texture with optimized logic
                if dominant_freq < 3:
                    texture = "Undulating"
                    self.road_texture_score = max(40, self.road_texture_score - 5)
                elif dominant_freq < 15:
                    texture = "Rough"
                    # Use simpler averaging formula
                    self.road_texture_score = (self.road_texture_score * 0.8) + (50 * 0.2)
                else:
                    texture = "Fine-grained"
                    self.road_texture_score = min(60, self.road_texture_score + 5)
                
                # Only log at appropriate level and when value changes significantly
                if logger.isEnabledFor(logging.DEBUG) and (
                   not hasattr(self, '_last_texture') or self._last_texture != texture):
                    logger.debug(f"Road texture: {texture} (dominant freq: {dominant_freq:.1f}Hz)")
                    self._last_texture = texture
        
        # Performance logging
        if self.enable_profiling:
            fft_time = time.time() - start_time
            if not hasattr(self, '_fft_times'):
                self._fft_times = deque(maxlen=20)
            self._fft_times.append(fft_time * 1000)  # ms
            if len(self._fft_times) % 10 == 0:
                logger.debug(f"FFT processing avg time: {np.mean(self._fft_times):.2f}ms")
                
        return self.road_texture_score