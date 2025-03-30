#!/usr/bin/env python3
"""
Quick utility to check if ngrok tunnel is running and show its public URL.
"""

import os
import sys
import logging
import time
import webbrowser
import qrcode
from io import StringIO

# Set up logging with a simpler format for this tool
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("NgrokStatus")

def display_qr_code_terminal(url):
    """Generate and display a QR code in the terminal"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)

        # Create a StringIO to capture the output
        f = StringIO()
        qr.print_ascii(out=f)
        f.seek(0)
        
        # Print the QR code
        print(f.read())
    except ImportError:
        print("QR code cannot be displayed (qrcode package not installed)")
        print("Install with: pip install qrcode")
    except Exception as e:
        print(f"Error generating QR code: {e}")

def check_ngrok_status():
    """Check if ngrok is running and show active tunnels"""
    try:
        from pyngrok import ngrok
        
        # Check for active tunnels
        tunnels = ngrok.get_tunnels()
        
        if not tunnels:
            print("🔴 No active ngrok tunnels found.")
            return False
        
        print(f"🟢 Found {len(tunnels)} active ngrok {'tunnel' if len(tunnels) == 1 else 'tunnels'}:")
        
        for i, tunnel in enumerate(tunnels, 1):
            print(f"\n{i}. {tunnel.public_url} → {tunnel.config['addr']}")
            print(f"   Protocol: {tunnel.proto}, Name: {tunnel.name}")
            
            # Generate QR code for this URL
            print("\nScan QR code to access:")
            display_qr_code_terminal(tunnel.public_url)
            
            # Also provide the Google Charts QR code URL
            qr_url = f"https://chart.googleapis.com/chart?cht=qr&chs=300x300&chl={tunnel.public_url}"
            print(f"\nOr use this QR code link: {qr_url}")
            
            # Ask to open in browser
            answer = input("\nOpen this URL in browser? (y/n): ").strip().lower()
            if answer == 'y':
                webbrowser.open(tunnel.public_url)
        
        return True
            
    except ImportError:
        print("❌ pyngrok module not installed. Install with: pip install pyngrok")
        return False
    except Exception as e:
        print(f"❌ Error checking ngrok status: {e}")
        return False

if __name__ == "__main__":
    print("\n===== Ngrok Tunnel Status =====\n")
    check_ngrok_status()
    print("\n==============================")
