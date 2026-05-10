from . import api_timer_bp
from flask import request, jsonify, current_app
from src.server.decorators.auth import require_jwt
from src.server.logging_config import get_logger
from src.server.utils.validation import require_json_content_type
from src.server.utils.repository import get_task_preset

logger = get_logger(__name__)


##########################################################################
###                        TIMER API ROUTES                            ###
##########################################################################


#-- MAY NOT NEED --#
@api_timer_bp.post("/timer/reset")
@require_jwt
def api_reset_timer(uid: str):
    """Reset web timer to selected preset task time."""

    # Get timer object
    timer = current_app.timer

    # checking for content error
    content_error = require_json_content_type()
    if content_error:
        return content_error

    # parsing data from json
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    # checking parsed data if valid
    task_name = data.get("task_name")
    if not task_name:
        return jsonify({"error": "task name required"}), 400

    # parsing preset data using task name
    preset_data = get_task_preset(uid, task_name)

    # parsing current time from preset data
    task_time = preset_data.get("task_time")

    # resetting time from preset_data
    timer.stop()
    timer.reset(task_time)

    logger.info(f"Timer reset via API for task '{task_name}' ({task_time}s)", extra={
        'user_id': uid,
        'endpoint': '/api/timer/reset',
        'method': 'POST'
    })

    # return success
    return jsonify({"task_time": task_time}), 200