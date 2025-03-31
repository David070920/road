import logging

def configure_logging():
    """Configure logging for the entire application"""
    # Set werkzeug log level to ERROR to prevent request logs
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    # Set a high log level for other potentially noisy libraries 
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    # Silence pyngrok logs
    logging.getLogger('pyngrok').setLevel(logging.ERROR)
    logging.getLogger('pyngrok.process').setLevel(logging.ERROR)
    logging.getLogger('pyngrok.process.ngrok').setLevel(logging.ERROR)
    
    # Configure the main application logger
    logger = logging.getLogger("SensorFusion")
    logger.setLevel(logging.INFO)
    
    # Add any other custom logging configuration here
