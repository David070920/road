import flask
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading
import time
import logging
import json
import os

logger = logging.getLogger("WebServer")

class RoadQualityWebServer:
    def __init__(self, sensor_fusion, config, host='0.0.0.0', port=8080):
        """Initialize the web server with access to sensor data"""
        self.app = Flask(__name__, 
                         static_folder='static',
                         template_folder='templates')
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        self.sensor_fusion = sensor_fusion
        self.config = config
        self.host = host
        self.port = port
        self.running = False
        self.thread = None
        self.connected_clients = 0
        
        # Register routes
        self.register_routes()
        # Register socket events
        self.register_socket_events()
        
        logger.info(f"Web server initialized on http://{host}:{port}/")
    
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
                    }
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
        
        # Start web server
        logger.info(f"Starting web server on http://{self.host}:{self.port}/")
        try:
            self.socketio.run(self.app, host=self.host, port=self.port, 
                              debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
        except Exception as e:
            logger.error(f"Error starting web server: {e}")
            self.running = False
    
    def stop(self):
        """Stop the web server"""
        logger.info("Stopping web server")
        self.running = False
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
