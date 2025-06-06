import flask
import time
import os
from quality.data_storage import DataStorage
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading
import time
import logging
logging.getLogger().setLevel(logging.DEBUG)
import json
import os
import socket
from datetime import datetime

logger = logging.getLogger("WebServer")
logger.setLevel(logging.DEBUG)

# Import ngrok helper
try:
    from .ngrok_helper import NgrokTunnel, check_ngrok_installed, get_ngrok_version
    NGROK_AVAILABLE = True
except ImportError:
    logger.warning("Ngrok helper module not found. Remote access will not be available.")
    NGROK_AVAILABLE = False

# Import the system monitor
from .system_monitor import get_system_status

class RoadQualityWebServer:
    def __init__(self, sensor_fusion, config, host='0.0.0.0', port=8080):
        """Initialize the web server with access to sensor data"""
        self.app = Flask(__name__, 
                         static_folder='static',
                         template_folder='templates')
        
        # Enhanced socketio configuration with more robust error handling
        self.socketio = SocketIO(
            self.app, 
            cors_allowed_origins="*", 
            async_mode='threading',
            logger=False,  # Disable socketio logger
            engineio_logger=False,  # Disable engineio logger 
            ping_timeout=20,
            ping_interval=25
        )
        
        self.sensor_fusion = sensor_fusion
        self.config = config
        self.host = host
        self.port = self._find_available_port(port)  # Find an available port if default is taken
        self.running = False
        self.thread = None
        self.connected_clients = 0
        self.latest_gps_data = {'lat': 0, 'lon': 0, 'altitude': None, 'satellites': None}
        
        # Add these lines to disable werkzeug request logs
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)  # Only show errors, not INFO messages
        
        # Disable Flask's default logging of requests
        self.app.logger.disabled = True
        logging.getLogger('werkzeug').disabled = True
        
        # Disable ngrok logs as well
        logging.getLogger('pyngrok').setLevel(logging.ERROR)
        logging.getLogger('pyngrok.process').setLevel(logging.ERROR)
        
        # Ngrok tunnel
        self.ngrok_tunnel = None
        
        # Register routes
        self.register_routes()
        # Register socket events
        self.register_socket_events()
        
        logger.info(f"Web server initialized on http://{host}:{self.port}/")
        
        # Initialize ngrok if enabled
        if getattr(self.config, 'ENABLE_NGROK', False) and NGROK_AVAILABLE:
            self.setup_ngrok()
    
    def _find_available_port(self, preferred_port):
        """Find an available port, starting with the preferred one"""
        port = preferred_port
        max_attempts = 10
        
        for attempt in range(max_attempts):
            try:
                # Try to create a socket on the port
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                test_socket.bind((self.host, port))
                test_socket.close()
                logger.info(f"Port {port} is available")
                return port
            except socket.error:
                logger.warning(f"Port {port} is in use, trying port {port+1}")
                port += 1
        
        # If we get here, just return the last port we tried
        logger.warning(f"Could not find available port after {max_attempts} attempts. Using port {port}")
        return port

    def setup_ngrok(self):
        """Set up ngrok tunnel for remote access"""
        try:
            # Check if pyngrok is installed
            import importlib
            spec = importlib.util.find_spec('pyngrok')
            if spec is None:
                logger.error("pyngrok module not installed. Run: pip install pyngrok")
                print("\n" + "=" * 80)
                print("⚠️  REMOTE ACCESS ERROR: pyngrok module not installed")
                print("   To enable remote access, install pyngrok:")
                print("   pip install pyngrok")
                print("=" * 80 + "\n")
                return
                
            if not check_ngrok_installed():
                logger.error("ngrok executable not found. Install it using pyngrok")
                print("\n" + "=" * 80)
                print("⚠️  REMOTE ACCESS ERROR: ngrok executable not found")
                print("   Try installing it with:")
                print("   python -c 'from pyngrok import ngrok; ngrok.install_ngrok()'")
                print("=" * 80 + "\n")
                return
                
            logger.info(f"Setting up ngrok tunnel (version: {get_ngrok_version()})...")
            
            # Create tunnel with the correct port
            self.ngrok_tunnel = NgrokTunnel(
                port=self.port,  # Use the actual port we're running on
                auth_token=getattr(self.config, 'NGROK_AUTH_TOKEN', None),
                region=getattr(self.config, 'NGROK_REGION', 'us')
            )
            
            logger.info("Ngrok tunnel setup complete and ready to start")
            
        except Exception as e:
            logger.error(f"Error setting up ngrok: {e}")
            print("\n" + "=" * 80)
            print(f"⚠️  REMOTE ACCESS ERROR: {e}")
            print("=" * 80 + "\n")
    
    def register_routes(self):
        """Register HTTP routes"""
        @self.app.route('/')
        def index():
            return render_template('index.html', 
                                  user_info=self.config.USER_LOGIN,
                                  session_time=self.config.SYSTEM_START_TIME)
        
        @self.app.route('/status')
        def status():
            """Simple endpoint to check if the server is running"""
            return flask.jsonify({'status': 'ok', 'timestamp': time.time()})
 
        @self.app.route('/gps_data', methods=['POST'])
        def receive_gps_data():
            """Receive raw GPS payloads from Tasker app and log for debug"""
            try:
                tstamp = time.strftime('%Y-%m-%d %H:%M:%S')
                raw_body = flask.request.get_data(as_text=True)
                logger.debug(f"[{tstamp}] /gps_data raw body: {raw_body}")
                logger.debug(f"[{tstamp}] /gps_data headers: {dict(flask.request.headers)}")
                logger.debug(f"[{tstamp}] /gps_data is_json: {flask.request.is_json}")
                payload = flask.request.get_json(force=True)
                # Update latest GPS data for real-time dashboard
                self.latest_gps_data = {
                    'lat': payload.get('latitude', payload.get('lat', 0)),
                    'lon': payload.get('longitude', payload.get('lon', 0)),
                    'altitude': payload.get('altitude'),
                    'satellites': payload.get('satellites', payload.get('sats', None))
                }
                
                # Update the SensorFusion/SensorDataReader GPS data to ensure data is synchronized
                # Handle both SensorFusion and SensorDataReader classes
                if self.sensor_fusion:
                    # Check if we're using SensorFusion or SensorDataReader
                    if hasattr(self.sensor_fusion, 'gps_data_lock'):
                        # SensorFusion case
                        try:
                            with self.sensor_fusion.gps_data_lock:
                                self.sensor_fusion.gps_data['lat'] = self.latest_gps_data['lat']
                                self.sensor_fusion.gps_data['lon'] = self.latest_gps_data['lon']
                                self.sensor_fusion.gps_data['alt'] = self.latest_gps_data.get('altitude')
                                self.sensor_fusion.gps_data['sats'] = self.latest_gps_data.get('satellites')
                                self.sensor_fusion.gps_data['timestamp'] = time.time()
                        except Exception as sync_error:
                            logger.error(f"Error updating SensorFusion GPS data: {sync_error}")
                    else:
                        # SensorDataReader case
                        try:
                            with self.sensor_fusion.snapshot_lock:
                                if hasattr(self.sensor_fusion, '_cached_snapshot') and isinstance(self.sensor_fusion._cached_snapshot, dict):
                                    self.sensor_fusion._cached_snapshot['gps_data'] = {
                                        'lat': self.latest_gps_data['lat'],
                                        'lon': self.latest_gps_data['lon'],
                                        'alt': self.latest_gps_data.get('altitude'),
                                        'sats': self.latest_gps_data.get('satellites'),
                                        'timestamp': time.time()
                                    }
                        except Exception as sync_error:
                            logger.error(f"Error updating SensorDataReader GPS data: {sync_error}")
                
                # DIRECT LOG: Log GPS data directly to CSV file when we receive it from Tasker
                lat = self.latest_gps_data['lat']
                lon = self.latest_gps_data['lon']
                
                # Only log if we have valid coordinates
                if lat != 0 and lon != 0:
                    # Get the current quality score from the analyzer if available
                    quality_score = 80  # Default quality score
                    if hasattr(self.sensor_fusion, 'analyzer') and self.sensor_fusion.analyzer:
                        if hasattr(self.sensor_fusion.analyzer, 'lidar_quality_score'):
                            quality_score = self.sensor_fusion.analyzer.lidar_quality_score
                        elif hasattr(self.sensor_fusion.analyzer, 'combined_quality_score'):
                            quality_score = self.sensor_fusion.analyzer.combined_quality_score
                    
                    # Log the GPS data with the current quality score
                    self.log_gps_to_csv(lat, lon, quality_score)
                
                self.emit_data_update()
                logger.debug(f"[{tstamp}] /gps_data parsed object: {payload}")
                logger.debug(f"[{tstamp}] Raw GPS payload: {json.dumps(payload)}")
                return flask.jsonify({'status': 'received'}), 200
            except Exception as e:
                logger.error(f"Error in /gps_data handler: {e}")
                return flask.jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/data')
        def get_data():
            """API endpoint to get current data snapshot"""
            try:
                with self.sensor_fusion.snapshot_lock:
                    # Get quality metrics and classification
                    lidar_quality = 0
                    accel_quality = 0
                    classification = "Unknown"
                    events = []
                    
                    if hasattr(self.sensor_fusion, 'analyzer') and self.sensor_fusion.analyzer:
                        lidar_quality = getattr(self.sensor_fusion.analyzer, 'lidar_quality_score', 0)
                        accel_quality = getattr(self.sensor_fusion.analyzer, 'current_quality_score', 0)
                        
                        if hasattr(self.sensor_fusion.analyzer, 'get_road_classification'):
                            classification = self.sensor_fusion.analyzer.get_road_classification()
                        
                        if hasattr(self.sensor_fusion.analyzer, 'get_recent_events'):
                            events = self.sensor_fusion.analyzer.get_recent_events(count=10)
                        elif hasattr(self.sensor_fusion.analyzer, 'events'):
                            events = getattr(self.sensor_fusion.analyzer, 'events', [])[-10:]
                    
                    # Get GPS data (including altitude and satellites)
                    gps_data = {
                        'lat': self.latest_gps_data.get('lat', 0),
                        'lon': self.latest_gps_data.get('lon', 0),
                        'altitude': self.latest_gps_data.get('altitude'),
                        'satellites': self.latest_gps_data.get('satellites')
                    }
                    
                    data = {
                        'lidar_quality': lidar_quality,
                        'accel_quality': accel_quality,
                        'classification': classification,
                        'gps': gps_data,
                        'events': events
                    }
                
                return flask.jsonify(data)
            except Exception as e:
                logger.error(f"Error fetching API data: {e}")
                return flask.jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/system')
        def get_system_status_api():
            """API endpoint to get system status information"""
            try:
                status_data = get_system_status()
                
                # Add data points information safely
                status_data['data_points'] = {
                    'accel': 0,
                    'lidar': 0,
                    'gps': 0
                }
                
                # Get data point counts safely
                try:
                    if hasattr(self.sensor_fusion, 'accel_data'):
                        status_data['data_points']['accel'] = len(self.sensor_fusion.accel_data or [])
                    
                    if hasattr(self.sensor_fusion, 'lidar_data'):
                        status_data['data_points']['lidar'] = len(self.sensor_fusion.lidar_data or [])
                    
                    if (hasattr(self.sensor_fusion, 'analyzer') and 
                        self.sensor_fusion.analyzer and 
                        hasattr(self.sensor_fusion.analyzer, 'gps_quality_history')):
                        status_data['data_points']['gps'] = len(self.sensor_fusion.analyzer.gps_quality_history)
                except Exception as e:
                    logger.error(f"Error getting data point counts: {e}")
                
                return flask.jsonify(status_data)
            except Exception as e:
                logger.error(f"Error fetching system status: {e}")
                return flask.jsonify({'error': str(e)}), 500
        
        @self.app.route('/remote_access')
        def remote_access():
            """Display ngrok tunnel information"""
            if self.ngrok_tunnel and self.ngrok_tunnel.public_url:
                tunnel_url = self.ngrok_tunnel.public_url
                status = "active"
            else:
                tunnel_url = "Not available"
                status = "inactive"
                
            return flask.jsonify({
                'status': status,
                'tunnel_url': tunnel_url,
                'local_url': f"http://{self.host}:{self.port}/",
            })
        
        # Add a handler for the removed GPS map
        @self.app.route('/gps_position.html')
        def gps_position_redirect():
            """Redirect to home for removed GPS map file"""
            return flask.redirect('/')

        @self.app.route('/start_server', methods=['POST'])
        def start_server():
            """Start the data update loop with optimized settings for web visualization"""
            try:
                # Set web visualization as primary mode
                setattr(self.config, 'USE_WEB_VISUALIZATION', True)
                
                # Make sure the update loop is running
                if not self.thread or not self.thread.is_alive():
                    self.thread = threading.Thread(target=self.data_update_loop)
                    self.thread.daemon = True
                    self.thread.start()
                    logger.info("Started data update loop with web-optimized settings")
                else:
                    # Force optimization settings to update immediately
                    self._last_optimization_check = 0
                    logger.info("Data update loop already running, optimizing for web")
                
                return flask.jsonify({'status': 'ok', 'message': 'Web server optimized for web visualization'})
            except Exception as e:
                logger.error(f"Error starting server: {e}")
                return flask.jsonify({'status': 'error', 'message': str(e)}), 500
        
        @self.app.route('/stop_server', methods=['POST'])
        def stop_server():
            """Stop the data update loop to save resources when web is not primary"""
            try:
                # Set GUI as primary mode
                setattr(self.config, 'USE_WEB_VISUALIZATION', False)
                
                # Force update of optimization settings on next check
                self._last_optimization_check = 0
                logger.info("Web server optimized for GUI mode (reduced updates)")
                
                return flask.jsonify({'status': 'ok', 'message': 'Web server in background mode'})
            except Exception as e:
                logger.error(f"Error stopping server: {e}")
                return flask.jsonify({'status': 'error', 'message': str(e)}), 500
    
    def register_socket_events(self):
        """Register WebSocket event handlers"""
        @self.socketio.on('connect')
        def handle_connect():
            self.connected_clients += 1
            logger.info(f'Client connected to WebSocket. Total clients: {self.connected_clients}')
            # Send initial data
            self.emit_data_update()
            # Send a welcome message to confirm connection
            self.socketio.emit('connection_status', {'status': 'connected', 'msg': 'Connected to server'})
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            self.connected_clients = max(0, self.connected_clients - 1)
            logger.info(f'Client disconnected from WebSocket. Remaining clients: {self.connected_clients}')
        
        @self.socketio.on('ping')
        def handle_ping():
            # Client can ping server to check connection
            self.socketio.emit('pong', {'timestamp': time.time()})
    
    def emit_data_update(self):
        """Emit updated sensor data to connected clients"""
        try:
            with self.sensor_fusion.snapshot_lock:
                # Get quality metrics - handle both SensorFusion and SensorDataReader objects
                lidar_quality = 0
                accel_quality = 0
                combined_quality = 0
                classification = "Unknown"
                events = []
                
                if hasattr(self.sensor_fusion, 'analyzer') and self.sensor_fusion.analyzer:
                    lidar_quality = getattr(self.sensor_fusion.analyzer, 'lidar_quality_score', 0)
                    accel_quality = getattr(self.sensor_fusion.analyzer, 'current_quality_score', 0)
                    combined_quality = getattr(self.sensor_fusion.analyzer, 'combined_quality_score', 0)
                    
                    # Get road classification and events if available
                    if hasattr(self.sensor_fusion.analyzer, 'get_road_classification'):
                        classification = self.sensor_fusion.analyzer.get_road_classification()
                    
                    # Get events if available
                    if hasattr(self.sensor_fusion.analyzer, 'events'):
                        events = getattr(self.sensor_fusion.analyzer, 'events', [])[-20:]
                    elif hasattr(self.sensor_fusion.analyzer, 'get_recent_events'):
                        events = self.sensor_fusion.analyzer.get_recent_events(count=20)
                
                # Get GPS data (including altitude and satellites)
                gps_data = {
                    'lat': self.latest_gps_data.get('lat', 0),
                    'lon': self.latest_gps_data.get('lon', 0),
                    'altitude': self.latest_gps_data.get('altitude'),
                    'satellites': self.latest_gps_data.get('satellites')
                }
                
                # Get environmental data
                env_data = {
                    'temperature': None,
                    'humidity': None,
                    'pressure': None,
                    'altitude': None
                }
                if hasattr(self.sensor_fusion, 'env_data'):
                    env_data = {
                        'temperature': self.sensor_fusion.env_data.get('temperature'),
                        'humidity': self.sensor_fusion.env_data.get('humidity'),
                        'pressure': self.sensor_fusion.env_data.get('pressure'),
                        'altitude': self.sensor_fusion.env_data.get('altitude')
                    }
                
                # Get accelerometer data
                accel_data = []
                if hasattr(self.sensor_fusion, 'accel_data'):
                    accel_data = list(self.sensor_fusion.accel_data)[-50:] if self.sensor_fusion.accel_data else []
                
                # Build the data object
                data = {
                    'timestamp': time.time(),
                    'lidar_quality': lidar_quality,
                    'accel_quality': accel_quality,
                    'accel_data': accel_data,
                    'classification': classification,
                    'gps': gps_data,
                    'env': env_data,
                    'combined_quality_score': combined_quality,
                    'recent_events': events
                }
                
            # Only emit if there are connected clients to save resources
            if self.connected_clients > 0:
                self.socketio.emit('data_update', data)
                
                # Add a periodic debug log to verify data is being sent
                if hasattr(self, '_debug_counter'):
                    self._debug_counter += 1
                    if self._debug_counter % 20 == 0:  # Log every 20 updates
                        logger.debug(f"Emitted data update #{self._debug_counter} to {self.connected_clients} client(s)")
                else:
                    self._debug_counter = 1
                
        except Exception as e:
            logger.error(f"Error emitting data update: {e}")
            
        # Save data to database
        try:
            if hasattr(self, 'data_storage') and self.data_storage:
                ts = data.get('timestamp', time.time())
                lat = data.get('gps', {}).get('lat', 0) 
                lon = data.get('gps', {}).get('lon', 0)
                quality_score = data.get('combined_quality_score', None)
                classification = data.get('classification', '')

                # Insert road quality data
                self.data_storage.insert_quality_data(ts, lat, lon, quality_score, classification)

                # Insert recent events
                for event in data.get('recent_events', []):
                    event_lat = event.get('lat', 0)
                    event_lon = event.get('lon', 0)
                    severity = event.get('severity', 0)
                    source = event.get('source', '')
                    confidence = event.get('confidence', 0)
                    event_ts = event.get('timestamp', ts)
                    self.data_storage.insert_event(event_ts, event_lat, event_lon, severity, source, confidence)
        except Exception as e:
            logger.error(f"Error saving data to database: {e}")
    
    def data_update_loop(self):
        """Background thread that emits data updates periodically"""
        logger.info("Starting data update loop thread")
        self._debug_counter = 0
        self._last_optimization_check = time.time()
        
        while self.running:
            try:
                # Only emit data update if we have connected clients
                if self.connected_clients > 0:
                    self.emit_data_update()
                
                    # Add a periodic debug log to verify data is being sent
                    if hasattr(self, '_debug_counter'):
                        self._debug_counter += 1
                        if self._debug_counter % 20 == 0:  # Log every 20 updates
                            logger.debug(f"Emitted data update #{self._debug_counter} to {self.connected_clients} client(s)")
                    else:
                        self._debug_counter = 1
            except Exception as e:
                logger.error(f"Error in data update loop: {e}")
                
            # Use adaptive update interval based on visualization mode
            # Check the current mode - this is more efficient than checking on every iteration
            current_time = time.time()
            if current_time - self._last_optimization_check > 5.0:  # Check every 5 seconds
                self._last_optimization_check = current_time
                self._update_optimization_settings()
            
            # Use the current update interval
            time.sleep(self._get_current_update_interval())
    
    def _update_optimization_settings(self):
        """Update optimization settings based on current configuration"""
        try:
            # Track whether settings have changed
            settings_changed = False
            
            # Check if web visualization is active
            web_is_primary = getattr(self.config, 'USE_WEB_VISUALIZATION', False)
            
            # Store the setting so we don't have to access it repeatedly
            if not hasattr(self, '_web_is_primary') or self._web_is_primary != web_is_primary:
                self._web_is_primary = web_is_primary
                settings_changed = True
            
            # If settings changed, log it
            if settings_changed:
                if self._web_is_primary:
                    logger.info("Web is primary visualization - using faster update rate")
                else:
                    logger.info("GUI is primary visualization - using reduced web update rate")
        except Exception as e:
            logger.error(f"Error updating optimization settings: {e}")
            # Fallback to default settings
            self._web_is_primary = False
    
    def _get_current_update_interval(self):
        """Get the current update interval based on configuration"""
        # Default to legacy setting if none of our new configs exist
        default_interval = getattr(self.config, 'WEB_UPDATE_INTERVAL', 500) / 1000.0
        
        try:
            # Use optimized settings if available
            if hasattr(self, '_web_is_primary') and self._web_is_primary:
                # Web is primary visualization - use faster updates
                interval_ms = getattr(self.config, 'WEB_ACTIVE_UPDATE_INTERVAL', 200)
            else:
                # GUI is primary visualization - use slower updates for web
                interval_ms = getattr(self.config, 'WEB_BACKGROUND_UPDATE_INTERVAL', 1000)
            
            # Convert to seconds
            return interval_ms / 1000.0
        except Exception as e:
            logger.error(f"Error calculating update interval: {e}")
            return default_interval
    
    def start(self):
        """Start the web server"""
        if self.running:
            logger.warning("Web server is already running")
            return
            
        self.running = True
        # Start background thread for data updates
        self.thread = threading.Thread(target=self.data_update_loop)
        self.thread.daemon = True
        self.thread.start()
        
        # Start ngrok tunnel if available - Do this BEFORE starting the Flask server
        ngrok_started = False
        if self.ngrok_tunnel:
            # Try multiple times to establish the tunnel
            retry_count = getattr(self.config, 'NGROK_RETRY_COUNT', 3)
            retry_delay = getattr(self.config, 'NGROK_RETRY_DELAY', 2)
            
            for attempt in range(retry_count):
                logger.info(f"Starting ngrok tunnel (attempt {attempt+1}/{retry_count})...")
                try:
                    if self.ngrok_tunnel.start():
                        logger.info(f"✅ Remote access URL: {self.ngrok_tunnel.public_url}")
                        # Print QR code URL for easy mobile access
                        qr_url = f"https://chart.googleapis.com/chart?cht=qr&chs=300x300&chl={self.ngrok_tunnel.public_url}"
                        logger.info(f"📱 Scan QR code to access: {qr_url}")
                        
                        # Add this to make it very visible in the console
                        print("\n" + "=" * 80)
                        print(f"🌐 REMOTE ACCESS URL: {self.ngrok_tunnel.public_url}")
                        print(f"📱 SCAN QR CODE: {qr_url}")
                        print("=" * 80 + "\n")
                        
                        ngrok_started = True
                        break
                    else:
                        logger.warning(f"Failed to start ngrok tunnel on attempt {attempt+1}")
                except Exception as e:
                    logger.error(f"Error starting ngrok tunnel: {e}")
                
                time.sleep(retry_delay)  # Wait before retry
                
            if not ngrok_started:
                logger.error("Failed to start ngrok tunnel after multiple attempts")
                print("\n" + "=" * 80)
                print("⚠️  REMOTE ACCESS ERROR: Failed to start ngrok tunnel")
                print("   Check logs for more details")
                print("=" * 80 + "\n")
        
        # Start web server
        logger.info(f"Starting web server on http://{self.host}:{self.port}/")
        try:
            # Use try/except to catch socket errors
            self.socketio.run(
                self.app, 
                host=self.host, 
                port=self.port, 
                debug=False, 
                use_reloader=False, 
                log_output=False,  # Disable SocketIO logging
                allow_unsafe_werkzeug=True
            )
        except OSError as e:
            logger.error(f"Error starting web server: {e}")
            if "Address already in use" in str(e):
                logger.error(f"Port {self.port} is already in use. Try changing the port in config.")
            self.running = False
        except Exception as e:
            logger.error(f"Unexpected error starting web server: {e}")
            self.running = False
    
    def stop(self):
        """Stop the web server"""
        logger.info("Stopping web server")
        self.running = False
        
        # Stop ngrok tunnel
        if self.ngrok_tunnel:
            self.ngrok_tunnel.stop()
            
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        # Shutdown flask in a better way (depends on flask version)
        try:
            from flask import request
            func = request.environ.get('werkzeug.server.shutdown')
            if func is None:
                raise RuntimeError('Not running with the Werkzeug Server')
            func()
        except:
            logger.warning("Could not shut down Werkzeug server gracefully")

    def log_gps_to_csv(self, lat, lon, quality_score=80):
        """Log GPS data directly to CSV file in the logs directory."""
        try:
            # Set up the logs directory path
            logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                                  "logs")
            
            # Create logs directory if it doesn't exist
            if not os.path.exists(logs_dir):
                os.makedirs(logs_dir)
                logger.info(f"Created logs directory: {logs_dir}")
            
            # Set the output file path in the logs directory
            output_file = os.path.join(logs_dir, "data.csv")
            
            # Convert quality score to color (0-100 scale)
            color = "#00FF00"  # Default green
            if quality_score <= 50:
                # Red stays at FF, green increases from 00 to FF
                red = 255
                green = int((quality_score / 50) * 255)
                blue = 0
                color = f"#{red:02X}{green:02X}{blue:02X}"
            else:
                # Red decreases from FF to 00, green stays at FF
                red = int(((100 - quality_score) / 50) * 255)
                green = 255
                blue = 0
                color = f"#{red:02X}{green:02X}{blue:02X}"
            
            # Check if file exists to write header
            file_exists = os.path.isfile(output_file)
            
            # Write to CSV file
            with open(output_file, "a") as f:
                # Write header if file doesn't exist
                if not file_exists:
                    f.write("latitude,longitude,quality_score,color,timestamp\n")
                
                # Write data row
                timestamp = datetime.now().isoformat()
                f.write(f"{lat},{lon},{quality_score},{color},{timestamp}\n")
                
            logger.info(f"Directly logged GPS data to {output_file}: lat={lat}, lon={lon}, quality={quality_score}")
            return True
            
        except Exception as e:
            logger.error(f"Error logging GPS data to CSV: {e}")
            return False
