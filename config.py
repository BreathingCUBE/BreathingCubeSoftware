import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask secret key - MUST be set in production
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError(
            "CRITICAL: FLASK_SECRET_KEY environment variable not set. "
            "Session tokens will be vulnerable. Set FLASK_SECRET_KEY in .env or container."
        )
    
    WEB_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY")
    
    # Resolve Firebase service account path - absolute path for Docker compatibility
    # First try environment variable, then default to serviceAccountKey.json
    service_account_env = os.getenv("FIREBASE_SERVICE_ACCOUNT", "serviceAccountKey.json")
    
    # Make path absolute if it's not already
    if os.path.isabs(service_account_env):
        SERVICE_ACCOUNT_PATH = service_account_env
    else:
        # Resolve relative to project root (where config.py is located)
        PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
        SERVICE_ACCOUNT_PATH = os.path.join(PROJECT_ROOT, service_account_env)
    
    CUBE_API_KEY = os.environ.get("CUBE_API_KEY")
