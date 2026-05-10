from . import api_profile_bp
from flask import request, jsonify
from src.server.decorators.auth import require_jwt
from src.server.logging_config import get_logger
from src.server.utils.validation import require_json_content_type, validate_user_info
from src.server.utils.repository import save_user_info, save_cube_uuid, get_user_info, get_all_user_info, get_profile

logger = get_logger(__name__)


##########################################################################
###                       Profile API ROUTES                           ###
##########################################################################


@api_profile_bp.get("/profile")
@require_jwt
def api_get_profile(uid: str):
    """Get all the current user's profile data."""

    # Get all profile data
    profile_data = get_profile(uid)
    
    logger.info(f"Profile retrieved", extra={
        'user_id': uid,
        'endpoint': '/api/profile',
        'method': 'GET'
    })

    return jsonify({"profile": profile_data}), 200


@api_profile_bp.route("/profile/user_info/<field>", methods=["GET"])
@require_jwt
def api_get_user_info(uid: str, field: str):
    """Get the user's user information. (ie. first_name, last_name, etc.)"""

    # Return all user data if passed "all"
    if field == "all":
        user_data = get_all_user_info(uid)
        if not user_data:
            logger.warning(f"No user info found", extra={
                'user_id': uid,
                'endpoint': '/api/profile/user_info/all',
                'method': 'GET'
            })
            return jsonify({"error": "No information added."}), 404
        logger.info(f"Retrieved all user info", extra={
            'user_id': uid,
            'endpoint': '/api/profile/user_info/all',
            'method': 'GET'
        })
        return jsonify({"user_info": user_data}), 200

    # Return user data
    user_data = get_user_info(uid, field)
    if not user_data:
        logger.warning(f"User info field not found: {field}", extra={
            'user_id': uid,
            'endpoint': '/api/profile/user_info/{field}',
            'method': 'GET',
            'field': field
        })
        return jsonify({"error": "No information added."}), 404
    
    logger.info(f"Retrieved user info field: {field}", extra={
        'user_id': uid,
        'endpoint': '/api/profile/user_info/{field}',
        'method': 'GET',
        'field': field
    })

    return jsonify({f"{field}": user_data}), 200


@api_profile_bp.put("/profile/user_info")
@require_jwt
def api_update_user_info(uid: str):
    """Update user information. (ie. first_name, last_name, etc.)"""

    # Check Content-Type header
    content_error = require_json_content_type()
    if content_error:
        return content_error

    # Extract data from JSON
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    # Validate input data
    error = validate_user_info(data)
    if error:
        return jsonify({"error": error}), 400

    # Prepare updated user info values (only include provided fields)
    first_name = data.get("first_name")
    last_name = data.get("last_name")

    user_info = {}
    if first_name is not None:
        user_info["first_name"] = first_name.strip().title() if first_name else ""
    if last_name is not None:
        user_info["last_name"] = last_name.strip().title() if last_name else ""

    # Save updated user info in database
    save_user_info(uid, user_info)
    
    logger.info(f"User info updated", extra={
        'user_id': uid,
        'endpoint': '/api/profile/user_info',
        'method': 'PUT',
        'fields_updated': list(user_info.keys())
    })

    # Return updated user info with all fields
    updated_user_info = get_all_user_info(uid)
    return jsonify({"user_info": updated_user_info}), 200


@api_profile_bp.post("/profile/cube")
@require_jwt
def api_save_cube(uid: str):
    """Register a CUBE UUID with a user account."""

    # Check Content-Type header
    content_error = require_json_content_type()
    if content_error:
        return content_error

    # Extract data from JSON
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    cube_uuid = data.get("cube_uuid")
    if not cube_uuid:
        return jsonify({"error": "Cube uuid required"}), 400

    # Save cube uuid
    save_cube_uuid(uid, cube_uuid)
    
    logger.info(f"Cube registered: {cube_uuid}", extra={
        'user_id': uid,
        'endpoint': '/api/profile/cube',
        'method': 'POST',
        'cube_uuid': cube_uuid
    })

    return jsonify({"cube_uuid": cube_uuid}), 200