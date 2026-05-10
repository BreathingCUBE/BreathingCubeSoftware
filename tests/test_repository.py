# test_repository.py
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UID = "test_uid"
CUBE_UUID = "test_cube_uuid"


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


def get_sessions_chain(mock_session_history):
    """
    Terminal mock for get_sessions / get_session queries.
    Chain: document → collection → order_by → limit → stream
    """
    return (
        mock_session_history
        .document.return_value
        .collection.return_value
        .order_by.return_value
        .limit.return_value
    )


def get_date_range_chain(mock_session_history):
    """
    Terminal mock for get_sessions_by_date_range queries.
    Chain: document → collection → where → where → order_by → stream
    """
    return (
        mock_session_history
        .document.return_value
        .collection.return_value
        .where.return_value
        .where.return_value
        .order_by.return_value
    )


# ---------------------------------------------------------------------------
# Guard fixture — enforces that every test actually hit a mock collection
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def assert_mock_firestore_was_used(mock_firestore_client):
    """
    After each test, assert that at least one mocked Firestore collection was
    called. This catches tests that accidentally bypass the mock and hit a real
    (or no) Firestore client instead.
    """
    yield
    mocks = {
        'user_profiles': mock_firestore_client['user_profiles'],
        'cubes':          mock_firestore_client['cubes'],
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
# get_user_info
# ---------------------------------------------------------------------------

class TestGetUserInfo:

    def test_returns_requested_field_when_doc_exists(self, mock_firestore_client, repo):
        """Returns the value of the requested field from user_info."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({
            "user_info": {"email": "test_email@gmail.com", "first_name": "Johnny", "last_name": "Test", "role": "user"}
        })

        result = repo.get_user_info(UID, "email")

        assert result == "test_email@gmail.com"
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_doc_does_not_exist(self, mock_firestore_client, repo):
        """Returns None when the user document is missing."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_missing_doc()

        result = repo.get_user_info(UID, "email")

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_user_info_field_is_absent(self, mock_firestore_client, repo):
        """Returns None when the document has no user_info field."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({})

        result = repo.get_user_info(UID, "email")

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_requested_field_is_absent(self, mock_firestore_client, repo):
        """Returns None when user_info exists but the requested field does not."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({
            "user_info": {"first_name": "Johnny", "last_name": "Test", "role": "user"}
        })

        result = repo.get_user_info(UID, "email")

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


# ---------------------------------------------------------------------------
# get_all_user_info
# ---------------------------------------------------------------------------

class TestGetAllUserInfo:

    def test_returns_full_user_info_dict_when_doc_exists(self, mock_firestore_client, repo):
        """Returns the entire user_info dict when the document exists."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({
            "user_info": {"email": "test_email@gmail.com", "first_name": "Johnny", "last_name": "Test", "role": "user"}
        })

        result = repo.get_all_user_info(UID)

        assert result == {"email": "test_email@gmail.com", "first_name": "Johnny", "last_name": "Test", "role": "user"}
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_doc_does_not_exist(self, mock_firestore_client, repo):
        """Returns None when the user document is missing."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_missing_doc()

        result = repo.get_all_user_info(UID)

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_user_info_field_is_absent(self, mock_firestore_client, repo):
        """Returns None when the document has no user_info field."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({})

        result = repo.get_all_user_info(UID)

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


# ---------------------------------------------------------------------------
# get_cube_user
# ---------------------------------------------------------------------------

class TestGetCubeUser:

    def test_returns_uid_when_cube_doc_exists(self, mock_firestore_client, repo):
        """Returns the associated user uid when the cube document exists."""
        mock_firestore_client['cubes'].document.return_value.get.return_value = make_mock_doc({
            "user uid": "test_user_uid"
        })

        result = repo.get_cube_user(CUBE_UUID)

        assert result == "test_user_uid"
        mock_firestore_client['cubes'].document.assert_called_once_with(CUBE_UUID)
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()

    def test_returns_none_when_cube_doc_does_not_exist(self, mock_firestore_client, repo):
        """Returns None when no cube document exists for the given UUID."""
        mock_firestore_client['cubes'].document.return_value.get.return_value = make_missing_doc()

        result = repo.get_cube_user(CUBE_UUID)

        assert result is None
        mock_firestore_client['cubes'].document.assert_called_once_with(CUBE_UUID)
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()

    def test_returns_none_when_user_uid_field_is_absent(self, mock_firestore_client, repo):
        """Returns None when the cube document has no 'user uid' field."""
        mock_firestore_client['cubes'].document.return_value.get.return_value = make_mock_doc({})

        result = repo.get_cube_user(CUBE_UUID)

        assert result is None
        mock_firestore_client['cubes'].document.assert_called_once_with(CUBE_UUID)
        mock_firestore_client['cubes'].document.return_value.get.assert_called_once()


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------

class TestGetProfile:

    def test_returns_full_profile_when_doc_exists(self, mock_firestore_client, repo):
        """Returns the complete profile dict when the document exists."""
        profile = {
            "current_task": "Meditation",
            "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}},
            "session_history": [{"elapsed_time": 300, "task": "Meditation", "timestamp": "2023-01-01T00:00:00"}],
            "user_info": {"email": "test_email@gmail.com", "first_name": "Johnny", "last_name": "Test", "role": "user"}
        }
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc(profile)

        result = repo.get_profile(UID)

        assert result == profile
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_doc_does_not_exist(self, mock_firestore_client, repo):
        """Returns None when the user document is missing."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_missing_doc()

        result = repo.get_profile(UID)

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


# ---------------------------------------------------------------------------
# get_task_preset
# ---------------------------------------------------------------------------

class TestGetTaskPreset:

    def test_returns_preset_when_doc_and_preset_exist(self, mock_firestore_client, repo):
        """Returns the specific preset dict when both the doc and preset exist."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({
            "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
        })

        result = repo.get_task_preset(UID, "Meditation")

        assert result == {"task_color": "#ffaa00", "task_time": 600}
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_doc_does_not_exist(self, mock_firestore_client, repo):
        """Returns None when the user document is missing."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_missing_doc()

        result = repo.get_task_preset(UID, "Meditation")

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_presets_field_is_absent(self, mock_firestore_client, repo):
        """Returns None when the document has no presets field."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({})

        result = repo.get_task_preset(UID, "Meditation")

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_specific_preset_does_not_exist(self, mock_firestore_client, repo):
        """Returns None when the preset name is not found within presets."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({
            "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
        })

        result = repo.get_task_preset(UID, "NonExistentTask")

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


# ---------------------------------------------------------------------------
# get_all_task_presets
# ---------------------------------------------------------------------------

class TestGetAllTaskPresets:

    def test_returns_all_presets_when_doc_exists(self, mock_firestore_client, repo):
        """Returns the full presets dict when the document exists."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({
            "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
        })

        result = repo.get_all_task_presets(UID)

        assert result == {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_doc_does_not_exist(self, mock_firestore_client, repo):
        """Returns None when the user document is missing."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_missing_doc()

        result = repo.get_all_task_presets(UID)

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_presets_field_is_absent(self, mock_firestore_client, repo):
        """Returns None when the document has no presets field."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({})

        result = repo.get_all_task_presets(UID)

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


# ---------------------------------------------------------------------------
# get_current_task
# ---------------------------------------------------------------------------

class TestGetCurrentTask:

    def test_returns_current_task_when_doc_exists(self, mock_firestore_client, repo):
        """Returns the current task name when the document exists."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({
            "current_task": "Meditation"
        })

        result = repo.get_current_task(UID)

        assert result == "Meditation"
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_doc_does_not_exist(self, mock_firestore_client, repo):
        """Returns None when the user document is missing."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_missing_doc()

        result = repo.get_current_task(UID)

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()

    def test_returns_none_when_current_task_field_is_absent(self, mock_firestore_client, repo):
        """Returns None when the document has no current_task field."""
        mock_firestore_client['user_profiles'].document.return_value.get.return_value = make_mock_doc({})

        result = repo.get_current_task(UID)

        assert result is None
        mock_firestore_client['user_profiles'].document.assert_called_once_with(UID)
        mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------

class TestGetSession:

    def test_returns_most_recent_session(self, mock_firestore_client, repo):
        """Returns the first session document from the subcollection."""
        session = {"task": "Meditation", "elapsed_time": 300, "timestamp": "2023-01-01T00:00:00"}
        get_sessions_chain(mock_firestore_client['session_history']).stream.return_value = [
            make_mock_doc(session)
        ]

        result = repo.get_session(UID)

        assert result == session
        mock_firestore_client['session_history'].document.assert_called_once_with(UID)
        mock_firestore_client['session_history'].document.return_value.collection.assert_called_once_with("sessions")

    def test_returns_none_when_no_sessions_exist(self, mock_firestore_client, repo):
        """Returns None when the sessions subcollection is empty."""
        get_sessions_chain(mock_firestore_client['session_history']).stream.return_value = []

        result = repo.get_session(UID)

        assert result is None
        mock_firestore_client['session_history'].document.assert_called_once_with(UID)

    def test_requests_only_one_document_from_firestore(self, mock_firestore_client, repo):
        """Delegates to get_sessions with limit=1 to avoid over-fetching."""
        mock_sh = mock_firestore_client['session_history']
        get_sessions_chain(mock_sh).stream.return_value = []

        repo.get_session(UID)

        mock_sh.document.return_value.collection.return_value \
            .order_by.return_value.limit.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# get_sessions
# ---------------------------------------------------------------------------

class TestGetSessions:

    def test_returns_list_of_session_dicts(self, mock_firestore_client, repo):
        """Returns a list of dicts from the streamed subcollection docs."""
        session_a = {"task": "Meditation", "elapsed_time": 300, "timestamp": "2024-06-01T10:00:00"}
        session_b = {"task": "Break",      "elapsed_time": 60,  "timestamp": "2024-06-01T09:00:00"}
        get_sessions_chain(mock_firestore_client['session_history']).stream.return_value = [
            make_mock_doc(session_a), make_mock_doc(session_b)
        ]

        result = repo.get_sessions(UID)

        assert result == [session_a, session_b]
        mock_firestore_client['session_history'].document.assert_called_once_with(UID)
        mock_firestore_client['session_history'].document.return_value.collection.assert_called_once_with("sessions")

    def test_returns_empty_list_when_no_sessions_exist(self, mock_firestore_client, repo):
        """Returns an empty list when the sessions subcollection has no documents."""
        get_sessions_chain(mock_firestore_client['session_history']).stream.return_value = []

        result = repo.get_sessions(UID)

        assert result == []
        mock_firestore_client['session_history'].document.assert_called_once_with(UID)

    def test_orders_results_by_timestamp_descending(self, mock_firestore_client, repo):
        """Passes DESCENDING order_by to Firestore on the timestamp field."""
        mock_sh = mock_firestore_client['session_history']
        get_sessions_chain(mock_sh).stream.return_value = []

        repo.get_sessions(UID)

        mock_sh.document.return_value.collection.return_value \
            .order_by.assert_called_once_with("timestamp", direction="DESCENDING")

    def test_applies_default_limit_of_100(self, mock_firestore_client, repo):
        """Uses a limit of 100 when no limit is specified."""
        mock_sh = mock_firestore_client['session_history']
        get_sessions_chain(mock_sh).stream.return_value = []

        repo.get_sessions(UID)

        mock_sh.document.return_value.collection.return_value \
            .order_by.return_value.limit.assert_called_once_with(100)

    def test_applies_custom_limit(self, mock_firestore_client, repo):
        """Passes the caller-supplied limit value to Firestore."""
        mock_sh = mock_firestore_client['session_history']
        get_sessions_chain(mock_sh).stream.return_value = []

        repo.get_sessions(UID, limit=5)

        mock_sh.document.return_value.collection.return_value \
            .order_by.return_value.limit.assert_called_once_with(5)

    def test_calls_to_dict_on_every_document(self, mock_firestore_client, repo):
        """Calls .to_dict() on each streamed document to build the result list."""
        docs = [make_mock_doc({"task": "Meditation", "elapsed_time": i}) for i in range(3)]
        get_sessions_chain(mock_firestore_client['session_history']).stream.return_value = docs

        repo.get_sessions(UID)

        for doc in docs:
            doc.to_dict.assert_called_once()


# ---------------------------------------------------------------------------
# get_sessions_by_date_range
# ---------------------------------------------------------------------------

class TestGetSessionsByDateRange:

    def test_returns_sessions_within_date_range(self, mock_firestore_client, repo):
        """Returns session dicts falling within the given date range."""
        session = {"task": "Meditation", "elapsed_time": 300, "timestamp": "2024-06-15T10:00:00"}
        get_date_range_chain(mock_firestore_client['session_history']).stream.return_value = [
            make_mock_doc(session)
        ]

        result = repo.get_sessions_by_date_range(UID, "2024-06-01", "2024-06-30")

        assert result == [session]
        mock_firestore_client['session_history'].document.assert_called_once_with(UID)
        mock_firestore_client['session_history'].document.return_value.collection.assert_called_once_with("sessions")

    def test_returns_empty_list_when_no_sessions_in_range(self, mock_firestore_client, repo):
        """Returns an empty list when no sessions fall in the date range."""
        get_date_range_chain(mock_firestore_client['session_history']).stream.return_value = []

        result = repo.get_sessions_by_date_range(UID, "2024-06-01", "2024-06-30")

        assert result == []
        mock_firestore_client['session_history'].document.assert_called_once_with(UID)

    def test_builds_correct_iso_bounds_for_where_clauses(self, mock_firestore_client, repo):
        """Constructs start-of-day and end-of-day ISO timestamps for the where filters."""
        mock_sh = mock_firestore_client['session_history']
        get_date_range_chain(mock_sh).stream.return_value = []
        sessions_col = mock_sh.document.return_value.collection.return_value

        repo.get_sessions_by_date_range(UID, "2024-06-01", "2024-06-30")

        sessions_col.where.assert_called_once_with("timestamp", ">=", "2024-06-01T00:00:00")
        sessions_col.where.return_value.where.assert_called_once_with("timestamp", "<=", "2024-06-30T23:59:59")

    def test_orders_results_by_timestamp_descending(self, mock_firestore_client, repo):
        """Passes DESCENDING order_by to Firestore after the where filters."""
        mock_sh = mock_firestore_client['session_history']
        get_date_range_chain(mock_sh).stream.return_value = []

        repo.get_sessions_by_date_range(UID, "2024-06-01", "2024-06-30")

        mock_sh.document.return_value.collection.return_value \
            .where.return_value.where.return_value \
            .order_by.assert_called_once_with("timestamp", direction="DESCENDING")

    def test_single_day_range_uses_correct_start_and_end_bounds(self, mock_firestore_client, repo):
        """When start and end are the same date, bounds span that entire day."""
        mock_sh = mock_firestore_client['session_history']
        get_date_range_chain(mock_sh).stream.return_value = []
        sessions_col = mock_sh.document.return_value.collection.return_value

        repo.get_sessions_by_date_range(UID, "2024-03-15", "2024-03-15")

        sessions_col.where.assert_called_once_with("timestamp", ">=", "2024-03-15T00:00:00")
        sessions_col.where.return_value.where.assert_called_once_with("timestamp", "<=", "2024-03-15T23:59:59")


# ---------------------------------------------------------------------------
# save_session
# ---------------------------------------------------------------------------

class TestSaveSession:

    def test_calls_add_on_sessions_subcollection(self, mock_firestore_client, repo):
        """Writes to session_history/{uid}/sessions via .add()."""
        mock_sh = mock_firestore_client['session_history']

        repo.save_session(UID, "Meditation", 300)

        mock_sh.document.assert_called_once_with(UID)
        mock_sh.document.return_value.collection.assert_called_once_with("sessions")
        mock_sh.document.return_value.collection.return_value.add.assert_called_once()

    def test_saved_document_contains_required_fields(self, mock_firestore_client, repo):
        """The document passed to .add() contains task, elapsed_time, and timestamp."""
        mock_sh = mock_firestore_client['session_history']

        repo.save_session(UID, "Meditation", 300)

        saved = mock_sh.document.return_value.collection.return_value.add.call_args[0][0]
        assert saved["task"] == "Meditation"
        assert saved["elapsed_time"] == 300
        assert "timestamp" in saved

    def test_timestamp_is_a_valid_utc_iso_string(self, mock_firestore_client, repo):
        """The timestamp recorded falls between before and after the call."""
        mock_sh = mock_firestore_client['session_history']

        before = datetime.now(timezone.utc).isoformat()
        repo.save_session(UID, "Meditation", 300)
        after = datetime.now(timezone.utc).isoformat()

        saved = mock_sh.document.return_value.collection.return_value.add.call_args[0][0]
        assert before <= saved["timestamp"] <= after

    def test_task_color_included_when_provided(self, mock_firestore_client, repo):
        """task_color is present in the saved document when passed as an argument."""
        mock_sh = mock_firestore_client['session_history']

        repo.save_session(UID, "Meditation", 300, task_color="#ffaa00")

        saved = mock_sh.document.return_value.collection.return_value.add.call_args[0][0]
        assert saved["task_color"] == "#ffaa00"

    def test_task_color_omitted_when_not_provided(self, mock_firestore_client, repo):
        """task_color is absent from the saved document when not passed."""
        mock_sh = mock_firestore_client['session_history']

        repo.save_session(UID, "Meditation", 300)

        saved = mock_sh.document.return_value.collection.return_value.add.call_args[0][0]
        assert "task_color" not in saved

    def test_task_color_omitted_when_explicitly_none(self, mock_firestore_client, repo):
        """task_color is absent from the saved document when explicitly passed as None."""
        mock_sh = mock_firestore_client['session_history']

        repo.save_session(UID, "Meditation", 300, task_color=None)

        saved = mock_sh.document.return_value.collection.return_value.add.call_args[0][0]
        assert "task_color" not in saved

    def test_zero_elapsed_time_is_saved(self, mock_firestore_client, repo):
        """An elapsed_time of 0 is stored correctly and not treated as falsy."""
        mock_sh = mock_firestore_client['session_history']

        repo.save_session(UID, "Meditation", 0)

        saved = mock_sh.document.return_value.collection.return_value.add.call_args[0][0]
        assert saved["elapsed_time"] == 0


# ---------------------------------------------------------------------------
# save_cube_uuid
# ---------------------------------------------------------------------------

class TestSaveCubeUuid:

    def test_writes_user_uid_to_cube_document(self, mock_firestore_client, repo):
        """Writes the user uid to the cube document using set with merge."""
        mock_doc = MagicMock()
        mock_firestore_client['cubes'].document.return_value = mock_doc

        repo.save_cube_uuid(UID, CUBE_UUID)

        mock_firestore_client['cubes'].document.assert_called_with(CUBE_UUID)
        mock_doc.set.assert_called_once_with({"user uid": UID}, merge=True)


# ---------------------------------------------------------------------------
# save_user_info
# ---------------------------------------------------------------------------

class TestSaveUserInfo:

    def test_writes_user_info_to_user_profile(self, mock_firestore_client, repo):
        """Calls set(merge=True) on the user profile document with the provided user_info."""
        mock_up = mock_firestore_client['user_profiles']

        repo.save_user_info(UID, {"email": "new@example.com"})

        mock_up.document.assert_called_with(UID)
        mock_up.document.return_value.set.assert_called_once_with(
            {"user_info": {"email": "new@example.com"}}, merge=True
        )


# ---------------------------------------------------------------------------
# update_task_preset
# ---------------------------------------------------------------------------

class TestUpdateTaskPreset:

    def test_writes_preset_to_user_profile(self, mock_firestore_client, repo):
        """Calls set(merge=True) on the user profile document with the full presets dict."""
        mock_up = mock_firestore_client['user_profiles']
        mock_up.document.return_value.get.return_value = make_mock_doc({
            "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
        })
        preset_data = {"task_color": "#ffbb00", "task_time": 900}

        repo.update_task_preset(UID, "Study", preset_data)

        mock_up.document.assert_called_with(UID)
        mock_up.document.return_value.set.assert_called_once_with(
            {"presets": {
                "Meditation": {"task_color": "#ffaa00", "task_time": 600},
                "Study": {"task_color": "#ffbb00", "task_time": 900},
            }},
            merge=True
        )

    def test_writes_first_preset_when_no_presets_exist(self, mock_firestore_client, repo):
        """Creates the presets dict from scratch when the document has no presets field."""
        mock_up = mock_firestore_client['user_profiles']
        mock_up.document.return_value.get.return_value = make_mock_doc({})
        preset_data = {"task_color": "#ffbb00", "task_time": 900}

        repo.update_task_preset(UID, "Meditation", preset_data)

        mock_up.document.assert_called_with(UID)
        mock_up.document.return_value.set.assert_called_once_with(
            {"presets": {"Meditation": {"task_color": "#ffbb00", "task_time": 900}}},
            merge=True
        )

    def test_writes_first_preset_when_doc_does_not_exist(self, mock_firestore_client, repo):
        """Creates the presets dict from scratch when the document is missing entirely."""
        mock_up = mock_firestore_client['user_profiles']
        mock_up.document.return_value.get.return_value = make_missing_doc()
        preset_data = {"task_color": "#ffbb00", "task_time": 900}

        repo.update_task_preset(UID, "Meditation", preset_data)

        mock_up.document.assert_called_with(UID)
        mock_up.document.return_value.set.assert_called_once_with(
            {"presets": {"Meditation": {"task_color": "#ffbb00", "task_time": 900}}},
            merge=True
        )


# ---------------------------------------------------------------------------
# delete_task_preset
# ---------------------------------------------------------------------------

class TestDeleteTaskPreset:

    def test_removes_preset_from_user_profile(self, mock_firestore_client, repo):
        """Calls update on the user profile document with DELETE_FIELD for the preset key."""
        from google.cloud.firestore import DELETE_FIELD
        mock_up = mock_firestore_client['user_profiles']

        repo.delete_task_preset(UID, "Meditation")

        mock_up.document.assert_called_with(UID)
        mock_up.document.return_value.update.assert_called_once_with(
            {"presets.Meditation": DELETE_FIELD}
        )


# ---------------------------------------------------------------------------
# set_current_task
# ---------------------------------------------------------------------------

class TestSetCurrentTask:

    def test_writes_current_task_to_user_profile(self, mock_firestore_client, repo):
        """Calls set(merge=True) on the user profile document with the new current task."""
        mock_up = mock_firestore_client['user_profiles']

        repo.set_current_task(UID, "Meditation")

        mock_up.document.assert_called_with(UID)
        mock_up.document.return_value.set.assert_called_once_with(
            {"current_task": "Meditation"}, merge=True
        )