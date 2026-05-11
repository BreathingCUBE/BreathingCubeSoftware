from flask import Flask, request, jsonify

app = Flask(__name__)

# ---- server state ----
state = {}

# ---- CONFIG (GET) ---- This gets called upon RESET command
@app.route("/api/esp/config", methods=["GET"])
def get_config():
    config = {
        "task_name": "Meditation",
        "task_time":10,
        "task_color": "#0004D400",
        "timing_pattern": [4, 4, 4, 4],
        "alarm_type": "bell"
    }
    return jsonify(config), 200


# ---- TELEMETRY (POST) ---- This gets called upon START/STOP COMMAND command
@app.route("/api/task/control", methods=["POST"])
def telemetry():
    data = request.get_json()
    # print("RAW DATA:", data)
    action = None

    if data:
        action = data.get("action") or data.get("COMMAND") 


    if action == "START":
        state["mode"] = "running"
        state["task"] = data.get("task")
        state["time Elapsed"] = data.get("timeElapsed")

    elif action == "STOP":
        state["mode"] = "stopped"
        state["timeElapsed"] = data.get("timeElapsed")

    elif action == "RESET":
        state["mode"] = "stopped"
        state["timeElapsed"] = 0
    elif not action:
        return jsonify({"error": "Invalid payload", "received": data}), 400
    
    print("Parsed action:", action)

    response = {
        "status": "ok",
        "state": state
    } 

    return jsonify(response), 200

# ---- RUN SERVER ----
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)