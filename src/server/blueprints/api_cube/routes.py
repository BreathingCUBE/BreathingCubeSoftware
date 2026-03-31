from . import api_cube_bp
from flask import request, jsonify, current_app
from src.server.decorators.auth import require_api_key
from src.server.utils.validation import require_json_content_type
from src.server.utils.repository import get_cube_user, get_current_task, save_session, get_task_preset


##########################################################################
###                         CUBE API ROUTES                            ###
##########################################################################


# This end-point is currently device only (no user auth required)
@api_cube_bp.post("/task/control")
@require_api_key
def task_control(cube_uuid: str):

    # Get timer object
    timer = current_app.timer

    # Extract associated user account from CUBE UUID
    uid = get_cube_user(cube_uuid)
    if not uid:
        return jsonify({"error": "Cube not registered with user account"}), 401

    # Check Content-Type header
    content_error = require_json_content_type()
    if content_error:
        return content_error

    # Extract data from JSON
    data = request.get_json()
    print("SERVER RECEIVED: ", data)
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
    tt_min = task_time // 60
    tt_sec = task_time % 60

    # Start action logic
    if action == "start":
        timer.start()
        return jsonify({"message": f"{current_task} task started"}), 200

    # Stop action logic
    if action == "stop":
        timer.stop()
        save_session(uid, current_task, elapsed_time)
        if elapsed_time <= task_time:
            min = elapsed_time // 60
            sec = elapsed_time % 60
            return jsonify({"message": f"{current_task} task stopped. "
                                       f"{min}m:{sec}s of session time logged."
                            }), 200
        else:
            extra_time = elapsed_time - task_time
            min = extra_time // 60
            sec = extra_time % 60
            return jsonify({"message": f"{current_task} task stopped. "
                                       f"{tt_min}m:{tt_sec}s of session time + "
                                       f"{min}m:{sec}s of extra session time logged."
                            }), 200

    # Reset action logic
    if action == "reset":
        timer.reset(task_time)
        return jsonify({"message": f"{current_task} task reset",
                        "task_name": current_task,
                        "task_time": task_time,
                        "config": {
                            "task_name": "Meditation",
                            "task_time":10,
                            "task_color": "#0000FF",
                            "timing_pattern": [8, 8, 8, 8],
                            "alarm_type": "bell"
                        }
                        }), 200