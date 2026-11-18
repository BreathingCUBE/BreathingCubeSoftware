'''
Transport-independent command parsing for the cube.

BLE (and any future link) hands raw bytes to parse_command(). The result is a
small dict that CubeController.apply_command() executes on the main loop, so
every wireless interface goes through the same application logic.

Accepted formats (UTF-8, case-insensitive keywords):

  Text (fits in a default 20-byte BLE write):
    start                 start a session (same as a double tap from RESET)
    reset                 reset the session (same as a double tap from START)
    toggle                exactly what a double tap does
    focus <seconds>       (re)start a session that rings after <seconds>,
                          breathing meanwhile (desktop app "Switch to Focus")
    stop                  stop the timer and lights (app "End Focus")
    status                refresh the status characteristic
    perf                  publish the performance counters
    perf reset            clear the performance counters
    disconnect            drop the BLE connection
    color #RRGGBB[XX]     same as the server's task_color
    time <seconds>        same as the server's task_time
    task <name>           same as the server's task_name

  JSON (needs a larger MTU, which nRF Connect normally negotiates):
    {"cmd": "start"}
    {"cmd": "focus", "task_time": 1500, "task_name": "Piano"}
    {"task_name": "Read", "task_color": "#00ff0000", "task_time": 1500}
    The second form is the same payload the REST server returns, and goes
    through CubeController.upload_configSettings() unchanged.

parse_command() only allocates a few small objects and never touches I2C,
flash, or LEDs, so it is safe to call from a BLE handler.
'''

import json

SIMPLE_OPS = ("start", "reset", "stop", "toggle", "status", "perf", "disconnect")
SETTING_KEYS = {
    "color": "task_color",
    "colour": "task_color",
    "time": "task_time",
    "task": "task_name",
}
MAX_COMMAND_BYTES = 256


def parse_command(data):
    """Turn raw bytes into {"op": ..., "payload": ...}. Raises ValueError."""
    if not data:
        raise ValueError("empty command")
    if len(data) > MAX_COMMAND_BYTES:
        raise ValueError("command too long")
    try:
        text = bytes(data).decode("utf-8").strip()
    except Exception:
        raise ValueError("command is not UTF-8")
    if not text:
        raise ValueError("empty command")

    if text[0] == "{":
        return _parse_json(text)
    return _parse_text(text)


def _parse_json(text):
    try:
        obj = json.loads(text)
    except ValueError:
        raise ValueError("invalid JSON")
    if not isinstance(obj, dict):
        raise ValueError("JSON command must be an object")

    op = obj.get("cmd")
    if op is not None:
        if not isinstance(op, str):
            raise ValueError("cmd must be a string")
        if op.lower() == "focus":
            payload = {}
            for key in ("task_time", "task_name", "task_color"):
                if key in obj:
                    payload[key] = obj[key]
            return _focus(payload)
        return _parse_text(op)

    # No "cmd": treat it as a settings payload in the server's format.
    return {"op": "settings", "payload": obj}


def _parse_text(text):
    keyword, _, rest = text.partition(" ")
    keyword = keyword.lower()
    rest = rest.strip()

    if keyword == "perf" and rest.lower() == "reset":
        return {"op": "perf_reset"}
    if keyword == "focus":
        try:
            seconds = int(rest)
        except ValueError:
            raise ValueError("focus needs whole seconds, e.g. focus 1500")
        return _focus({"task_time": seconds})
    if keyword in SIMPLE_OPS and not rest:
        return {"op": keyword}

    key = SETTING_KEYS.get(keyword)
    if key is not None:
        if not rest:
            raise ValueError(keyword + " needs a value")
        if key == "task_time":
            try:
                value = int(rest)
            except ValueError:
                raise ValueError("time must be whole seconds")
        else:
            value = rest
        return {"op": "settings", "payload": {key: value}}

    raise ValueError("unknown command: " + keyword)


def _focus(payload):
    seconds = payload.get("task_time")
    if not isinstance(seconds, int) or seconds <= 0:
        raise ValueError("focus time must be a positive whole number of seconds")
    return {"op": "focus", "payload": payload}
