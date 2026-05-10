import os
import hmac
from functools import wraps
from firebase_admin import auth
from flask import request, jsonify, redirect, url_for, session

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "uid" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, uid=session["uid"], **kwargs)
    return wrapper


def require_jwt(f):
    """Decorator to require JWT authentication for API endpoints.

    Verifies the JWT token from the Authorization header and injects
    the user ID into the route function as a keyword argument 'uid'.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return jsonify({"error": "Missing Authorization header"}), 401

        # Check for "Bearer " prefix
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Invalid Authorization header format"}), 401

        token = auth_header.split(" ")[1]

        try:
            # Verify the JWT token using Firebase Admin SDK
            decoded_token = auth.verify_id_token(token)
            uid = decoded_token["uid"]
            # Inject uid into the route function
            return f(*args, uid=uid, **kwargs)
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401
    return decorated_function


def require_api_key(f):
    """Decorator to require API key authentication for device endpoints.
    
    Expected header: X-API-Key: <actual_cube_uuid>
    The X-API-Key header should contain the cube's UUID for authentication.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get the expected key from environment
        expected_key = os.environ.get("CUBE_API_KEY")

        if not expected_key:
            return jsonify({"error": "API key not configured on server"}), 500

        # Get the provided key from request headers
        provided_key = request.headers.get("X-API-Key")

        if not provided_key:
            return jsonify({"error": "Missing X-API-Key header"}), 401

        # Compare keys
        if provided_key != expected_key:
            print("Provided key:", provided_key)
            print("Expected key:", expected_key)
            return jsonify({"error": "Unauthorized"}), 401

        # Security: X-API-Key header should contain the actual cube_uuid
        # Not the API key itself. Extract from request if provided.
        cube_uuid = request.headers.get("X-Cube-UUID", provided_key)

        # Allow the route to execute with the cube UUID
        return f(*args, cube_uuid=cube_uuid, **kwargs)
    return decorated_function


