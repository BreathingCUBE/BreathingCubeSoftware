# test_api_session.py
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UID = "test_user_123"

URL_TASK_CURRENT   = "http://localhost:5000/api/task/current"
URL_SESSION_LATEST = "http://localhost:5000/api/sessions/latest"
URL_SESSIONS       = "http://localhost:5000/api/sessions"
URL_SESSIONS_RANGE = "http://localhost:5000/api/sessions/range"
URL_SESSIONS_CAL   = "http://localhost:5000/api/sessions/calendar"

# Bearer token value doesn't matter — verify_id_token is mocked by mock_firebase_auth
AUTH_HEADER = {"Authorization": "Bearer test-token"}

PRESET_DATA  = {"task_color": "#ffaa00", "task_time": 600}
SESSION_DATA = {"task": "Meditation", "elapsed_time": 300, "timestamp": "2024-06-15T10:00:00", "task_color": "#ffaa00"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_doc(data: dict, exists: bool = True) -> MagicMock:
    """Return a Firestore document mock."""
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = data
    return doc


def make_missing_doc() -> MagicMock:
    """Return a Firestore document mock representing a missing document."""
    doc = MagicMock()
    doc.exists = False
    return doc


def make_session_doc(data: dict) -> MagicMock:
    """Return a Firestore document mock whose .to_dict() returns session data."""
    doc = MagicMock()
    doc.to_dict.return_value = data
    return doc


def setup_user_doc(mock_firestore_client, data=None, exists=True):
    """Wire the user_profiles collection to return a document with the given data."""
    if data is None:
        data = {
            "current_task": "Meditation",
            "presets": {"Meditation": PRESET_DATA}
        }
    mock_firestore_client['user_profiles'].document.return_value.get.return_value = (
        make_mock_doc(data) if exists else make_missing_doc()
    )


def setup_sessions_stream(mock_firestore_client, sessions: list):
    """
    Wire the session_history subcollection stream to return the given session dicts.
    Covers the chain: document → collection → order_by → limit → stream
    """
    mock_docs = [make_session_doc(s) for s in sessions]
    (
        mock_firestore_client['session_history']
        .document.return_value
        .collection.return_value
        .order_by.return_value
        .limit.return_value
        .stream.return_value
    ) = mock_docs


# ---------------------------------------------------------------------------
# Guard fixture — enforces that every test actually hit a mock collection
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def assert_mock_firestore_was_used(request, mock_firestore_client):
    """
    After each test, assert that at least one mocked Firestore collection was
    called. Tests that legitimately never reach Firestore (e.g. auth rejections
    before any DB call) can opt out with @pytest.mark.no_firestore.
    """
    yield
    if request.node.get_closest_marker("no_firestore"):
        return
    mocks = {
        'user_profiles':   mock_firestore_client['user_profiles'],
        'cubes':           mock_firestore_client['cubes'],
        'session_history': mock_firestore_client['session_history'],
    }
    any_called = any(
        m.called or m.document.called
        for m in mocks.values()
    )
    assert any_called, (
        "Test did not interact with any mocked Firestore collection. "
        "Ensure the repo fixture is wiring collections to their mocks."
    )


# ---------------------------------------------------------------------------
# JWT authentication guard tests (shared across all session routes)
# ---------------------------------------------------------------------------

class TestSessionAuth:

    @pytest.mark.no_firestore
    def test_get_task_current_returns_401_when_no_auth_header(self, client, repo, mock_firestore_client):
        """Returns 401 when GET /task/current is called without an Authorization header."""
        response = client.get(URL_TASK_CURRENT)

        assert response.status_code == 401
        mock_firestore_client['user_profiles'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_get_task_current_returns_401_when_token_is_invalid(self, client, repo, mock_firestore_client, monkeypatch):
        """Returns 401 when GET /task/current is called with a token that fails verification."""
        monkeypatch.setattr(
            "firebase_admin.auth.verify_id_token",
            MagicMock(side_effect=Exception("invalid token"))
        )

        response = client.get(URL_TASK_CURRENT, headers=AUTH_HEADER)

        assert response.status_code == 401
        mock_firestore_client['user_profiles'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_post_task_current_returns_401_when_no_auth_header(self, client, repo, mock_firestore_client):
        """Returns 401 when POST /task/current is called without an Authorization header."""
        response = client.post(
            URL_TASK_CURRENT,
            json={"task_name": "Meditation"},
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 401
        mock_firestore_client['user_profiles'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_get_session_latest_returns_401_when_no_auth_header(self, client, repo, mock_firestore_client):
        """Returns 401 when GET /session/latest is called without an Authorization header."""
        response = client.get(URL_SESSION_LATEST)

        assert response.status_code == 401
        mock_firestore_client['session_history'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_get_sessions_returns_401_when_no_auth_header(self, client, repo, mock_firestore_client):
        """Returns 401 when GET /sessions is called without an Authorization header."""
        response = client.get(URL_SESSIONS)

        assert response.status_code == 401
        mock_firestore_client['session_history'].document.assert_not_called()


# ---------------------------------------------------------------------------
# GET /task/current
# ---------------------------------------------------------------------------

class TestGetCurrentTask:

    def test_returns_200_with_current_task_name(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with the current task name when one is set."""
        setup_user_doc(mock_firestore_client)

        response = client.get(URL_TASK_CURRENT, headers=AUTH_HEADER)

        assert response.status_code == 200
        assert response.get_json()["current_task"] == "Meditation"
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_400_when_no_current_task_is_set(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 400 when the user document has no current_task field."""
        setup_user_doc(mock_firestore_client, data={})

        response = client.get(URL_TASK_CURRENT, headers=AUTH_HEADER)

        assert response.status_code == 400
        assert response.get_json()["error"] == "Current task not set"
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_400_when_user_doc_does_not_exist(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 400 when the user document is missing entirely."""
        setup_user_doc(mock_firestore_client, exists=False)

        response = client.get(URL_TASK_CURRENT, headers=AUTH_HEADER)

        assert response.status_code == 400
        assert response.get_json()["error"] == "Current task not set"
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


# ---------------------------------------------------------------------------
# POST /task/current
# ---------------------------------------------------------------------------

class TestSetCurrentTask:

    def test_returns_200_and_sets_current_task(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 and writes the new current task when the preset exists."""
        setup_user_doc(mock_firestore_client)

        response = client.post(
            URL_TASK_CURRENT,
            json={"task_name": "Meditation"},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 200
        assert response.get_json()["current_task"] == "Meditation"
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.set.assert_called_once_with(
            {"current_task": "Meditation"}, merge=True
        )

    def test_strips_and_title_cases_task_name_before_lookup(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Normalises the task_name (strip + title case) before looking up the preset."""
        setup_user_doc(mock_firestore_client)

        response = client.post(
            URL_TASK_CURRENT,
            json={"task_name": "  meditation  "},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 200
        assert response.get_json()["current_task"] == "Meditation"
        mock_firestore_client['user_profiles'].document.return_value.set.assert_called_once_with(
            {"current_task": "Meditation"}, merge=True
        )

    def test_returns_404_when_preset_does_not_exist(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 404 when the task_name has no matching preset for the user."""
        setup_user_doc(mock_firestore_client, data={"presets": {}})

        response = client.post(
            URL_TASK_CURRENT,
            json={"task_name": "NonExistent"},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 404
        assert response.get_json()["error"] == "Preset not found"
        mock_firestore_client['user_profiles'].document.return_value.set.assert_not_called()

    @pytest.mark.no_firestore
    def test_returns_400_when_task_name_is_empty(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 400 when the task_name value is an empty string."""
        setup_user_doc(mock_firestore_client)

        response = client.post(
            URL_TASK_CURRENT,
            json={"task_name": "   "},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == "task name required"
        mock_firestore_client['user_profiles'].document.return_value.set.assert_not_called()

    @pytest.mark.no_firestore
    def test_returns_415_when_content_type_is_not_json(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 415 when the request is not sent as application/json.
        The content-type check fires before any Firestore access."""
        response = client.post(
            URL_TASK_CURRENT,
            data={"task_name": "Meditation"},
            headers=AUTH_HEADER
        )

        assert response.status_code == 415
        assert response.get_json()["error"] == "Content-Type must be application/json"
        mock_firestore_client['user_profiles'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_returns_400_when_json_body_is_empty(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 400 when the JSON body is an empty object.
        The body check fires before any Firestore access."""
        response = client.post(
            URL_TASK_CURRENT,
            json={},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 400
        mock_firestore_client['user_profiles'].document.assert_not_called()


# ---------------------------------------------------------------------------
# GET /session/latest
# ---------------------------------------------------------------------------

class TestGetLatestSession:

    def test_returns_200_with_latest_session_fields(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with all session fields from the most recent session document."""
        setup_sessions_stream(mock_firestore_client, [SESSION_DATA])

        response = client.get(URL_SESSION_LATEST, headers=AUTH_HEADER)

        assert response.status_code == 200
        data = response.get_json()
        assert data["task"] == "Meditation"
        assert data["elapsed_time"] == 300
        assert data["timestamp"] == "2024-06-15T10:00:00"
        assert data["task_color"] == "#ffaa00"
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['session_history'].document.assert_called_with(UID)
        mock_firestore_client['session_history'].document.return_value \
            .collection.assert_called_with("sessions")

    def test_returns_200_with_null_task_color_when_absent(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with task_color as None when the session has no task_color field."""
        session_without_color = {k: v for k, v in SESSION_DATA.items() if k != "task_color"}
        setup_sessions_stream(mock_firestore_client, [session_without_color])

        response = client.get(URL_SESSION_LATEST, headers=AUTH_HEADER)

        assert response.status_code == 200
        assert response.get_json()["task_color"] is None

    def test_returns_400_when_no_session_history_exists(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 400 when the sessions subcollection is empty."""
        setup_sessions_stream(mock_firestore_client, [])

        response = client.get(URL_SESSION_LATEST, headers=AUTH_HEADER)

        assert response.status_code == 400
        assert response.get_json()["error"] == "No recorded session history."
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['session_history'].document.assert_called_with(UID)


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------

class TestGetSessions:

    def test_returns_200_with_all_sessions_using_default_limit(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with all sessions using default limit=100 and offset=0."""
        sessions = [{"task": f"Task{i}", "elapsed_time": i * 60, "timestamp": f"2024-06-{i+1:02d}T10:00:00"} for i in range(3)]
        setup_sessions_stream(mock_firestore_client, sessions)

        response = client.get(URL_SESSIONS, headers=AUTH_HEADER)

        assert response.status_code == 200
        data = response.get_json()
        assert data["sessions"] == sessions
        assert data["total"] == 3
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['session_history'].document.assert_called_with(UID)

    def test_applies_custom_limit_to_firestore_query(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Passes limit + offset as the Firestore query limit."""
        sessions = [SESSION_DATA] * 5
        setup_sessions_stream(mock_firestore_client, sessions)

        client.get(f"{URL_SESSIONS}?limit=3", headers=AUTH_HEADER)

        mock_firestore_client['session_history'].document.return_value \
            .collection.return_value \
            .order_by.return_value \
            .limit.assert_called_once_with(3)  # limit=3, offset=0 → limit+offset=3

    def test_applies_offset_to_paginate_results(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Slices the returned list by offset so the correct page is returned."""
        sessions = [
            {"task": "A", "elapsed_time": 100, "timestamp": "2024-06-01T10:00:00"},
            {"task": "B", "elapsed_time": 200, "timestamp": "2024-06-02T10:00:00"},
            {"task": "C", "elapsed_time": 300, "timestamp": "2024-06-03T10:00:00"},
        ]
        setup_sessions_stream(mock_firestore_client, sessions)

        response = client.get(f"{URL_SESSIONS}?limit=2&offset=1", headers=AUTH_HEADER)

        assert response.status_code == 200
        data = response.get_json()
        assert data["sessions"] == sessions[1:]  # offset=1 skips first item
        assert data["total"] == 3

    def test_returns_empty_list_when_no_sessions_exist(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with an empty sessions list when the subcollection has no documents."""
        setup_sessions_stream(mock_firestore_client, [])

        response = client.get(URL_SESSIONS, headers=AUTH_HEADER)

        assert response.status_code == 200
        data = response.get_json()
        assert data["sessions"] == []
        assert data["total"] == 0


# ---------------------------------------------------------------------------
# GET /sessions/range
# ---------------------------------------------------------------------------

class TestGetSessionsRange:

    def test_returns_200_with_sessions_in_date_range(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with sessions falling within the given date range."""
        (
            mock_firestore_client['session_history']
            .document.return_value
            .collection.return_value
            .where.return_value
            .where.return_value
            .order_by.return_value
            .stream.return_value
        ) = [make_session_doc(SESSION_DATA)]

        response = client.get(
            f"{URL_SESSIONS_RANGE}?start=2024-06-01&end=2024-06-30",
            headers=AUTH_HEADER
        )

        assert response.status_code == 200
        assert response.get_json()["sessions"] == [SESSION_DATA]
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['session_history'].document.assert_called_with(UID)

    @pytest.mark.no_firestore
    def test_returns_200_with_empty_list_when_no_sessions_in_range(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with an empty list when no sessions fall in the date range."""
        (
            mock_firestore_client['session_history']
            .document.return_value
            .collection.return_value
            .where.return_value
            .where.return_value
            .order_by.return_value
            .stream.return_value
        ) = []

        response = client.get(
            f"{URL_SESSIONS_RANGE}?start=2024-06-01&end=2024-06-30",
            headers=AUTH_HEADER
        )

        assert response.status_code == 200
        assert response.get_json()["sessions"] == []

    @pytest.mark.no_firestore
    def test_returns_400_when_start_param_is_missing(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 400 when the start query parameter is absent."""
        setup_sessions_stream(mock_firestore_client, [])

        response = client.get(f"{URL_SESSIONS_RANGE}?end=2024-06-30", headers=AUTH_HEADER)

        assert response.status_code == 400
        assert response.get_json()["error"] == "start and end dates required (YYYY-MM-DD)"

    @pytest.mark.no_firestore
    def test_returns_400_when_end_param_is_missing(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 400 when the end query parameter is absent."""
        setup_sessions_stream(mock_firestore_client, [])

        response = client.get(f"{URL_SESSIONS_RANGE}?start=2024-06-01", headers=AUTH_HEADER)

        assert response.status_code == 400
        assert response.get_json()["error"] == "start and end dates required (YYYY-MM-DD)"

    @pytest.mark.no_firestore
    def test_returns_400_when_both_params_are_missing(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 400 when both start and end query parameters are absent."""
        setup_sessions_stream(mock_firestore_client, [])

        response = client.get(URL_SESSIONS_RANGE, headers=AUTH_HEADER)

        assert response.status_code == 400
        assert response.get_json()["error"] == "start and end dates required (YYYY-MM-DD)"


# ---------------------------------------------------------------------------
# GET /sessions/calendar
# ---------------------------------------------------------------------------

class TestGetSessionsCalendar:

    def test_returns_200_with_aggregated_daily_data(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with daily_data aggregated by date for the requested month."""
        sessions = [
            {"task": "Meditation", "elapsed_time": 300, "timestamp": "2024-06-15T10:00:00"},
            {"task": "Meditation", "elapsed_time": 600, "timestamp": "2024-06-15T14:00:00"},
            {"task": "Break",      "elapsed_time": 60,  "timestamp": "2024-06-20T09:00:00"},
        ]
        setup_sessions_stream(mock_firestore_client, sessions)

        response = client.get(
            f"{URL_SESSIONS_CAL}?year=2024&month=6",
            headers=AUTH_HEADER
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["year"] == 2024
        assert data["month"] == 6
        assert data["daily_data"]["2024-06-15"]["count"] == 2
        assert data["daily_data"]["2024-06-15"]["total_time"] == 900
        assert data["daily_data"]["2024-06-20"]["count"] == 1
        assert data["daily_data"]["2024-06-20"]["total_time"] == 60
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['session_history'].document.assert_called_with(UID)

    def test_excludes_sessions_outside_requested_month(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Filters out sessions that fall outside the requested year/month."""
        sessions = [
            {"task": "Meditation", "elapsed_time": 300, "timestamp": "2024-06-15T10:00:00"},
            {"task": "Break",      "elapsed_time": 60,  "timestamp": "2024-05-10T09:00:00"},  # wrong month
            {"task": "Study",      "elapsed_time": 900, "timestamp": "2023-06-15T08:00:00"},  # wrong year
        ]
        setup_sessions_stream(mock_firestore_client, sessions)

        response = client.get(
            f"{URL_SESSIONS_CAL}?year=2024&month=6",
            headers=AUTH_HEADER
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "2024-06-15" in data["daily_data"]
        assert "2024-05-10" not in data["daily_data"]
        assert "2023-06-15" not in data["daily_data"]

    def test_returns_empty_daily_data_when_no_sessions_in_month(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns empty daily_data and max_sessions of 1 when no sessions exist for the month."""
        setup_sessions_stream(mock_firestore_client, [])

        response = client.get(
            f"{URL_SESSIONS_CAL}?year=2024&month=6",
            headers=AUTH_HEADER
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["daily_data"] == {}
        assert data["max_sessions"] == 1

    def test_max_sessions_reflects_busiest_day(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """max_sessions equals the highest single-day session count in the month."""
        sessions = [
            {"task": "Meditation", "elapsed_time": 300, "timestamp": "2024-06-15T08:00:00"},
            {"task": "Meditation", "elapsed_time": 300, "timestamp": "2024-06-15T12:00:00"},
            {"task": "Meditation", "elapsed_time": 300, "timestamp": "2024-06-15T16:00:00"},
            {"task": "Break",      "elapsed_time": 60,  "timestamp": "2024-06-20T09:00:00"},
        ]
        setup_sessions_stream(mock_firestore_client, sessions)

        response = client.get(
            f"{URL_SESSIONS_CAL}?year=2024&month=6",
            headers=AUTH_HEADER
        )

        assert response.status_code == 200
        assert response.get_json()["max_sessions"] == 3

    def test_skips_sessions_with_malformed_timestamps(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Silently ignores sessions whose timestamp cannot be parsed."""
        sessions = [
            {"task": "Meditation", "elapsed_time": 300, "timestamp": "2024-06-15T10:00:00"},
            {"task": "Bad",        "elapsed_time": 100, "timestamp": "not-a-date"},
            {"task": "Also bad",   "elapsed_time": 100, "timestamp": ""},
        ]
        setup_sessions_stream(mock_firestore_client, sessions)

        response = client.get(
            f"{URL_SESSIONS_CAL}?year=2024&month=6",
            headers=AUTH_HEADER
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "2024-06-15" in data["daily_data"]
        assert len(data["daily_data"]) == 1

    def test_uses_default_year_and_month_when_not_provided(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Falls back to the current year and month when no query params are given."""
        setup_sessions_stream(mock_firestore_client, [])
        from datetime import datetime

        response = client.get(URL_SESSIONS_CAL, headers=AUTH_HEADER)

        assert response.status_code == 200
        data = response.get_json()
        assert data["year"] == datetime.now().year
        assert data["month"] == datetime.now().month