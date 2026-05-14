import sys
import os
import socket
import logging

# Log dosyasını kullanıcı home dizinine yönlendir (packaged app için)
_app_dir = os.path.join(os.path.expanduser('~'), '.fdmsensor_desktop')
os.makedirs(_app_dir, exist_ok=True)
_log_path = os.path.join(_app_dir, 'server.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(_log_path, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

from server import app
from waitress import serve

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]

if __name__ == "__main__":
    # Start the background scraper safely
    try:
        import threading
        from server import background_scraper
        scraper_thread = threading.Thread(target=background_scraper, daemon=True)
        scraper_thread.start()
        logger.info("Background scraper thread started.")
    except Exception as e:
        logger.error(f"Could not start background scraper: {e}")

    port = int(sys.argv[1]) if len(sys.argv) > 1 else find_free_port()
    
    # Flush stdout immediately so Electron reads PORT line
    print(f"PORT:{port}", flush=True)
    sys.stdout.flush()
    
    logger.info(f"API server starting on port {port}...")
    
    # Run the server. This blocks until the process is terminated.
    serve(app, host='127.0.0.1', port=port, threads=8)
