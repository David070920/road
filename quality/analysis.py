import numpy as np
import logging
from scipy.signal import find_peaks
from scipy import stats
from collections import deque
from datetime import datetime
import time  # Add for performance measurements

logger = logging.getLogger("SensorFusion")

class RoadQualityAnalyzer:
    def __init__(self, config):
        self.config = config
        
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
        
        # LiDAR road analysis variables - Initialize with more realistic values
        self.lidar_baseline_distance = None
        self.lidar_calibrated = False
        self.lidar_distance_history = deque(maxlen=50)  # Store recent measurements
        self.lidar_quality_score = 80  # Initialize with a more realistic value than 100
        self.lidar_segment_scores = deque(maxlen=10)
        self.lidar_calibration_attempts = 0  # Track calibration attempts
        
        # Add performance tracking
        self.processing_times = deque(maxlen=50)
        self.enable_profiling = True  # Set to False in production
        
        # Cache for pre-computed values
        self._angle_cache = {}  # Cache for angle conversions
        self._last_quality_calculation = 0  # Timestamp of last calculation
        self._quality_calculation_interval = 0.1  # Minimum seconds between recalculations
        
        logger.info("Road Quality Analyzer initialized")
    
    def calibrate(self, accel_data):
        """Calibrate the analyzer with current accelerometer data"""
        if len(accel_data) < 50:  # Need enough samples to calibrate
            return False
            
        # Calculate the baseline (average) and noise level
        samples = list(accel_data)[-50:]
        self.accel_baseline = np.mean(samples)
        std_dev = np.std(samples)
        
        # Set threshold at 2.5x standard deviation - can be adjusted
        self.accel_threshold = max(0.3, 2.5 * std_dev)  # Minimum 0.3g threshold
        
        self.is_calibrated = True
        logger.info(f"Calibrated: baseline={self.accel_baseline:.3f}g, threshold={self.accel_threshold:.3f}g")
        return True
    
    def detect_road_events(self, accel_data, gps_data):
        """Detect bumps, potholes and other road events from accelerometer data"""
        if not self.is_calibrated:
            if not self.calibrate(accel_data):
                return []
        
        if len(accel_data) < 10:  # Need some data to analyze
            return []
            
        # Get recent samples
        samples = list(accel_data)[-20:]
        
        # Convert to numpy array and remove baseline
        signal = np.array(samples) - self.accel_baseline
        
        # Find peaks (both positive and negative)
        pos_peaks, _ = find_peaks(signal, height=self.accel_threshold)
        neg_peaks, _ = find_peaks(-signal, height=self.accel_threshold)
        
        # Combine peaks and sort by time
        all_peaks = [(idx, signal[idx]) for idx in pos_peaks] + [(idx, signal[idx]) for idx in neg_peaks]
        all_peaks.sort(key=lambda x: x[0])
        
        # Analyze peaks for events
        new_events = []
        for idx, magnitude in all_peaks:
            # Classify the event based on magnitude and shape
            if abs(magnitude) > self.accel_threshold * 2:
                event_type = "Pothole" if magnitude < 0 else "Bump"
                severity = min(100, int(abs(magnitude) / self.accel_threshold * 50))
                
                # Create event with GPS data
                event = {
                    "type": event_type,
                    "severity": severity,
                    "magnitude": float(magnitude),
                    "timestamp": datetime.now().isoformat(),
                    "lat": gps_data["lat"],
                    "lon": gps_data["lon"]
                }
                
                new_events.append(event)
                
                # Only log significant events
                if severity > 50:
                    logger.info(f"Detected {event_type}: severity={severity}, magnitude={magnitude:.3f}g")
        
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
            
            # Find dominant frequencies (excluding DC)
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
    
    def calibrate_lidar(self, lidar_data):
        """Calibrate the LiDAR analysis with current data"""
        if not lidar_data:
            self.lidar_calibration_attempts += 1
            if self.lidar_calibration_attempts % 10 == 0:  # Log only occasionally
                logger.warning(f"No LiDAR data available for calibration (attempt {self.lidar_calibration_attempts})")
            return False
        
        # Extract distances from valid points (only points directly below/in front)
        # Use a wider angle range to ensure we get enough points
        valid_points = []
        for point in lidar_data:
            angle_deg = point[0]
            distance = point[1]
            
            # Convert 315-360 degrees to -45-0 degrees
            if angle_deg >= 315 and angle_deg <= 360:
                angle_deg = angle_deg - 360
                
            # Widen the range to get more points (-15 to 15 degrees)
            if -15 <= angle_deg <= 15:
                valid_points.append(distance)
        
        if len(valid_points) < 5:  # Need enough points
            self.lidar_calibration_attempts += 1
            if self.lidar_calibration_attempts % 10 == 0:
                logger.warning(f"Not enough valid LiDAR points for calibration: {len(valid_points)} (need 5+)")
            return False
            
        # Calculate baseline distance (median to avoid outliers)
        self.lidar_baseline_distance = np.median(valid_points)
        logger.info(f"LiDAR calibrated: baseline distance={self.lidar_baseline_distance:.2f}mm with {len(valid_points)} points")
        self.lidar_calibrated = True
        
        # Force initial quality score to be lower to avoid starting at "perfect"
        # This ensures users see changes in the score
        self.lidar_quality_score = 80
        self.lidar_segment_scores.clear()
        self.lidar_segment_scores.append(80)
        
        return True
    
    def calculate_lidar_road_quality(self, lidar_data):
        """Calculate road quality score based on LiDAR data - Optimized version"""
        # Early return if no data is available
        if not lidar_data:
            logger.debug("No LiDAR data available for road quality calculation")
            return self.lidar_quality_score
            
        # Rate limiting to avoid excessive calculations
        current_time = time.time()
        if current_time - self._last_quality_calculation < self._quality_calculation_interval:
            return self.lidar_quality_score
        
        self._last_quality_calculation = current_time
        
        # Start timing if profiling is enabled
        start_time = time.time() if self.enable_profiling else 0
            
        # Calibrate if needed
        if not self.lidar_calibrated:
            if not self.calibrate_lidar(lidar_data):
                if self.lidar_calibration_attempts % 20 == 0:
                    logger.warning("Unable to calibrate LiDAR, using default quality score")
                return self.lidar_quality_score
                
        # Extract valid points for analysis
        # Optimize: Pre-allocate arrays and use vectorized operations where possible
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
            
        # Optimize: Convert directly to numpy arrays instead of extracting later
        angles_deg = np.array(angles_deg)
        distances = np.array(distances)
        
        # Convert angles to radians - do once for all calculations
        angles_rad = np.radians(angles_deg)
        
        # Optimize: Only log at debug level and only if enabled
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Analyzing road quality with {len(valid_points)} LiDAR points")
        
        # Step 1: Estimate d₀ (LiDAR height from ground) more robustly
        # Optimize: Use numpy's built-in comparison and avoid loops
        center_mask = np.abs(angles_deg) < 5
        if np.any(center_mask):
            estimated_height = np.median(distances[center_mask])
        else:
            # If no center points available, estimate height using min
            estimated_height = np.min(distances) * 1.05  # Add 5% margin
        
        # Step 2: Calculate expected distances for a flat road using cosine model
        # Optimize: Vectorized calculation with appropriate guards
        cos_values = np.cos(angles_rad)
        # Use vectorized maximum to avoid loops
        cos_values = np.maximum(cos_values, 0.1)  # Prevent values too close to zero
        expected_distances = estimated_height / cos_values
        
        # Step 3: Calculate deviations from the expected distances (residuals)
        residuals = distances - expected_distances
        
        # Step 4: Determine if the surface is convex or concave (road crown or dip)
        # Optimize: Only perform quadratic fit if we have enough points
        if len(angles_deg) >= 5:  # Need at least 5 points for a meaningful fit
            try:
                # Try quadratic fit to handle road crown/camber
                # Optimize: Use lower-degree polynomial if fewer points
                quad_coeffs = np.polyfit(angles_deg, residuals, min(2, len(angles_deg) - 1))
                quad_fit = np.polyval(quad_coeffs, angles_deg)
                # Remove the quadratic component from residuals
                adjusted_residuals = residuals - quad_fit
            except:
                adjusted_residuals = residuals
        else:
            adjusted_residuals = residuals
        
        # Calculate quality metrics on adjusted residuals - all vectorized operations
        mean_abs_deviation = np.mean(np.abs(adjusted_residuals))
        max_deviation = np.max(np.abs(adjusted_residuals))
        residual_std = np.std(adjusted_residuals)
        
        # Calculate R² equivalent with adjusted model
        # Optimize: Only compute if needed for score calculation
        ss_res = np.sum(adjusted_residuals**2)
        mean_distance = np.mean(distances)
        ss_tot = np.sum((distances - mean_distance)**2)
        r_squared = 1 - (ss_res / ss_tot if ss_tot > 0 else 0)
        
        # Adaptive scaling: determine reasonable thresholds based on the data
        # Optimize: Simplify calculations
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
        
        # Only detect events for significant quality drops to save processing
        if quality_score < 75 or self.lidar_quality_score - quality_score > 10:
            self._detect_lidar_events(adjusted_residuals, angles_deg, distances, quality_score)
        
        # Smooth the score with previous readings, using weighted average
        self.lidar_segment_scores.append(quality_score)
        
        # Optimize: Use numpy's array operations for weighted average
        if len(self.lidar_segment_scores) > 0:
            weights = np.linspace(0.5, 1.0, len(self.lidar_segment_scores))
            weighted_scores = np.array(self.lidar_segment_scores) * weights
            self.lidar_quality_score = min(100, np.sum(weighted_scores) / np.sum(weights))
        
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
            logger.debug(f"Quality score: {quality_score:.1f} → smoothed: {self.lidar_quality_score:.1f}")
        
        # Log significant changes in road quality
        road_class = self.get_road_classification_from_score(self.lidar_quality_score)
        if not hasattr(self, '_last_reported_quality') or \
           abs(self._last_reported_quality - self.lidar_quality_score) > 5:
            logger.info(f"LiDAR road quality: {self.lidar_quality_score:.1f}/100 ({road_class})")
            self._last_reported_quality = self.lidar_quality_score
        
        return self.lidar_quality_score
    
    def _detect_lidar_events(self, residuals, angles, distances, quality_score):
        """Detect road events from LiDAR data"""
        # Calculate a dynamic threshold based on the data
        if not hasattr(self, 'lidar_event_threshold'):
            median_abs_deviation = np.median(np.abs(residuals - np.median(residuals)))
            # Use MAD as a robust measure of variation (less sensitive to outliers than std)
            self.lidar_event_threshold = 3 * median_abs_deviation
            # Ensure minimum threshold to avoid detecting noise
            self.lidar_event_threshold = max(5.0, self.lidar_event_threshold)
        
        # Find indices where residuals exceed threshold (potential potholes/bumps)
        event_indices = np.where(np.abs(residuals) > self.lidar_event_threshold)[0]
        
        # Group adjacent indices into single events
        events = []
        if len(event_indices) > 0:
            event_start = event_indices[0]
            current_event = [event_start]
            
            for i in range(1, len(event_indices)):
                if event_indices[i] == event_indices[i-1] + 1:
                    # Adjacent point, add to current event
                    current_event.append(event_indices[i])
                else:
                    # Non-adjacent point, finish current event and start new one
                    events.append(current_event)
                    current_event = [event_indices[i]]
            
            # Add the last event
            if current_event:
                events.append(current_event)
        
        # Process each detected event
        new_events = []
        for event_indices in events:
            # Calculate event properties
            event_residuals = residuals[event_indices]
            max_idx = event_indices[np.argmax(np.abs(event_residuals))]
            max_residual = residuals[max_idx]
            event_angle = angles[max_idx]
            event_distance = distances[max_idx]
            
            # Classify event type and severity
            event_type = "Pothole" if max_residual > 0 else "Bump"
            severity = min(100, int(abs(max_residual) / self.lidar_event_threshold * 50))
            
            # Only log significant events
            if severity > 40 and quality_score < 70:
                logger.info(f"LiDAR detected {event_type}: severity={severity}, " +
                           f"deviation={max_residual:.2f}mm at angle={event_angle:.1f}°")
    
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
    
    def get_recent_events(self, count=5):
        """Get the most recent road events"""
        return self.events[-count:] if self.events else []