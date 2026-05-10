from firebase import user_profiles, cubes, session_history
from google.cloud.firestore import DELETE_FIELD, ArrayUnion, SERVER_TIMESTAMP
from datetime import datetime, timezone

def save_user_info(uid: str, user_info: dict[str, str]):
    """Saves user information in database."""
    user_profiles.document(uid).set({"user_info": user_info}, merge=True)


def get_user_info(uid: str, field: str):
    """Reads a specific user information field from the database."""
    doc = user_profiles.document(uid).get()
    if not doc.exists:
        return None

    user_info = doc.to_dict().get("user_info")
    if not user_info:
        return None

    if not field in user_info:
        return None
    return user_info.get(field)


def get_all_user_info(uid: str):
    """Reads all user information from the database."""
    doc = user_profiles.document(uid).get()
    if not doc.exists:
        return None

    user_info = doc.to_dict().get("user_info")
    if not user_info:
        return None
    return user_info


def save_cube_uuid(uid: str, cube_uuid: str):
    cubes.document(cube_uuid).set({"user uid": uid}, merge=True)


def get_cube_user(cube_uuid: str):
    doc = cubes.document(cube_uuid).get()
    if not doc.exists:
        return None

    uid = doc.to_dict().get("user uid")
    if not uid:
        return None
    return uid


def get_profile(uid: str):
    """Reads all user profile data from the database."""
    doc = user_profiles.document(uid).get()
    if doc.exists:
        return doc.to_dict()
    return None


def get_task_preset(uid: str, task: str):
    doc = user_profiles.document(uid).get()
    if not doc.exists:
        return None

    presets = doc.to_dict().get("presets")
    if not presets:
        return None

    if not task in presets:
        return None
    return presets.get(task)


def get_all_task_presets(uid: str):
    doc = user_profiles.document(uid).get()
    if not doc.exists:
        return None

    presets = doc.to_dict().get("presets")
    if not presets:
        return None
    return presets


def update_task_preset(uid: str, task: str, preset_data: dict):
    doc_ref = user_profiles.document(uid)
    doc = doc_ref.get()

    if doc.exists:
        presets = doc.to_dict().get("presets", {})
    else:
        presets = {}

    presets[task] = preset_data

    doc_ref.set({"presets": presets}, merge=True)


def delete_task_preset(uid: str, task: str):
    user_profiles.document(uid).update({
        f"presets.{task}": DELETE_FIELD
    })


def set_current_task(uid: str, task_name: str):
    doc_ref = user_profiles.document(uid)
    doc_ref.set({"current_task": task_name}, merge=True)


def get_current_task(uid: str):
    doc = user_profiles.document(uid).get()
    if not doc.exists:
        return None

    current_task = doc.to_dict().get("current_task")
    if not current_task:
        return None
    return current_task


def get_session(uid: str):
    """Get the most recent session (for backward compatibility)."""
    sessions = get_sessions(uid, limit=1)
    return sessions[0] if sessions else None


def get_sessions(uid: str, limit: int = 100):
    """Retrieve all sessions for a user (newest first)."""
    docs = (
        session_history.document(uid).collection("sessions")
        .order_by("timestamp", direction="DESCENDING")
        .limit(limit)
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def get_sessions_by_date_range(uid: str, start_date: str, end_date: str):
    """Get sessions within a date range (ISO format: YYYY-MM-DD)."""
    start_iso = f"{start_date}T00:00:00"
    end_iso = f"{end_date}T23:59:59"

    docs = (
        session_history.document(uid).collection("sessions")
        .where("timestamp", ">=", start_iso)
        .where("timestamp", "<=", end_iso)
        .order_by("timestamp", direction="DESCENDING")
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def save_session(uid: str, task: str, elapsed_time: int, task_color: str = None):
    """Append a new session to session_history array with server timestamp."""
    session_data = {
        "task": task,
        "elapsed_time": elapsed_time,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    if task_color:
        session_data["task_color"] = task_color

    # Subcollection: session_history/{uid}/sessions/{auto-id}
    session_history.document(uid).collection("sessions").add(session_data)
