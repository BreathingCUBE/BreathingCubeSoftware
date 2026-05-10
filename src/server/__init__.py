from flask import Flask
from config import Config
from .services.timer_sevice import CountupTimer
import os

# Import blueprints
from src.server.blueprints.api_cube import api_cube_bp
from src.server.blueprints.api_presets import api_presets_bp
from src.server.blueprints.api_profile import api_profile_bp
from src.server.blueprints.api_session import api_session_bp
from src.server.blueprints.api_timer import api_timer_bp
from src.server.blueprints.auth import auth_bp
from src.server.blueprints.presets import presets_bp
from src.server.blueprints.sessions import sessions_bp
from src.server.blueprints.dashboard import dashboard_bp
from src.server.blueprints.user_info import user_info_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Determine app type: 'web' for UI routes, 'api' for REST endpoints
    app_type = os.getenv('APP_TYPE', 'web')

    # Register blueprints based on APP_TYPE
    if app_type == 'api':
        # API-only mode: register ONLY API endpoints (for cube device communication)
        app.register_blueprint(api_cube_bp)
        app.register_blueprint(api_presets_bp)
        app.register_blueprint(api_profile_bp)
        app.register_blueprint(api_session_bp)
        app.register_blueprint(api_timer_bp)
    else:
        # Web mode (default): register ONLY web routes (UI, auth, dashboard)
        # API calls from web will proxy to the API container via HTTP
        app.register_blueprint(auth_bp)
        app.register_blueprint(presets_bp)
        app.register_blueprint(sessions_bp)
        app.register_blueprint(dashboard_bp)
        app.register_blueprint(user_info_bp)

    # Initialize Timer Object
    app.timer = CountupTimer()

    return app