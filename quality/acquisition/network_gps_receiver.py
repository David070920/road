import logging
import threading
from flask import Flask, request, jsonify

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Global variable to store the latest GPS data
# This can be a simple dictionary or a more complex thread-safe structure if needed.
# For now, a simple dictionary is used as per the preference for consistency with existing gps_data.
network_gps_data = {
    "latitude": None,
    "longitude": None,
    "altitude": None,
    "satellites": None,
    "timestamp": None,
    "error": None
}

app = Flask(__name__)

@app.route('/gps_data', methods=['POST'])
def receive_gps_data():
    """
    Receives GPS data via POST request and updates the global network_gps_data.
    Expected JSON payload:
    {
        "latitude": float,
        "longitude": float,
        "altitude": float (optional),
        "satellites": int (optional),
        "timestamp": str (optional, ISO 8601 format e.g., "2025-05-22T10:30:00Z")
    }
    """
    global network_gps_data
    try:
        data = request.get_json()
        if not data:
            logger.error("Received empty or non-JSON data.")
            return jsonify({"status": "error", "message": "Invalid or empty JSON payload"}), 400

        required_fields = ["latitude", "longitude"]
        for field in required_fields:
            if field not in data:
                logger.error(f"Missing required field: {field} in received data: {data}")
                return jsonify({"status": "error", "message": f"Missing required field: {field}"}), 400
            if not isinstance(data[field], (int, float)):
                 logger.error(f"Invalid data type for field: {field}. Expected float or int.")
                 return jsonify({"status": "error", "message": f"Invalid data type for field: {field}. Expected float or int."}), 400


        # Update network_gps_data, ensuring thread-safety if this were a more complex app
        # For this simple case, direct assignment is okay for demonstration.
        # A lock could be used: `with data_lock:`
        network_gps_data["latitude"] = data.get("latitude")
        network_gps_data["longitude"] = data.get("longitude")
        network_gps_data["altitude"] = data.get("altitude")
        network_gps_data["satellites"] = data.get("satellites")
        network_gps_data["timestamp"] = data.get("timestamp")
        network_gps_data["error"] = None # Clear any previous error

        logger.info(f"Received GPS data: {network_gps_data}")
        return jsonify({"status": "success", "message": "GPS data received"}), 200

    except Exception as e:
        logger.exception(f"Error processing GPS data: {e}")
        network_gps_data["error"] = str(e)
        return jsonify({"status": "error", "message": str(e)}), 500

def start_network_gps_server(host='0.0.0.0', port=5001):
    """
    Starts the Flask HTTP server in a separate thread.
    """
    logger.info(f"Starting network GPS receiver server on {host}:{port}")
    # Using 'werkzeug' reloader=False and debug=False is important for threaded mode
    # or when running in production environments.
    # For development, Flask's built-in server is fine, but for production,
    # a more robust WSGI server like Gunicorn or uWSGI should be used.
    thread = threading.Thread(target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False))
    thread.daemon = True  # Daemonize thread to allow main program to exit
    thread.start()
    logger.info("Network GPS receiver server thread started.")
    return thread

if __name__ == '__main__':
    # Example of how to run the server directly for testing
    server_thread = start_network_gps_server()
    logger.info("Network GPS Receiver server is running. Press Ctrl+C to stop.")
    try:
        # Keep the main thread alive to allow the daemonized server thread to run
        while True:
            pass
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        # Note: Flask's dev server might not shut down cleanly on KeyboardInterrupt
        # when run this way in a daemon thread. For production, use a proper WSGI server.