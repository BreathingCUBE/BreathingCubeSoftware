# conftest.py
import pytest
from unittest.mock import MagicMock, patch
import importlib

# Patch Firebase to prevent file access and initialization during import
patch('firebase_admin.credentials.Certificate').start()
patch('firebase_admin.initialize_app').start()
patch('firebase_admin.firestore.client').start()


@pytest.fixture
def mock_firestore_client():
    """Mock Firestore client that tracks all operations."""
    with patch('firebase_admin.firestore.client') as mock_db:
        # Create mock collections
        mock_user_profiles = MagicMock()
        mock_cubes = MagicMock()
        mock_session_history = MagicMock()

        # Set up the db to return mock collections
        mock_db.return_value.collection.side_effect = lambda name: {
            'user_profiles': mock_user_profiles,
            'cubes': mock_cubes,
            'session_history': mock_session_history
        }.get(name, MagicMock())

        yield {
            'db': mock_db,
            'user_profiles': mock_user_profiles,
            'cubes': mock_cubes,
            'session_history': mock_session_history
        }


@pytest.fixture
def mock_firebase_init():
    """Mock Firebase initialization."""
    with patch('firebase_admin.initialize_app'):
        yield


@pytest.fixture
def client(mock_firebase_init, mock_firestore_client, monkeypatch):
    """Flask test client fixture with TESTING enabled."""
    monkeypatch.setenv("CUBE_API_KEY", "test-key")
    monkeypatch.setenv("APP_TYPE", "api")

    app_module = importlib.import_module("run")
    app = app_module.create_app()
    app.config.update(TESTING=True)

    app.timer = MagicMock(name="mock_timer")

    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def mock_firebase_auth(monkeypatch):
    """Patch JWT verification to return a known test uid by default."""
    verify_mock = MagicMock(return_value={"uid": "test_user_123"})
    monkeypatch.setattr("firebase_admin.auth.verify_id_token", verify_mock)
    return verify_mock


@pytest.fixture
def repo(mock_firestore_client):
    """Reload repository module and patch repo-level Firestore refs."""
    import src.server.utils.repository
    module = importlib.reload(src.server.utils.repository)

    module.user_profiles = mock_firestore_client['user_profiles']
    module.cubes = mock_firestore_client['cubes']
    module.session_history = mock_firestore_client['session_history']

    return module
