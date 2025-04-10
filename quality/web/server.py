import flask
import time
import os
from quality.data_storage import DataStorage
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading
import time
import logging
import json
import os
import socket

logger = logging.getLogger("WebServer")

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
        
        @self.app.route('/api/data')
        def get_data():
            """API endpoint to get current data snapshot"""
            with self.sensor_fusion.snapshot_lock:
                data = {
                    'lidar_quality': self.sensor_fusion.analyzer.lidar_quality_score,
                    'accel_quality': self.sensor_fusion.analyzer.current_quality_score,
                    'classification': self.sensor_fusion.analyzer.get_road_classification(),
                    'gps': {
                        'lat': self.sensor_fusion.gps_data['lat'],
                        'lon': self.sensor_fusion.gps_data['lon']
                    },
                    'events': self.sensor_fusion.analyzer.get_recent_events(count=10)
                }
            return flask.jsonify(data)
        
        @self.app.route('/api/system')
        def get_system_status_api():
            """API endpoint to get system status information"""
            status_data = get_system_status()
            
            # Add data points information
            status_data['data_points'] = {
                'accel': len(self.sensor_fusion.accel_data),
                'lidar': len(self.sensor_fusion.lidar_data),
                'gps': len(self.sensor_fusion.analyzer.gps_quality_history) if hasattr(self.sensor_fusion.analyzer, 'gps_quality_history') else 0
            }
            
            return flask.jsonify(status_data)
        
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
                data = {
                    'timestamp': time.time(),
                    'lidar_quality': self.sensor_fusion.analyzer.lidar_quality_score,
                    'accel_data': list(self.sensor_fusion.accel_data)[-50:] if self.sensor_fusion.accel_data else [],
                    'classification': self.sensor_fusion.analyzer.get_road_classification(),
                    'gps': {
                        'lat': self.sensor_fusion.gps_data['lat'],
                        'lon': self.sensor_fusion.gps_data['lon']
                    },
                    # Add environmental data
                    'env': {
                        'temperature': self.sensor_fusion.env_data['temperature'],
                        'humidity': self.sensor_fusion.env_data['humidity'],
                        'pressure': self.sensor_fusion.env_data['pressure'],
                        'altitude': self.sensor_fusion.env_data['altitude']
                    },
                    # Add combined road quality score
                    'combined_quality_score': getattr(self.sensor_fusion.analyzer, 'combined_quality_score', None),
                    # Add recent detected events
                    'recent_events': getattr(self.sensor_fusion.analyzer, 'events', [])[-20:]
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
        
        while self.running:
            try:
                self.emit_data_update()
            except Exception as e:
                logger.error(f"Error in data update loop: {e}")
                
            # Use config for update interval if available, otherwise default to 200ms
            update_interval = getattr(self.config, 'WEB_UPDATE_INTERVAL', 500) / 1000.0
            time.sleep(update_interval)
    
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
