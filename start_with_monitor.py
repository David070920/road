#!/usr/bin/env python3
"""
Monitoring wrapper script for the Road Quality Measurement System
This script starts the main program and restarts it if it gets stuck
"""
import os
import sys
import time
import subprocess
import signal
import logging
import select
import fcntl

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MonitorScript")

# Path to the main program
MAIN_PROGRAM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.py")
# Marker text that signals potential hanging
MARKER_TEXT = "GPS map generation is disabled"
# Text that indicates the web server is successfully running
WEB_SERVER_RUNNING_TEXT = "Starting web server on http://"
# Time to wait after marker text before assuming it's stuck (seconds)
TIMEOUT_SECONDS = 15
# How often to check for timeouts (seconds)
CHECK_INTERVAL = 1.0

def start_process():
    """Start the main program as a subprocess and return the process object"""
    logger.info(f"Starting the Road Quality System: {MAIN_PROGRAM}")
    
    # Start the process and capture its output
    process = subprocess.Popen(
        [sys.executable, MAIN_PROGRAM],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,  # Use binary mode for better control
        bufsize=0    # Unbuffered
    )
    
    # Set stdout pipe to non-blocking mode
    fd = process.stdout.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    
    return process

def monitor_and_restart():
    """Monitor the program output and restart if needed"""
    while True:
        process = start_process()
        found_marker = False
        web_server_started = False
        last_output_time = time.time()
        buffer = b""
        
        try:
            # Monitor loop
            while process.poll() is None:  # While process is still running
                # Use select to wait for output with timeout
                ready_to_read, _, _ = select.select([process.stdout], [], [], CHECK_INTERVAL)
                
                if process.stdout in ready_to_read:
                    # Read available output (non-blocking)
                    chunk = process.stdout.read()
                    if chunk:
                        buffer += chunk
                        
                        # Process complete lines
                        while b'\n' in buffer:
                            idx = buffer.find(b'\n')
                            line = buffer[:idx+1].decode('utf-8', errors='replace')
                            buffer = buffer[idx+1:]
                            
                            # Print the line to console
                            print(line, end='')
                            
                            # Check if web server has started successfully
                            if WEB_SERVER_RUNNING_TEXT in line:
                                logger.info("Web server started successfully, monitoring disabled")
                                web_server_started = True
                                found_marker = False  # Reset to prevent timeout checks
                            
                            # Check for marker text (only if web server hasn't started yet)
                            if not web_server_started and MARKER_TEXT in line:
                                logger.info("Detected initialization marker, monitoring for potential hang...")
                                found_marker = True
                                last_output_time = time.time()
                            elif found_marker and not web_server_started:
                                # If we get any output after the marker but before web server starts, update the time
                                last_output_time = time.time()
                
                # Check for timeout only if we're in the critical period 
                # (after marker found but before web server starts)
                current_time = time.time()
                if found_marker and not web_server_started and (current_time - last_output_time) > TIMEOUT_SECONDS:
                    logger.warning(f"No output for {TIMEOUT_SECONDS} seconds after initialization marker!")
                    logger.warning("Program appears to be stuck, restarting...")
                    break
            
            # Print any remaining buffer
            if buffer:
                print(buffer.decode('utf-8', errors='replace'), end='')
                
            # If we get here, the process ended on its own or we broke out of the loop
            if process.poll() is None:
                # Process is still running but stuck, terminate it
                logger.info("Terminating stuck process...")
                process.terminate()
                try:
                    process.wait(timeout=5)  # Wait up to 5 seconds for graceful termination
                except subprocess.TimeoutExpired:
                    logger.warning("Process didn't terminate, sending SIGKILL...")
                    process.kill()  # Force kill if it doesn't respond
            
            exit_code = process.poll()
            if exit_code is not None and exit_code != 0:
                logger.warning(f"Process exited with code {exit_code}")
            
            logger.info("Waiting 2 seconds before restart...")
            time.sleep(2)  # Brief pause before restart
            
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            if process.poll() is None:
                logger.info("Terminating process due to keyboard interrupt...")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            logger.info("Exiting monitor script")
            break
        except Exception as e:
            logger.error(f"Error in monitor script: {e}")
            if process.poll() is None:
                process.terminate()
            time.sleep(2)  # Wait before retry

if __name__ == "__main__":
    logger.info("Starting Road Quality System with auto-restart monitor")
    monitor_and_restart()
