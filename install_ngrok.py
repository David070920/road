#!/usr/bin/env python3
"""
Helper script to install ngrok for the Road Quality Measurement System
"""
import sys
import os
import subprocess
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("NgrokInstaller")

def install_pyngrok():
    """Install pyngrok package if not already installed"""
    try:
        import pyngrok
        logger.info("✅ pyngrok is already installed")
        return True
    except ImportError:
        logger.info("Installing pyngrok package...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyngrok"])
            logger.info("✅ pyngrok successfully installed")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to install pyngrok: {e}")
            return False

def install_ngrok():
    """Install ngrok binary using pyngrok"""
    try:
        import pyngrok.ngrok as ngrok
        logger.info("Installing ngrok binary...")
        
        # Make sure we have the latest version of ngrok configs
        from pyngrok import conf
        conf.get_default().config_path = None
        
        # Install ngrok
        ngrok.install_ngrok()
        
        # Verify installation
        try:
            if hasattr(ngrok, 'get_ngrok_path'):
                path = ngrok.get_ngrok_path()
            else:
                from pyngrok.conf import PyngrokConfig
                path = PyngrokConfig().ngrok_path
                
            if path and os.path.exists(path):
                logger.info(f"✅ ngrok successfully installed at: {path}")
                
                # Try to get the version for verification
                result = subprocess.run([path, "version"], 
                                     stdout=subprocess.PIPE, 
                                     stderr=subprocess.PIPE,
                                     text=True)
                logger.info(f"ngrok version: {result.stdout.strip()}")
                return True
            else:
                logger.error("❌ ngrok path not found after installation")
                return False
        except Exception as e:
            logger.error(f"❌ Error verifying ngrok installation: {e}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to install ngrok: {e}")
        return False

def main():
    """Main installation function"""
    print("\n" + "=" * 60)
    print(" Ngrok Installation for Road Quality System ")
    print("=" * 60 + "\n")
    
    # Step 1: Install pyngrok package
    print("\nStep 1: Installing pyngrok package...")
    if not install_pyngrok():
        print("\n❌ Failed to install pyngrok package. Please install it manually:")
        print("   pip install pyngrok")
        return 1
    
    # Step 2: Install ngrok binary
    print("\nStep 2: Installing ngrok binary...")
    if not install_ngrok():
        print("\n❌ Failed to install ngrok binary. Please try installing manually:")
        print("   python -c 'from pyngrok import ngrok; ngrok.install_ngrok()'")
        return 1
    
    print("\n✅ Installation complete! You can now use remote access features.")
    print("   Run the main application with remote access enabled.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
