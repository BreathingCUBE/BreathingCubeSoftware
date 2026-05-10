from src.server import create_app
from src.server.logging_config import setup_logging
from dotenv import load_dotenv
import os
from functools import wraps

load_dotenv()

# Initialize logging early
setup_logging()

# Create the application instance at module level (required for gunicorn)
app = create_app()


# Add health check endpoint
@app.route('/health')
def health():
    """Health check endpoint for Docker/Kubernetes."""
    # Security: Do not expose internal app configuration
    return {'status': 'healthy'}, 200


if __name__ == "__main__":
    # Determine configuration based on environment
    app_type = os.getenv('APP_TYPE', 'web')
    port = 5000 if app_type == 'web' else 5001
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Host '0.0.0.0' makes the server accessible to other devices (like your phone)
    # on the same Wi-Fi network.
    app.run(host='0.0.0.0', port=int(port), debug=debug)