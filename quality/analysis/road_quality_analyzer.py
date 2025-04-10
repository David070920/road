import numpy as np
import logging
from scipy.signal import find_peaks
from collections import deque
from datetime import datetime
import time

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
        
    def calibrate(self, accel_data, temp_data=None, pressure_data=None):
        """Calibrate the analyzer with current accelerometer data and environmental data"""
        if len(accel_data) < 50:  # Need enough samples to calibrate
            return False
            
        # Calculate the baseline (average) and noise level
        samples = list(accel_data)[-50:]
        self.accel_baseline = np.mean(samples)
        std_dev = np.std(samples)
        
        # Set threshold at 2.5x standard deviation - can be adjusted
        self.accel_threshold = max(0.3, 2.5 * std_dev)  # Minimum 0.3g threshold
        
        # Adjust calibration based on temperature if available
        if temp_data is not None and len(temp_data) > 0:
            # Temperature can affect sensor sensitivity
            current_temp = float(temp_data[-1])
            # Reference temperature (20°C/68°F is typical)
            reference_temp = getattr(self.config, 'REFERENCE_TEMPERATURE', 20.0)
            # Adjust threshold based on temperature difference (±0.5% per °C)
            temp_diff = current_temp - reference_temp
            self.temp_calibration_factor = 1.0 + (temp_diff * 0.005)
            # Apply temperature calibration
            self.accel_threshold *= self.temp_calibration_factor
            
        # Adjust calibration based on pressure if available
        if pressure_data is not None and len(pressure_data) > 0:
            # Barometric pressure can affect LiDAR readings
            current_pressure = float(pressure_data[-1])
            # Reference pressure (1013.25 hPa is standard at sea level)
            reference_pressure = getattr(self.config, 'REFERENCE_PRESSURE', 1013.25)
            # Adjust factor based on pressure difference (±0.1% per 10 hPa)
            pressure_diff = current_pressure - reference_pressure
            self.pressure_calibration_factor = 1.0 + (pressure_diff * 0.0001)
            
        self.is_calibrated = True
        logger.debug(f"Calibrated: baseline={self.accel_baseline:.3f}g, threshold={self.accel_threshold:.3f}g, "
                     f"temp_factor={self.temp_calibration_factor:.3f}, pressure_factor={self.pressure_calibration_factor:.3f}")
        return True
        
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
        
    def calculate_road_quality(self, accel_data, window_size=50):
        """Calculate overall road quality score based on recent accelerometer data"""
        if len(accel_data) < window_size:
            return self.current_quality_score
            
        # Get the recent samples
        samples = list(accel_data)[-window_size:]
        signal = np.array(samples)
        
        if not self.is_calibrated:
            self.calibrate(accel_data)
        
        # Calculate metrics
        mean_abs_deviation = np.mean(np.abs(signal - self.accel_baseline))
        max_deviation = np.max(np.abs(signal - self.accel_baseline))
        variance = np.var(signal)
        
        # Calculate a quality score (0-100 scale)
        # Lower variance and deviations = higher score
        base_score = 100
        
        # Penalize based on variance (smoother roads have lower variance)
        variance_penalty = min(50, variance * 100)
        
        # Penalize based on maximum deviation (large bumps/potholes)
        max_deviation_penalty = min(30, max_deviation * 60)
        
        # Penalize based on mean deviation (overall roughness)
        mean_deviation_penalty = min(20, mean_abs_deviation * 40)
        
        # Calculate final score
        quality_score = max(0, base_score - variance_penalty - max_deviation_penalty - mean_deviation_penalty)
        
        # Smooth the score with previous readings for stability
        self.segment_scores.append(quality_score)
        self.current_quality_score = np.mean(self.segment_scores)
        
        return self.current_quality_score
        
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
    
    def calculate_lidar_road_quality(self, lidar_data, temp_data=None, pressure_data=None):
        """Calculate road quality score based on LiDAR data with enhanced responsiveness"""
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
    
    def _detect_lidar_events(self, residuals, angles, distances, quality_score):
        """Detect road events from LiDAR data"""
        # Skip detection if disabled in config
        if not getattr(self.config, 'EVENT_DETECTION_ENABLED', True):
            return []
            
        # Calculate a dynamic threshold based on the data
        if not hasattr(self, 'lidar_event_threshold'):
            median_abs_deviation = np.median(np.abs(residuals - np.median(residuals)))
            # Use MAD as a robust measure of variation (less sensitive to outliers than std)
            self.lidar_event_threshold = 3 * median_abs_deviation
            # Use configuration value if available, otherwise use default minimum
            min_lidar_magnitude = getattr(self.config, 'MIN_LIDAR_EVENT_MAGNITUDE', 5.0)
            self.lidar_event_threshold = max(min_lidar_magnitude, self.lidar_event_threshold)
        
        # Find indices where residuals exceed threshold (potential potholes/bumps)
        event_indices = np.where(np.abs(residuals) > self.lidar_event_threshold)[0]
        
        # Group adjacent indices into single events with improved clustering
        events = []
        if len(event_indices) > 0:
            # Sort indices to ensure proper clustering
            event_indices = np.sort(event_indices)
            
            # Use a smarter clustering approach
            try:
                from scipy.cluster.hierarchy import fclusterdata
                if len(event_indices) > 1:
                    # Convert to 2D points (index, residual value)
                    points = np.column_stack((event_indices, residuals[event_indices]))
                    # Scale the points to give more weight to the index dimension
                    points[:, 0] = points[:, 0] / max(1, np.max(points[:, 0])) * 10
                    
                    # Try clustering with scipy
                    clusters = fclusterdata(points, t=1.5, criterion='distance')
                    unique_clusters = np.unique(clusters)
                    
                    for cluster_id in unique_clusters:
                        # Get all indices in this cluster
                        cluster_indices = event_indices[clusters == cluster_id]
                        if len(cluster_indices) > 0:
                            events.append(cluster_indices.tolist())
                else:
                    # Just one point
                    events.append([event_indices[0]])
            except:
                # Fallback to simple adjacency-based grouping if clustering fails
                current_event = [event_indices[0]]
                for i in range(1, len(event_indices)):
                    if event_indices[i] <= event_indices[i-1] + 2:  # Allow for small gaps
                        current_event.append(event_indices[i])
                    else:
                        events.append(current_event)
                        current_event = [event_indices[i]]
                
                # Add the last event
                if current_event:
                    events.append(current_event)
        
        # Process each detected event
        new_events = []
        min_severity = getattr(self.config, 'MIN_EVENT_SEVERITY', 30)
        
        for event_indices in events:
            # Calculate event properties
            event_residuals = residuals[event_indices]
            max_idx = event_indices[np.argmax(np.abs(event_residuals))]
            max_residual = residuals[max_idx]
            event_angle = angles[max_idx]
            event_distance = distances[max_idx]
            
            # Skip small events (noise)
            if abs(max_residual) < self.lidar_event_threshold:
                continue
                
            # Improved type classification
            # Positive residual = LiDAR sees ground closer than expected = pothole
            # Negative residual = LiDAR sees ground farther than expected = bump
            event_type = "Pothole" if max_residual > 0 else "Bump"
            
            # Improved severity calculation with logarithmic scale
            min_lidar_magnitude = getattr(self.config, 'MIN_LIDAR_EVENT_MAGNITUDE', 5.0)
            severity = min(100, int(40 * np.log10(1 + abs(max_residual) / min_lidar_magnitude)))
            
            # Only create events for significant anomalies
            if severity >= min_severity:
                # Create event with GPS data and LiDAR-specific properties
                gps_data = {"lat": 0, "lon": 0}
                if hasattr(self.sensor_fusion, 'gps_data'):
                    gps_data = self.sensor_fusion.gps_data
                    
                event = {
                    "type": event_type,
                    "severity": severity,
                    "magnitude": float(abs(max_residual)),  # Use residual as magnitude
                    "source": "LiDAR",  # Mark as LiDAR-detected event
                    "angle": float(event_angle),  # LiDAR-specific: detection angle
                    "distance": float(event_distance),  # LiDAR-specific: detection distance
                    "timestamp": datetime.now().isoformat(),
                    "lat": gps_data["lat"],
                    "lon": gps_data["lon"]
                }
                
                new_events.append(event)
        
        # Add to master event list
        self.events.extend(new_events)
        
        return new_events
        
    def calculate_combined_road_quality(self, accel_data=None, lidar_data=None, temp_data=None, pressure_data=None):
        """Calculate a comprehensive road quality score using data from all available sensors"""
        # Get individual quality scores if data is available
        accel_score = None
        if accel_data is not None and len(accel_data) > 0:
            accel_score = self.calculate_road_quality(accel_data)
            
        lidar_score = None
        if lidar_data is not None and len(lidar_data) > 0:
            lidar_score = self.calculate_lidar_road_quality(lidar_data, temp_data, pressure_data)
            
        # Default weights for sensor fusion
        accel_weight = getattr(self.config, 'ACCEL_WEIGHT', 0.4)
        lidar_weight = getattr(self.config, 'LIDAR_WEIGHT', 0.6)
        
        # Adjust weights based on data reliability
        # If driving very slowly, LiDAR is more reliable
        # If driving quickly, accelerometer may capture more details
        if hasattr(self.sensor_fusion, 'speed') and self.sensor_fusion.speed is not None:
            speed = self.sensor_fusion.speed
            # At low speeds, favor LiDAR; at high speeds, favor accelerometer
            if speed < 5:  # below 5 km/h or mph
                accel_weight = 0.2
                lidar_weight = 0.8
            elif speed > 60:  # above 60 km/h or mph
                accel_weight = 0.6
                lidar_weight = 0.4
        
        # Calculate combined score
        if accel_score is not None and lidar_score is not None:
            # Both sensors available - weighted average
            combined_score = (accel_score * accel_weight) + (lidar_score * lidar_weight)
        elif lidar_score is not None:
            # Only LiDAR available
            combined_score = lidar_score
        elif accel_score is not None:
            # Only accelerometer available
            combined_score = accel_score
        else:
            # No new data - return last combined score
            return self.combined_quality_score
            
        # Track score changes for responsiveness adjustment
        self.last_quality_scores.append(combined_score)
        if len(self.last_quality_scores) > 5:
            self.last_quality_scores.pop(0)
            
        # Calculate rate of change for dynamic responsiveness
        if len(self.last_quality_scores) >= 2:
            self.quality_change_rate = abs(self.last_quality_scores[-1] - self.last_quality_scores[-2])
            
        # Apply exponential smoothing with adaptive parameter
        alpha = min(0.8, max(0.2, self.quality_change_rate / 50))
        self.combined_quality_score = (1 - alpha) * self.combined_quality_score + alpha * combined_score
        
        # Round to 1 decimal place for display
        self.combined_quality_score = round(self.combined_quality_score, 1)
        
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Combined quality: {self.combined_quality_score:.1f} (accel: {accel_score:.1f}, "
                        f"lidar: {lidar_score:.1f}, alpha: {alpha:.2f})")
            
        return self.combined_quality_score
        
    def detect_combined_road_events(self, accel_data=None, lidar_data=None, gps_data=None, temp_data=None, pressure_data=None):
        """Detect road events using data from multiple sensors for higher accuracy"""
        # Skip detection if disabled in config
        if not getattr(self.config, 'EVENT_DETECTION_ENABLED', True):
            return []
            
        new_events = []
        accel_events = []
        lidar_events = []
        
        # Get accelerometer-based events if data available
        if accel_data is not None and len(accel_data) > 10 and gps_data is not None:
            accel_events = self.detect_road_events(accel_data, gps_data)
            
        # Get LiDAR-based events if data available
        if lidar_data is not None and len(lidar_data) > 8:
            # First calculate quality to trigger event detection
            self.calculate_lidar_road_quality(lidar_data, temp_data, pressure_data)
            # Get the latest events (events are detected inside calculate_lidar_road_quality)
            if self.events:
                lidar_events = [event for event in self.events[-10:] if event.get('source') == 'LiDAR']
        
        # Create a set of locations to check for duplicate events
        # Define a small area (approximately 5-10m radius) to consider as "same location"
        location_precision = 5  # Decimal places in GPS coordinates (5 is ~1.1m precision)
        event_locations = {}
        
        # Process all events from both sensors
        all_events = accel_events + lidar_events
        for event in all_events:
            # Get GPS location
            lat = event.get('lat', 0)
            lon = event.get('lon', 0)
            
            # Skip events with invalid GPS data
            if lat == 0 and lon == 0:
                continue
                
            # Round coordinates to create location bins
            location_key = (round(lat, location_precision), round(lon, location_precision))
            
            # Check if we already have an event at this location
            if location_key in event_locations:
                existing_event = event_locations[location_key]
                
                # If this is from a different source than the existing event,
                # increase the confidence (corroboration between sensors)
                if event.get('source') != existing_event.get('source'):
                    # Average severity of both detections
                    new_severity = (event.get('severity', 0) + existing_event.get('severity', 0)) / 2
                    existing_event['severity'] = int(new_severity)
                    # Mark as confirmed by multiple sensors
                    existing_event['confidence'] = min(1.0, existing_event.get('confidence', 0.7) + 0.3)
                    existing_event['sources'] = [existing_event.get('source'), event.get('source')]
                    
                elif event.get('severity', 0) > existing_event.get('severity', 0):
                    # This is a stronger detection from same source, update severity
                    existing_event['severity'] = event.get('severity', 0)
                    # Slightly increase confidence
                    existing_event['confidence'] = min(1.0, existing_event.get('confidence', 0.7) + 0.1)
            else:
                # New event location
                event['confidence'] = 0.7  # Start with moderate confidence
                event['sources'] = [event.get('source')]
                event_locations[location_key] = event
                
        # Only include events with sufficient confidence
        for location, event in event_locations.items():
            if event.get('confidence', 0) >= self.event_confidence_threshold:
                # Check if this is truly a new event or if we've seen it recently
                # Use a simplified time-based key
                time_key = event.get('timestamp', '')[:10]  # YYYY-MM-DD
                location_time_key = f"{location[0]}-{location[1]}-{time_key}"
                
                # If we haven't seen this event yet today, add it
                if location_time_key not in self.recent_event_locations:
                    new_events.append(event)
                    # Store this location to avoid duplicate reports
                    self.recent_event_locations[location_time_key] = time.time()
        
        # Clean up old entries in recent_event_locations (older than 1 hour)
        current_time = time.time()
        keys_to_remove = [k for k, v in self.recent_event_locations.items() 
                          if current_time - v > 3600]
        for key in keys_to_remove:
            del self.recent_event_locations[key]
        
        # Add to master event list
        self.events.extend(new_events)
        
        return new_events
        
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

    def get_recent_events(self, count=5):
        """Get the most recent road events"""
        return self.events[-count:] if self.events else []