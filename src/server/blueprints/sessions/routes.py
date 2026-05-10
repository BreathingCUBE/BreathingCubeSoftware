import calendar
from datetime import datetime
from flask import jsonify, request, render_template
from . import sessions_bp
from src.server.decorators.auth import login_required
from src.server.logging_config import get_logger
from src.server.utils.repository import get_session, get_sessions_by_date_range

logger = get_logger(__name__)


@sessions_bp.route('/stats')
@login_required
def stats(uid: str):
    """Render stats page showing latest session metrics."""
    logger.info(f"Stats page loaded", extra={
        'user_id': uid,
        'endpoint': '/stats',
        'method': 'GET'
    })
    return render_template('stats.html')


@sessions_bp.get('/sessions/latest')
@login_required
def session_latest(uid: str):
    """Return the most recent session for the stats page."""
    # Pulls the single most recent session from the new subcollection
    latest_session = get_session(uid)

    if not latest_session:
        return jsonify({"error": "No recorded session history."}), 400

    # .get() safely handles missing fields (like task_color) by returning None,
    # which jsonify perfectly converts to a standard JSON null.
    return jsonify({
        "task": latest_session.get("task"),
        "elapsed_time": latest_session.get("elapsed_time"),
        "timestamp": latest_session.get("timestamp"),
        "task_color": latest_session.get("task_color"),
        "task_type": latest_session.get("task_type"),
        "subject": latest_session.get("subject")
    }), 200


@sessions_bp.get('/sessions/calendar')
@login_required
def sessions_calendar(uid: str):
    """Return session data aggregated by day for calendar heatmap."""
    year = request.args.get("year", default=datetime.now().year, type=int)
    month = request.args.get("month", default=datetime.now().month, type=int)

    # Calculate the last day of the requested month
    _, last_day = calendar.monthrange(year, month)

    # Format dates as YYYY-MM-DD for the repository function
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day:02d}"

    # Fetch sessions from the new subcollection
    sessions = get_sessions_by_date_range(uid, start_date, end_date)

    daily_totals = {}

    for session in sessions:
        ts = session.get("timestamp", "")[:10]  # Safely extracts YYYY-MM-DD from the ISO string
        if ts not in daily_totals:
            daily_totals[ts] = {"count": 0, "total_time": 0}

        daily_totals[ts]["count"] += 1
        daily_totals[ts]["total_time"] += session.get("elapsed_time", 0)

    return jsonify({
        "year": year,
        "month": month,
        "daily_data": daily_totals,
        "max_sessions": max([d["count"] for d in daily_totals.values()]) if daily_totals else 1
    }), 200