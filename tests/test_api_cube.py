# test_api_cube.py
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

URL = "http://localhost:5000/api/task/control"
HEADERS = {"X-API-Key": "test-key"}
UID = "test_user_123"

CUBE_DOC = {"user uid": UID}
USER_DOC = {
    "current_task": "Meditation",
    "presets": {"Meditation": {"task_time": 600}}
}


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


def setup_cube_doc(mock_firestore_client, data=CUBE_DOC, exists=True):
    """Wire the cubes collection to return a document with the given data."""
    mock_firestore_client['cubes'].document.return_value.get.return_value = (
        make_mock_doc(data) if exists else make_missing_doc()
    )


def setup_user_doc(mock_firestore_client, data=USER_DOC, exists=True):
    """Wire the user_profiles collection to return a document with the given data."""
    mock_firestore_client['user_profiles'].document.return_value.get.return_value = (
        make_mock_doc(data) if exists else make_missing_doc()
    )


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
# API key / authentication guard tests
# ---------------------------------------------------------------------------

class TestTaskControlAuth:

    @pytest.mark.no_firestore
    def test_returns_500_when_server_api_key_not_configured(self, client, mock_firestore_client, monkeypatch):
        """Returns 500 when the server has no API key configured."""
        monkeypatch.setenv("CUBE_API_KEY", "")

        response = client.post(URL)

        assert response.status_code == 500
        assert response.get_json()["error"] == "API key not configured on server"
        mock_firestore_client['cubes'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_returns_401_when_api_key_header_is_missing(self, client, mock_firestore_client):
        """Returns 401 when the request carries no X-API-Key header."""
        response = client.post(URL)

        assert response.status_code == 401
        assert response.get_json()["error"] == "Missing X-API-Key header"
        mock_firestore_client['cubes'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_returns_401_when_api_key_is_wrong(self, client, mock_firestore_client, monkeypatch):
        """Returns 401 when the X-API-Key header value does not match the server key."""
        response = client.post(URL, headers={"X-API-Key": "wrong-key"})

        assert response.status_code == 401
        assert response.get_json()["error"] == "Unauthorized"
        mock_firestore_client['cubes'].document.assert_not_called()


# ---------------------------------------------------------------------------
# Cube registration and request validation tests
# ---------------------------------------------------------------------------

class TestTaskControlValidation:

    def test_returns_401_when_cube_is_not_registered(self, client, repo, mock_firestore_client):
        """Returns 401 when the cube UUID has no associated user account."""
        setup_cube_doc(mock_firestore_client, exists=False)

        response = client.post(URL, json={"action": "start"}, headers=HEADERS)

        assert response.status_code == 401
        assert response.get_json()["error"] == "Cube not registered with user account"
        mock_firestore_client['cubes'].document.assert_called_with('test-key')
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()
        mock_firestore_client['user_profiles'].document.assert_not_called()

    def test_returns_415_when_content_type_is_not_json(self, client, repo, mock_firestore_client):
        """Returns 415 when the request body is not sent as application/json."""
        setup_cube_doc(mock_firestore_client)

        response = client.post(URL, data={"action": "start"}, headers=HEADERS)

        assert response.status_code == 415
        assert response.get_json()["error"] == "Content-Type must be application/json"
        mock_firestore_client['cubes'].document.assert_called_with('test-key')
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()
        mock_firestore_client['user_profiles'].document.assert_not_called()

    def test_returns_400_when_json_body_is_empty(self, client, repo, mock_firestore_client):
        """Returns 400 when the JSON body is an empty object."""
        setup_cube_doc(mock_firestore_client)

        response = client.post(URL, json={}, headers=HEADERS)

        assert response.status_code == 400
        assert response.get_json()["error"] == "Invalid JSON"
        mock_firestore_client['cubes'].document.assert_called_with('test-key')
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()
        mock_firestore_client['user_profiles'].document.assert_not_called()

    def test_returns_400_when_no_current_task_is_set(self, client, repo, mock_firestore_client):
        """Returns 400 when the user has no current task configured."""
        setup_cube_doc(mock_firestore_client)
        setup_user_doc(mock_firestore_client, data={})

        response = client.post(URL, json={"action": "start"}, headers=HEADERS)

        assert response.status_code == 400
        assert response.get_json()["error"] == "Current task not set"
        mock_firestore_client['cubes'].document.assert_called_with('test-key')
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


# ---------------------------------------------------------------------------
# Start action tests
# ---------------------------------------------------------------------------

class TestTaskControlStart:

    def test_returns_200_and_starts_timer(self, client, repo, mock_firestore_client):
        """Returns 200 and starts the timer when action is start."""
        setup_cube_doc(mock_firestore_client)
        setup_user_doc(mock_firestore_client)

        response = client.post(URL, json={"action": "start"}, headers=HEADERS)

        assert response.status_code == 200
        assert response.get_json()["message"] == "Meditation task started"
        client.application.timer.start.assert_called_once()
        mock_firestore_client['cubes'].document.assert_called_with('test-key')
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        assert mock_firestore_client['user_profiles'].document.return_value.get.call_count == 2

    def test_does_not_save_session_on_start(self, client, repo, mock_firestore_client):
        """Does not write to session_history when action is start."""
        setup_cube_doc(mock_firestore_client)
        setup_user_doc(mock_firestore_client)

        client.post(URL, json={"action": "start"}, headers=HEADERS)

        mock_firestore_client['session_history'].document.return_value \
            .collection.return_value.add.assert_not_called()


# ---------------------------------------------------------------------------
# Stop action tests
# ---------------------------------------------------------------------------

class TestTaskControlStop:

    def test_returns_200_with_session_time_when_within_task_time(self, client, repo, mock_firestore_client):
        """Returns 200 with elapsed time message when stopped before task time expires."""
        setup_cube_doc(mock_firestore_client)
        setup_user_doc(mock_firestore_client)

        # Mock the elapsed time to an integer
        client.application.timer.get_elapsed.return_value = 300

        response = client.post(URL, json={"action": "stop", "elapsed_seconds": 300}, headers=HEADERS)

        assert response.status_code == 200
        assert response.get_json()["message"] == "Meditation task stopped. 5m:0s of session time logged."
        client.application.timer.stop.assert_called_once()
        mock_firestore_client['cubes'].document.assert_called_with('test-key')
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        assert mock_firestore_client['user_profiles'].document.return_value.get.call_count == 2

    def test_returns_400_with_invalid_task_time(self, client, repo, mock_firestore_client):
        """Returns 400 error due to invalid task time."""
        setup_cube_doc(mock_firestore_client)
        setup_user_doc(mock_firestore_client)

        # Mock the elapsed time to an integer
        client.application.timer.get_elapsed.return_value = 0

        response = client.post(URL, json={"action": "stop", "elapsed_seconds": 0}, headers=HEADERS)

        assert response.status_code == 400
        assert response.get_json()["error"] == "Elapsed time must be a positive non-zero integer."
        client.application.timer.stop.assert_called_once()
        mock_firestore_client['cubes'].document.assert_called_with('test-key')
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        assert mock_firestore_client['user_profiles'].document.return_value.get.call_count == 2

    def test_saves_session_to_subcollection_on_stop(self, client, repo, mock_firestore_client):
        """Writes a session document to session_history/{uid}/sessions on stop."""
        setup_cube_doc(mock_firestore_client)
        setup_user_doc(mock_firestore_client)

        # Mock the elapsed time to an integer
        client.application.timer.get_elapsed.return_value = 300

        client.post(URL, json={"action": "stop", "elapsed_seconds": 300}, headers=HEADERS)

        mock_firestore_client['session_history'].document.assert_called_with(UID)
        mock_firestore_client['session_history'].document.return_value \
            .collection.assert_called_with('sessions')
        mock_firestore_client['session_history'].document.return_value \
            .collection.return_value.add.assert_called_once()

    def test_returns_200_with_overtime_message_when_beyond_task_time(self, client, repo, mock_firestore_client):
        """Returns 200 with overtime breakdown message when elapsed exceeds task time."""
        setup_cube_doc(mock_firestore_client)
        setup_user_doc(mock_firestore_client)

        # Mock the elapsed time to an integer
        client.application.timer.get_elapsed.return_value = 900

        response = client.post(URL, json={"action": "stop", "elapsed_seconds": 900}, headers=HEADERS)

        assert response.status_code == 200
        assert response.get_json()["message"] == (
            "Meditation task stopped. 10m:0s of session time + 5m:0s of extra session time logged."
        )
        client.application.timer.stop.assert_called_once()
        mock_firestore_client['cubes'].document.assert_called_with('test-key')
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        assert mock_firestore_client['user_profiles'].document.return_value.get.call_count == 2

    def test_saves_session_to_subcollection_on_stop_with_overtime(self, client, repo, mock_firestore_client):
        """Writes a session document to session_history/{uid}/sessions even when overtime."""
        setup_cube_doc(mock_firestore_client)
        setup_user_doc(mock_firestore_client)

        # Mock the elapsed time to an integer
        client.application.timer.get_elapsed.return_value = 900

        client.post(URL, json={"action": "stop", "elapsed_seconds": 900}, headers=HEADERS)

        mock_firestore_client['session_history'].document.assert_called_with(UID)
        mock_firestore_client['session_history'].document.return_value \
            .collection.assert_called_with('sessions')
        mock_firestore_client['session_history'].document.return_value \
            .collection.return_value.add.assert_called_once()


# ---------------------------------------------------------------------------
# Reset action tests
# ---------------------------------------------------------------------------

class TestTaskControlReset:

    def test_returns_200_with_task_info_and_resets_timer(self, client, repo, mock_firestore_client):
        """Returns 200 with task details and resets the timer when action is reset."""
        setup_cube_doc(mock_firestore_client)
        setup_user_doc(mock_firestore_client)

        response = client.post(URL, json={"action": "reset"}, headers=HEADERS)

        assert response.status_code == 200
        data = response.get_json()
        assert data["message"] == "Meditation task reset"
        assert data["task_name"] == "Meditation"
        assert data["task_time"] == 600
        client.application.timer.reset.assert_called_once()
        mock_firestore_client['cubes'].document.assert_called_with('test-key')
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        assert mock_firestore_client['user_profiles'].document.return_value.get.call_count == 2

    def test_does_not_save_session_on_reset(self, client, repo, mock_firestore_client):
        """Does not write to session_history when action is reset."""
        setup_cube_doc(mock_firestore_client)
        setup_user_doc(mock_firestore_client)

        client.post(URL, json={"action": "reset"}, headers=HEADERS)

        mock_firestore_client['session_history'].document.return_value \
            .collection.return_value.add.assert_not_called()