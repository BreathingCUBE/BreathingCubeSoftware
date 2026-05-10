from . import api_presets_bp
from flask import request, jsonify
from src.server.decorators.auth import require_jwt
from src.server.logging_config import get_logger
from src.server.utils.validation import normalize_task_color, require_json_content_type, validate_preset
from src.server.utils.repository import delete_task_preset, update_task_preset, get_all_task_presets, get_task_preset

logger = get_logger(__name__)


##########################################################################
###                       PRESETS API ROUTES                           ###
##########################################################################

# helper function
def extract_preset_data():
    # Check Content-Type header
    content_error = require_json_content_type()
    if content_error:
        return content_error

    # Extract data from JSON
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    # Validate input data
    error = validate_preset(data)
    if error:
        return jsonify({"error": error}), 400

    return data


@api_presets_bp.route("/profile/preset/<task_name>", methods=["GET"])
@require_jwt
def api_get_preset(uid: str, task_name: str):
    """Get preset task configurations."""

    # Format task name
    task_name = task_name.strip().title()

    # Return all presets if passed "All"
    if task_name == "All":
        presets = get_all_task_presets(uid)
        if not presets:
            logger.warning(f"No presets configured for user", extra={
                'user_id': uid,
                'endpoint': '/api/profile/preset/All',
                'method': 'GET',
                'error_type': 'no_presets'
            })
            return jsonify({"error": "No presets configured."}), 404
        logger.info(f"Retrieved all presets for user", extra={
            'user_id': uid,
            'endpoint': '/api/profile/preset/All',
            'method': 'GET',
            'preset_count': len(presets)
        })
        return jsonify({"presets": presets}), 200

    # Return preset data
    preset_data = get_task_preset(uid, task_name)
    if not preset_data:
        logger.warning(f"Preset not found: {task_name}", extra={
            'user_id': uid,
            'endpoint': '/api/profile/preset/{task_name}',
            'method': 'GET',
            'task_name': task_name,
            'error_type': 'preset_not_found'
        })
        return jsonify({"error": "Preset not found"}), 404
    logger.info(f"Retrieved preset: {task_name}", extra={
        'user_id': uid,
        'endpoint': '/api/profile/preset/{task_name}',
        'method': 'GET',
        'task_name': task_name
    })
    return jsonify({f"{task_name}": preset_data}), 200


@api_presets_bp.post("/profile/preset")
@require_jwt
def api_create_preset(uid: str):
    """Create new preset task configuration."""

    # Extract preset data from JSON
    data = extract_preset_data()

    # Organize preset task data
    task_name = (data.get("task_name") or "").strip().title()
    if not task_name:
        return jsonify({"error": "task name required"}), 400

    task_time = data.get("task_time")
    if not task_time:
        return jsonify({"error": "task time required"}), 400

    task_color = normalize_task_color(data.get("task_color"))
    if not task_color:
        return jsonify({"error": "task color required"}), 400

    preset_data = {
        "task_time": task_time,
        "task_color": task_color,
    }

    # Save new preset task in database
    update_task_preset(uid, task_name, preset_data)
    
    logger.info(f"Preset created: {task_name}", extra={
        'user_id': uid,
        'endpoint': '/api/profile/preset',
        'method': 'POST',
        'task_name': task_name,
        'task_time': task_time
    })

    return jsonify({f"{task_name}": preset_data,}), 201


@api_presets_bp.put("/profile/preset")
@require_jwt
def api_update_preset(uid: str):
    """Update preset task configuration."""

    #Extract preset data from JSON
    data = extract_preset_data()

    # Prepare updated preset task data (only include provided fields)
    task_name = (data.get("task_name") or "").strip().title()
    if not task_name:
        return jsonify({"error": "Task name required"}), 400

    # Check for existing preset
    preset_data = get_task_preset(uid, task_name)
    if not preset_data:
        return jsonify({"error": "Task not found"}), 404

    task_time = data.get("task_time")
    task_color = data.get("task_color")

    updated_preset_data = {}
    if task_time is not None:
        updated_preset_data["task_time"] = task_time if task_time else ""
    if task_color is not None:
        updated_preset_data["task_color"] = normalize_task_color(task_color) if task_color else ""

    # Save updated preset task in database
    update_task_preset(uid, task_name, updated_preset_data)
    
    logger.info(f"Preset updated: {task_name}", extra={
        'user_id': uid,
        'endpoint': '/api/profile/preset',
        'method': 'PUT',
        'task_name': task_name
    })

    # Return updated task with all fields
    preset_data = get_task_preset(uid, task_name)
    return jsonify({f"{task_name}": preset_data,}), 200


@api_presets_bp.delete("/profile/preset")
@require_jwt
def api_delete_preset(uid: str):
    """Delete preset task configuration."""

    # Check Content-Type header
    content_error = require_json_content_type()
    if content_error:
        return content_error

    # Extract data from JSON
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    task_name = (data.get("task_name") or "").strip().title()
    if not task_name:
        return jsonify({"error": "task name required"}), 400

    preset_data = get_task_preset(uid, task_name)

    if not preset_data:
        return jsonify({"error": "Preset not found"}), 404

    delete_task_preset(uid, task_name)
    
    logger.info(f"Preset deleted: {task_name}", extra={
        'user_id': uid,
        'endpoint': '/api/profile/preset',
        'method': 'DELETE',
        'task_name': task_name
    })

    return jsonify({"message": f"{task_name} task preset information successfully deleted."}), 200