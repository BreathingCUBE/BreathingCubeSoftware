# test_api_profile.py
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UID = "test_user_123"

URL_PROFILE         = "http://localhost:5000/api/profile"
URL_USER_INFO       = "http://localhost:5000/api/profile/user_info"
URL_USER_INFO_ALL   = "http://localhost:5000/api/profile/user_info/all"
URL_USER_INFO_FIELD = lambda field: f"http://localhost:5000/api/profile/user_info/{field}"
URL_CUBE            = "http://localhost:5000/api/profile/cube"

# Bearer token value doesn't matter — verify_id_token is mocked by mock_firebase_auth
AUTH_HEADER = {"Authorization": "Bearer test-token"}

FULL_PROFILE = {
    "current_task": "Meditation",
    "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}},
    "user_info": {"email": "test@example.com", "first_name": "Johnny", "last_name": "Test", "role": "user"}
}
USER_INFO = {"email": "test@example.com", "first_name": "Johnny", "last_name": "Test", "role": "user"}


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


def setup_user_doc(mock_firestore_client, data=FULL_PROFILE, exists=True):
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
# JWT authentication guard tests (shared across all profile routes)
# ---------------------------------------------------------------------------

class TestProfileAuth:

    @pytest.mark.no_firestore
    def test_get_profile_returns_401_when_no_auth_header(self, client, repo, mock_firestore_client):
        """Returns 401 when GET /profile is called without an Authorization header."""
        response = client.get(URL_PROFILE)

        assert response.status_code == 401
        mock_firestore_client['user_profiles'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_get_profile_returns_401_when_token_is_invalid(self, client, repo, mock_firestore_client, monkeypatch):
        """Returns 401 when GET /profile is called with a token that fails verification."""
        monkeypatch.setattr(
            "firebase_admin.auth.verify_id_token",
            MagicMock(side_effect=Exception("invalid token"))
        )

        response = client.get(URL_PROFILE, headers=AUTH_HEADER)

        assert response.status_code == 401
        mock_firestore_client['user_profiles'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_put_user_info_returns_401_when_no_auth_header(self, client, repo, mock_firestore_client):
        """Returns 401 when PUT /profile/user_info is called without an Authorization header."""
        response = client.put(
            URL_USER_INFO,
            json={"first_name": "Jane"},
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 401
        mock_firestore_client['user_profiles'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_post_cube_returns_401_when_no_auth_header(self, client, repo, mock_firestore_client):
        """Returns 401 when POST /profile/cube is called without an Authorization header."""
        response = client.post(
            URL_CUBE,
            json={"cube_uuid": "cube-abc-123"},
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 401
        mock_firestore_client['user_profiles'].document.assert_not_called()
        mock_firestore_client['cubes'].document.assert_not_called()


# ---------------------------------------------------------------------------
# GET /profile
# ---------------------------------------------------------------------------

class TestGetProfile:

    def test_returns_200_with_full_profile(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with the complete profile dict for the authenticated user."""
        setup_user_doc(mock_firestore_client)

        response = client.get(URL_PROFILE, headers=AUTH_HEADER)

        assert response.status_code == 200
        assert response.get_json()["profile"] == FULL_PROFILE
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_200_with_none_when_doc_is_missing(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with a None profile when the user document does not exist."""
        setup_user_doc(mock_firestore_client, exists=False)

        response = client.get(URL_PROFILE, headers=AUTH_HEADER)

        assert response.status_code == 200
        assert response.get_json()["profile"] is None
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


# ---------------------------------------------------------------------------
# GET /profile/user_info/<field>
# ---------------------------------------------------------------------------

class TestGetUserInfo:

    def test_returns_200_with_all_user_info_when_field_is_all(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with the full user_info dict when the field parameter is 'all'."""
        setup_user_doc(mock_firestore_client, data={"user_info": USER_INFO})

        response = client.get(URL_USER_INFO_ALL, headers=AUTH_HEADER)

        assert response.status_code == 200
        assert response.get_json()["user_info"] == USER_INFO
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_404_when_all_user_info_is_missing_from_doc(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 404 when requesting 'all' but the document has no user_info field."""
        setup_user_doc(mock_firestore_client, data={})

        response = client.get(URL_USER_INFO_ALL, headers=AUTH_HEADER)

        assert response.status_code == 404
        assert response.get_json()["error"] == "No information added."
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_404_when_all_user_info_doc_does_not_exist(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 404 when requesting 'all' but the user document is missing entirely."""
        setup_user_doc(mock_firestore_client, exists=False)

        response = client.get(URL_USER_INFO_ALL, headers=AUTH_HEADER)

        assert response.status_code == 404
        assert response.get_json()["error"] == "No information added."
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_200_with_specific_field_value(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 with the value of the requested field when it exists in user_info."""
        setup_user_doc(mock_firestore_client, data={"user_info": USER_INFO})

        response = client.get(URL_USER_INFO_FIELD("email"), headers=AUTH_HEADER)

        assert response.status_code == 200
        assert response.get_json()["email"] == "test@example.com"
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_404_when_specific_field_does_not_exist_in_user_info(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 404 when the requested field is absent from user_info."""
        setup_user_doc(mock_firestore_client, data={"user_info": {"first_name": "Johnny"}})

        response = client.get(URL_USER_INFO_FIELD("email"), headers=AUTH_HEADER)

        assert response.status_code == 404
        assert response.get_json()["error"] == "No information added."
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_404_when_user_info_field_absent_from_doc(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 404 when the document exists but has no user_info field at all."""
        setup_user_doc(mock_firestore_client, data={})

        response = client.get(URL_USER_INFO_FIELD("email"), headers=AUTH_HEADER)

        assert response.status_code == 404
        assert response.get_json()["error"] == "No information added."
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_404_when_doc_does_not_exist(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 404 when the user document is missing entirely."""
        setup_user_doc(mock_firestore_client, exists=False)

        response = client.get(URL_USER_INFO_FIELD("email"), headers=AUTH_HEADER)

        assert response.status_code == 404
        assert response.get_json()["error"] == "No information added."
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


# ---------------------------------------------------------------------------
# PUT /profile/user_info
# ---------------------------------------------------------------------------

class TestUpdateUserInfo:

    def test_returns_200_and_saves_first_name(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 and persists a normalised first_name to user_profiles."""
        setup_user_doc(mock_firestore_client, data={"user_info": {**USER_INFO, "first_name": "Jane"}})

        response = client.put(
            URL_USER_INFO,
            json={"first_name": "jane"},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 200
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.set.assert_called_once_with(
            {"user_info": {"first_name": "Jane"}}, merge=True
        )

    def test_returns_200_and_saves_last_name(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 and persists a normalised last_name to user_profiles."""
        setup_user_doc(mock_firestore_client, data={"user_info": {**USER_INFO, "last_name": "Doe"}})

        response = client.put(
            URL_USER_INFO,
            json={"last_name": "doe"},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 200
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.set.assert_called_once_with(
            {"user_info": {"last_name": "Doe"}}, merge=True
        )

    def test_returns_200_and_saves_both_names(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 and persists both names when both are provided."""
        setup_user_doc(mock_firestore_client, data={"user_info": {**USER_INFO, "first_name": "Jane", "last_name": "Doe"}})

        response = client.put(
            URL_USER_INFO,
            json={"first_name": "jane", "last_name": "doe"},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 200
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['user_profiles'].document.assert_called_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.set.assert_called_once_with(
            {"user_info": {"first_name": "Jane", "last_name": "Doe"}}, merge=True
        )

    def test_returns_200_with_updated_user_info_in_response(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns the updated user_info dict read back from Firestore in the response body."""
        updated_info = {**USER_INFO, "first_name": "Jane"}
        setup_user_doc(mock_firestore_client, data={"user_info": updated_info})

        response = client.put(
            URL_USER_INFO,
            json={"first_name": "jane"},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 200
        assert response.get_json()["user_info"] == updated_info
        mock_firebase_auth.assert_called_once_with("test-token")

    def test_title_cases_and_strips_first_name_before_saving(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Strips surrounding whitespace and title-cases first_name before writing to Firestore."""
        setup_user_doc(mock_firestore_client, data={"user_info": USER_INFO})

        client.put(
            URL_USER_INFO,
            json={"first_name": "  jOhN  "},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        saved = mock_firestore_client['user_profiles'].document.return_value.set.call_args[0][0]
        assert saved["user_info"]["first_name"] == "John"

    def test_title_cases_and_strips_last_name_before_saving(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Strips surrounding whitespace and title-cases last_name before writing to Firestore."""
        setup_user_doc(mock_firestore_client, data={"user_info": USER_INFO})

        client.put(
            URL_USER_INFO,
            json={"last_name": "  sMiTh  "},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        saved = mock_firestore_client['user_profiles'].document.return_value.set.call_args[0][0]
        assert saved["user_info"]["last_name"] == "Smith"

    def test_saves_empty_string_when_first_name_is_explicitly_empty(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Saves an empty string for first_name when an empty string is explicitly provided."""
        setup_user_doc(mock_firestore_client, data={"user_info": USER_INFO})

        client.put(
            URL_USER_INFO,
            json={"first_name": ""},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        saved = mock_firestore_client['user_profiles'].document.return_value.set.call_args[0][0]
        assert saved["user_info"]["first_name"] == ""

    @pytest.mark.no_firestore
    def test_returns_415_when_content_type_is_not_json(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 415 when the request body is not sent as application/json.
        The content-type check fires before any Firestore access."""
        response = client.put(URL_USER_INFO, data={"first_name": "Jane"}, headers=AUTH_HEADER)

        assert response.status_code == 415
        assert response.get_json()["error"] == "Content-Type must be application/json"
        mock_firestore_client['user_profiles'].document.return_value.set.assert_not_called()

    @pytest.mark.no_firestore
    def test_returns_400_when_json_body_is_empty(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 400 when the JSON body is an empty object.
        The body check fires before any Firestore access."""
        response = client.put(
            URL_USER_INFO,
            json={},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == "Invalid JSON"
        mock_firestore_client['user_profiles'].document.return_value.set.assert_not_called()


# ---------------------------------------------------------------------------
# POST /profile/cube
# ---------------------------------------------------------------------------

class TestSaveCube:

    def test_returns_200_and_saves_cube_uuid(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 200 and registers the cube UUID against the authenticated user."""
        setup_user_doc(mock_firestore_client)

        response = client.post(
            URL_CUBE,
            json={"cube_uuid": "cube-abc-123"},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 200
        assert response.get_json()["cube_uuid"] == "cube-abc-123"
        mock_firebase_auth.assert_called_once_with("test-token")
        mock_firestore_client['cubes'].document.assert_called_with("cube-abc-123")
        mock_firestore_client['cubes'].document.return_value.set.assert_called_once_with(
            {"user uid": UID}, merge=True
        )

    @pytest.mark.no_firestore
    def test_returns_400_when_cube_uuid_is_absent_from_body(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 400 when the JSON body contains no cube_uuid field.
        The missing-field check fires before any Firestore access."""
        response = client.post(
            URL_CUBE,
            json={"other_field": "value"},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == "Cube uuid required"
        mock_firestore_client['cubes'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_returns_415_when_content_type_is_not_json(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 415 when the request body is not sent as application/json.
        The content-type check fires before any Firestore access."""
        response = client.post(URL_CUBE, data={"cube_uuid": "cube-abc-123"}, headers=AUTH_HEADER)

        assert response.status_code == 415
        assert response.get_json()["error"] == "Content-Type must be application/json"
        mock_firestore_client['cubes'].document.assert_not_called()

    @pytest.mark.no_firestore
    def test_returns_400_when_json_body_is_empty(self, client, repo, mock_firestore_client, mock_firebase_auth):
        """Returns 400 when the JSON body is an empty object.
        The body check fires before any Firestore access."""
        response = client.post(
            URL_CUBE,
            json={},
            headers={**AUTH_HEADER, "Content-Type": "application/json"}
        )

        assert response.status_code == 400
        assert response.get_json()["error"] == "Invalid JSON"
        mock_firestore_client['cubes'].document.assert_not_called()