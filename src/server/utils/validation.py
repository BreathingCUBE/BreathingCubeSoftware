import re
from flask import jsonify, request


def require_json_content_type():
    """Ensure the request is JSON; returns an error response tuple if not."""
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415
    return None


def validate_login_data(data: dict[str, str]):
    errors = []
    allowed = {"email", "password", "confirm_password"}

    # Whitelist Check - reject unknown fields
    if unknown := set(data.keys()) - allowed:
        errors.append(f"Unknown fields: {unknown}")

    # Reject None value inputs
    for key, value in data.items():
        if value is None:
            errors.append(f"{key} cannot be None")

    # Bounds Checking - enforce length limits
    email = data.get("email", "")
    if email:
        if len(email) > 50:
            errors.append("Email must be 50 chars or less")

    # Pattern Validation - enforce format rules
    password = data.get("password", "")
    if password:
        if not re.match(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]{8,50}$", password):
            errors.append("Password invalid")

    confirm_password = data.get("confirm_password", "")
    if confirm_password:
        if not re.match(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]{8,50}$", confirm_password):
            errors.append("Confirmation Password invalid")

    return errors  # Return ALL errors


def validate_preset(data: dict):
    errors = []
    allowed = {"task_name", "task_time", "task_color"}

    # Whitelist Checks
    if unknown := set(data.keys()) - allowed:
        errors.append(f"Unknown fields: {unknown}")

    # Reject None value inputs
    for key, value in data.items():
        if value is None:
            errors.append(f"{key} cannot be None")

    # Bounds Checking for task_name
    task_name = data.get("task_name", "")

    if task_name:
        if not isinstance(task_name, str):
            errors.append("task_name must be a string")
        else:
            if len(task_name) > 30:
                errors.append("task_name must be 30 chars or less")

    # Type / Value Validation for task_time
    task_time = data.get("task_time", "")

    if task_time:
        if isinstance(task_time, int):
            if task_time < 0:
                errors.append("Task time must be a positive integer")
            if task_time > 5940:
                errors.append("Task time must be less then 99 minutes")
        else:
            errors.append("Task time must be a positive integer")
    if task_time == 0:
        errors.append("Task time must be greater than zero")

    # Pattern Validation for task_color (RGB or RGBW)
    task_color = data.get("task_color", "")

    if task_color:
        if not isinstance(task_color, str) or not re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$").fullmatch(task_color):
            errors.append("Task color must be a valid hex RGB or RGBW string (e.g., '#0000ff' or '#0000ffff')")

    return errors  # Return ALL errors


def validate_user_info(data: dict[str, str]):
    errors = []
    allowed = {"first_name", "last_name"}

    # Whitelist Check - reject unknown fields
    if unknown := set(data.keys()) - allowed:
        errors.append(f"Unknown fields: {unknown}")

    # Reject None value inputs
    for key, value in data.items():
        if value is None:
            errors.append(f"{key} cannot be None")

    # Bounds Checking - enforce length limits
    first_name = data.get("first_name", "")
    if first_name:
        if len(first_name) > 50:
            errors.append("first_name must be 50 chars or less")

    last_name = data.get("last_name", "")
    if last_name:
        if len(last_name) > 50:
            errors.append("last_name must be 50 chars or less")

    return errors  # Return ALL errors


def normalize_task_color(task_color):
    if not task_color or not isinstance(task_color, str):
        return task_color

    task_color = task_color.strip().lower()

    if re.fullmatch(r"^#[0-9a-f]{6}$", task_color):
        return task_color + "ff"

    if re.fullmatch(r"^#[0-9a-f]{8}$", task_color):
        return task_color

    # fallback as provided
    return task_color


def parse_time(total_time_sec: int):
    if not isinstance(total_time_sec, int) or not total_time_sec > 0:
        return None, None
    minutes = total_time_sec // 60
    seconds = total_time_sec % 60
    return minutes, seconds


