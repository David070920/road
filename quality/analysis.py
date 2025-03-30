import numpy as np
import logging
from scipy.signal import find_peaks
from scipy import stats
from collections import deque
from datetime import datetime

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
        """Analyze the frequency spectrum of vibrations to classify road texture"""
        if len(accel_data) < 10:
            return self.road_texture_score
        
        # Add new accelerometer data to FFT window
        self.fft_window.extend(list(accel_data)[-10:])
        
        if len(self.fft_window) < 64:  # Need sufficient data for FFT
            return self.road_texture_score
        
        # Perform FFT on the window
        signal = np.array(self.fft_window) - np.mean(self.fft_window)  # Remove DC component
        fft_result = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
        
        # Get frequency bins
        freq_bins = np.fft.rfftfreq(len(signal), d=0.1)  # Assuming 10Hz sampling
        
        # Find dominant frequencies (excluding DC)
        peak_indices, _ = find_peaks(fft_result[1:])
        peak_indices = peak_indices + 1  # Adjust for the DC offset
        
        if len(peak_indices) > 0:
            # Sort by amplitude
            sorted_peaks = sorted([(i, fft_result[i]) for i in peak_indices], 
                                  key=lambda x: x[1], reverse=True)
            
            # Take the top peak
            if sorted_peaks:
                dominant_idx = sorted_peaks[0][0]
                dominant_freq = freq_bins[dominant_idx]
                self.dominant_frequencies.append(dominant_freq)
                
                # Classify road texture based on dominant frequency
                # Low frequencies (1-3 Hz): large undulations
                # Mid frequencies (4-15 Hz): general roughness
                # High frequencies (>15 Hz): fine texture/grain
                
                if dominant_freq < 3:
                    texture = "Undulating"
                    self.road_texture_score = max(40, self.road_texture_score - 5)
                elif dominant_freq < 15:
                    texture = "Rough"
                    self.road_texture_score = max(20, min(80, self.road_texture_score))
                else:
                    texture = "Fine-grained"
                    self.road_texture_score = min(60, self.road_texture_score + 5)
                
                logger.debug(f"Road texture: {texture} (dominant freq: {dominant_freq:.1f}Hz)")
        
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
        """Calculate road quality score based on LiDAR data"""
        if not lidar_data:
            logger.debug("No LiDAR data available for road quality calculation")
            return self.lidar_quality_score
            
        # Calibrate if needed
        if not self.lidar_calibrated:
            if not self.calibrate_lidar(lidar_data):
                if self.lidar_calibration_attempts % 20 == 0:
                    logger.warning("Unable to calibrate LiDAR, using default quality score")
                return self.lidar_quality_score
                
        # Extract valid points for analysis
        points = []
        for point in lidar_data:
            angle_deg = point[0]
            distance = point[1]
            
            # Convert 315-360 degrees to -45-0 degrees
            if angle_deg >= 315 and angle_deg <= 360:
                angle_deg = angle_deg - 360
                
            # Use a wider angle range for road profile analysis (-35 to 35 degrees)
            if -35 <= angle_deg <= 35:
                points.append((angle_deg, distance))
        
        if len(points) < 8:
            logger.debug(f"Not enough valid LiDAR points for analysis: {len(points)} (need 8+)")
            return self.lidar_quality_score
            
        # Sort by angle
        points.sort(key=lambda p: p[0])
        
        # Extract angles and distances as arrays
        angles_deg = np.array([p[0] for p in points])
        distances = np.array([p[1] for p in points])
        
        # Convert angles to radians for math operations
        angles_rad = np.radians(angles_deg)
        
        logger.debug(f"Analyzing road quality with {len(points)} LiDAR points")
        
        # For a perfectly flat road, the expected distance follows d = d₀/cos(θ)
        # where d₀ is the height of the LiDAR from the ground (distance at 0°)
        
        # Step 1: Estimate d₀ (LiDAR height from ground) more robustly
        center_indices = np.where(np.abs(angles_deg) < 5)[0]
        if len(center_indices) > 0:
            estimated_height = np.median(distances[center_indices])
        else:
            # If no center points available, estimate height using local fitting
            # to prevent underestimation
            estimated_height = np.min(distances) * 1.05  # Add 5% margin
        
        # Step 2: Calculate expected distances for a flat road using cosine model
        # Add a small epsilon to prevent division by zero at extreme angles
        cos_values = np.cos(angles_rad)
        cos_values = np.maximum(cos_values, 0.1)  # Prevent values too close to zero
        expected_distances = estimated_height / cos_values
        
        # Step 3: Calculate deviations from the expected distances (residuals)
        residuals = distances - expected_distances
        
        # Step 4: Determine if the surface is convex or concave (road crown or dip)
        # Fit a quadratic function to account for road camber/crown
        try:
            # Try quadratic fit to handle road crown/camber
            quad_coeffs = np.polyfit(angles_deg, residuals, 2)
            quad_fit = np.polyval(quad_coeffs, angles_deg)
            # Remove the quadratic component from residuals
            adjusted_residuals = residuals - quad_fit
        except:
            adjusted_residuals = residuals
        
        # Calculate quality metrics on adjusted residuals
        mean_abs_deviation = np.mean(np.abs(adjusted_residuals))
        max_deviation = np.max(np.abs(adjusted_residuals))
        residual_std = np.std(adjusted_residuals)
        
        # Calculate R² equivalent with adjusted model
        ss_res = np.sum(adjusted_residuals**2)
        ss_tot = np.sum((distances - np.mean(distances))**2)
        r_squared = 1 - (ss_res / ss_tot if ss_tot > 0 else 0)
        
        # Adaptive scaling: determine reasonable thresholds based on the data
        # This handles different scales of LiDAR measurements (mm vs cm vs m)
        measurement_scale = np.median(distances) * 0.001  # 0.1% of median distance
        # Ensure minimum scale is at least 5mm
        measurement_scale = max(5.0, measurement_scale)
        
        # Calculate quality score (0-100 scale)
        base_score = 98  # Start from 98 instead of 95 to allow close to perfect scores
        
        # Scale penalties based on reasonable expectations for road surfaces
        # For linearity - roads are rarely perfect but good roads are close
        linearity_penalty = (1 - r_squared) * 20  # Reduced from 30 to 20
        
        # For standard deviation - scale by the measurement_scale
        # Good roads typically have under 10mm standard deviation
        std_scale = max(10.0, measurement_scale * 1.5)
        std_penalty = min(25, (residual_std / std_scale) * 25)  # Reduced max impact
        
        # Maximum deviation - scale for common road features
        # Good roads might have 20-30mm max deviation
        max_dev_scale = max(30.0, measurement_scale * 3)
        max_penalty = min(30, (max_deviation / max_dev_scale) * 30)
        
        # Calculate final score with adjusted penalties
        quality_score = max(0, base_score - linearity_penalty - std_penalty - max_penalty)
        
        # Boost scores for very good roads
        if quality_score > 90:
            # If it's already above 90, reduce the gap to 100, but cap at 100
            quality_score = min(100, 90 + (quality_score - 90) * 2)
        
        # Detect events for significant deviations
        self._detect_lidar_events(adjusted_residuals, angles_deg, distances, quality_score)
        
        # Smooth the score with previous readings, using weighted average
        self.lidar_segment_scores.append(quality_score)
        weights = np.linspace(0.5, 1.0, len(self.lidar_segment_scores))
        weighted_scores = np.array(self.lidar_segment_scores) * weights
        self.lidar_quality_score = min(100, np.sum(weighted_scores) / np.sum(weights))
        
        # Log detailed quality metrics for debugging
        logger.debug(f"Road quality: r²={r_squared:.3f}, std={residual_std:.2f}mm, max_dev={max_deviation:.2f}mm")
        logger.debug(f"Measurement scale: {measurement_scale:.2f}, std_scale: {std_scale:.2f}, max_dev_scale: {max_dev_scale:.2f}")
        logger.debug(f"Penalties: linearity={linearity_penalty:.1f}, std={std_penalty:.1f}, max={max_penalty:.1f}")
        logger.debug(f"Quality score: {quality_score:.1f} → smoothed: {self.lidar_quality_score:.1f}")
        
        # Log significant changes in road quality
        road_class = self.get_road_classification_from_score(self.lidar_quality_score)
        logger.info(f"LiDAR road quality: {self.lidar_quality_score:.1f}/100 ({road_class})")
        
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
