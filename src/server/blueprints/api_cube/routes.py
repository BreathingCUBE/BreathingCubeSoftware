import os

import requests
from . import api_cube_bp
from flask import request, jsonify, current_app
from src.server.decorators.auth import require_api_key
from src.server.logging_config import get_logger
from src.server.utils.validation import require_json_content_type, parse_time
from src.server.utils.repository import get_cube_user, get_current_task, save_session, get_task_preset

logger = get_logger(__name__)

def _notify_web_timer_event(*, action: str, uid: str, task_name: str, target_duration: int | None = None, elapsed: int | None = None):
    secret = os.getenv("INTERNAL_SHARED_SECRET")
    if not secret:
        return

    base = os.getenv("WEB_INTERNAL_URL", "http://127.0.0.1:5000").rstrip("/")
    url = f"{base}/internal/timer-event"

    payload: dict = {"action": action, "uid": uid, "task_name": task_name}
    if target_duration is not None:
        payload["target_duration"] = target_duration
    if elapsed is not None:
        payload["elapsed"] = elapsed

    try:
        requests.post(
            url,
            json=payload,
            headers={"X-INTERNAL-SECRET": secret, "Content-Type": "application/json"},
            timeout=1.0,
        )
    except Exception as e:
        logger.warning(f"Failed to notify web timer event: {e}", extra={
            'endpoint': '/api/task/control',
            'action': action,
        })


##########################################################################
###                         CUBE API ROUTES                            ###
##########################################################################


@api_cube_bp.post("/task/control")
@require_api_key
def api_task_control(cube_uuid: str):
    """Interface between hardware cube, Firestore database, and timer service."""

    # Get timer object
    timer = current_app.timer

    # Extract associated user account from CUBE UUID
    uid = get_cube_user(cube_uuid)
    if not uid:
        logger.warning(f"Task control attempted with unregistered cube '{cube_uuid}'", extra={
            'endpoint': '/api/task/control',
            'method': 'POST',
            'error_type': 'unregistered_cube'
        })
        return jsonify({"error": "Cube not registered with user account"}), 401

    # Check Content-Type header
    content_error = require_json_content_type()
    if content_error:
        return content_error

    # Extract data from JSON
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    action = data.get("action")
    elapsed_time = data.get("elapsed_seconds")

    # Load Current task information
    current_task = get_current_task(uid)
    if not current_task:
        return jsonify({"error": "Current task not set"}), 400

    task_data = get_task_preset(uid, current_task)
    task_time = task_data.get("task_time")
    tt_min, tt_sec = parse_time(task_time)

    task_color = task_data.get("task_color")

    task_color = task_data.get("task_color")

    # Start action logic
    if action == "start":
        timer.start()
        _notify_web_timer_event(action="start", uid=uid, task_name=current_task, target_duration=task_time)
        logger.info(f"Task '{current_task}' started via cube", extra={
            'user_id': uid,
            'endpoint': '/api/task/control',
            'method': 'POST',
            'action': 'start'
        })
        return jsonify({"message": f"{current_task} task started"}), 200

    # Stop action logic
    if action == "stop":
        timer.stop()
        authoritative_elapsed = timer.get_elapsed()
        _notify_web_timer_event(action="stop", uid=uid, task_name=current_task, target_duration=task_time, elapsed=authoritative_elapsed)
        save_session(uid, current_task, authoritative_elapsed)
        logger.info(f"Task '{current_task}' stopped, {authoritative_elapsed}s elapsed", extra={
            'user_id': uid,
            'endpoint': '/api/task/control',
            'method': 'POST',
            'action': 'stop',
            'elapsed_seconds': authoritative_elapsed
        })
        if authoritative_elapsed <= task_time:
            min, sec = parse_time(authoritative_elapsed)
            if not min and not sec:
                return jsonify({"error": "Elapsed time must be a positive non-zero integer."}), 400
            return jsonify({"message": f"{current_task} task stopped. "
                                       f"{min}m:{sec}s of session time logged."
                            }), 200
        else:
            extra_time = authoritative_elapsed - task_time
            min, sec = parse_time(extra_time)
            return jsonify({"message": f"{current_task} task stopped. "
                                       f"{tt_min}m:{tt_sec}s of session time + "
                                       f"{min}m:{sec}s of extra session time logged."
                            }), 200

    # Reset action logic
    if action == "reset":
        timer.reset(task_time)
        _notify_web_timer_event(action="reset", uid=uid, task_name=current_task, target_duration=task_time, elapsed=0)
        logger.info(f"Task '{current_task}' reset via cube", extra={
            'user_id': uid,
            'endpoint': '/api/task/control',
            'method': 'POST',
            'action': 'reset',
            'task_time': task_time
        })
        return jsonify({"message": f"{current_task} task reset",
                        "task_name": current_task,
                        "task_time": task_time,
                        "task_color": task_color,
                        "config": {
                            "task_name": current_task,
                            "task_time":task_time,
                            "task_color": task_color,
                            "timing_pattern": [8, 8, 8, 8],
                            "alarm_type": "bell"
                        }
                        }), 200