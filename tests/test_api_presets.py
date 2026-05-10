from unittest.mock import MagicMock


def test_api_get_preset_no_auth(client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset/meditation"

    # Act
    response = client.get(url)

    # Assert
    assert response.status_code == 401
    data = response.get_json()
    assert "error" in data


def test_api_get_preset_no_task_name_in_route(client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"

    # Act
    response = client.get(url)

    # Assert
    assert response.status_code == 405


def test_api_get_preset_bad_token_format(client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset/meditation"
    headers = {'Authorization': 'NotBearer xyz'}

    # Act
    response = client.get(url, headers=headers)

    # Assert
    assert response.status_code == 401


def test_api_get_preset_invalid_token(client, mock_firebase_auth):
    # Arrange
    url = "http://localhost:5000/api/profile/preset/meditation"
    headers = {"Authorization": "Bearer invalid_jwt_token"}
    mock_firebase_auth.side_effect = Exception("Invalid token")

    # Act
    response = client.get(url, headers=headers)

    # Assert
    assert response.status_code == 401
    mock_firebase_auth.assert_called_once()


def test_api_get_preset_no_presets(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset/all"
    headers = {"Authorization": "Bearer valid_jwt_token"}

    # Mock user profile document without presets
    mock_user_doc = MagicMock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {}  # No presets
    mock_firestore_client['user_profiles'].document.return_value.get.return_value = mock_user_doc

    # Act
    response = client.get(url, headers=headers)

    # Assert
    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "No presets configured."
    mock_firebase_auth.assert_called_once()


def test_api_get_preset_get_all_success(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset/all"
    headers = {"Authorization": "Bearer valid_jwt_token"}

    # Mock user profile document with presets
    mock_user_doc = MagicMock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {
        "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
    }
    mock_firestore_client['user_profiles'].document.return_value.get.return_value = mock_user_doc

    # Act
    response = client.get(url, headers=headers)

    # Assert
    assert response.status_code == 200
    data = response.get_json()
    assert data["presets"] == {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
    mock_firebase_auth.assert_called_once()
    mock_firestore_client['user_profiles'].document.assert_called_once_with('test_user_123')
    mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


def test_api_get_preset_not_found(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset/bad_test"
    headers = {"Authorization": "Bearer valid_jwt_token"}

    # Mock user profile document with presets but not "bad_test"
    mock_user_doc = MagicMock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {
        "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
    }
    mock_firestore_client['user_profiles'].document.return_value.get.return_value = mock_user_doc

    # Act
    response = client.get(url, headers=headers)

    # Assert
    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "Preset not found"
    mock_firebase_auth.assert_called_once()
    mock_firestore_client['user_profiles'].document.assert_called_once_with('test_user_123')
    mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


def test_api_get_preset_success(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset/meditation"
    headers = {"Authorization": "Bearer valid_jwt_token"}

    # Mock user profile document with presets
    mock_user_doc = MagicMock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {
        "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
    }
    mock_firestore_client['user_profiles'].document.return_value.get.return_value = mock_user_doc

    # Act
    response = client.get(url, headers=headers)

    # Assert
    assert response.status_code == 200
    data = response.get_json()
    assert data["Meditation"] == {"task_color": "#ffaa00", "task_time": 600}
    mock_firebase_auth.assert_called_once()
    
    # Verify Firestore interactions
    mock_firestore_client['user_profiles'].document.assert_called_with('test_user_123')
    mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()


def test_api_create_preset_no_task_name(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"
    headers = {"Authorization": "Bearer valid_jwt_token"}
    payload = {"task_color": "#ffaa00"}

    # Act
    response = client.post(url, json=payload, headers=headers)

    # Assert
    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "task name required"
    mock_firebase_auth.assert_called_once()
    mock_firestore_client['user_profiles'].document.assert_not_called()


def test_api_create_preset_no_task_time(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"
    headers = {"Authorization": "Bearer valid_jwt_token"}
    payload = {"task_name": "study"}

    # Act
    response = client.post(url, json=payload, headers=headers)

    # Assert
    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "task time required"
    mock_firebase_auth.assert_called_once()
    mock_firestore_client['user_profiles'].document.assert_not_called()


def test_api_create_preset_no_task_time(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"
    headers = {"Authorization": "Bearer valid_jwt_token"}
    payload = {"task_name": "study", "task_time": 900}

    # Act
    response = client.post(url, json=payload, headers=headers)

    # Assert
    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "task color required"
    mock_firebase_auth.assert_called_once()
    mock_firestore_client['user_profiles'].document.assert_not_called()


def test_api_create_preset_success(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"
    headers = {"Authorization": "Bearer valid_jwt_token"}
    payload = {"task_name": "study", "task_color": "#ffaa00", "task_time": 900}

    # Mock user profile document
    mock_user_doc = MagicMock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {}
    mock_firestore_client['user_profiles'].document.return_value.get.return_value = mock_user_doc

    # Act
    response = client.post(url, json=payload, headers=headers)

    # Assert
    assert response.status_code == 201
    mock_firebase_auth.assert_called_once()
    
    # Verify Firestore interactions
    mock_firestore_client['user_profiles'].document.assert_called_with('test_user_123')
    mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()
    mock_firestore_client['user_profiles'].document.return_value.set.assert_called_once()


def test_api_update_preset_no_task_name(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"
    headers = {"Authorization": "Bearer valid_jwt_token"}
    payload = {"task_color": "#ffaa00"}

    # Act
    response = client.put(url, json=payload, headers=headers)

    # Assert
    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "Task name required"
    mock_firebase_auth.assert_called_once()
    mock_firestore_client['user_profiles'].document.assert_not_called()
    mock_firebase_auth.assert_called_once()


def test_api_update_preset_task_not_found(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"
    headers = {"Authorization": "Bearer valid_jwt_token"}
    payload = {"task_name": "study", "task_color": "#ffaa00", "task_time": 900}

    # Mock user profile document without "study" preset
    mock_user_doc = MagicMock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {
        "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
    }
    mock_firestore_client['user_profiles'].document.return_value.get.return_value = mock_user_doc

    # Act
    response = client.put(url, json=payload, headers=headers)

    # Assert
    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "Task not found"
    mock_firebase_auth.assert_called_once()
    mock_firestore_client['user_profiles'].document.assert_called_once_with('test_user_123')
    mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()
    mock_firestore_client['user_profiles'].document.return_value.update.assert_not_called()


def test_api_update_preset_success(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"
    headers = {"Authorization": "Bearer valid_jwt_token"}
    payload = {"task_name": "study", "task_color": "#ffaa00", "task_time": 900}

    # Mock user profile document with "Study" preset
    mock_user_doc = MagicMock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {
        "presets": {"Study": {"task_color": "#ffaa00", "task_time": 600}}
    }
    mock_firestore_client['user_profiles'].document.return_value.get.return_value = mock_user_doc

    # Act
    response = client.put(url, json=payload, headers=headers)

    # Assert
    assert response.status_code == 200
    mock_firebase_auth.assert_called_once()
    
    # Verify Firestore interactions
    mock_firestore_client['user_profiles'].document.assert_called_with('test_user_123')
    assert mock_firestore_client['user_profiles'].document.return_value.get.call_count == 3
    mock_firestore_client['user_profiles'].document.return_value.set.assert_called_once()


def test_api_delete_preset_no_data(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"
    headers = {"Authorization": "Bearer valid_jwt_token"}
    payload = {}

    # Act
    response = client.delete(url, json=payload, headers=headers)

    # Assert
    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "Invalid JSON"
    mock_firebase_auth.assert_called_once()
    mock_firestore_client['user_profiles'].document.assert_not_called()


def test_api_delete_preset_content_error(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"
    headers = {"Authorization": "Bearer valid_jwt_token"}
    payload = {"task_name": "study"}

    # Act
    response = client.delete(url, data=payload, headers=headers)

    # Assert
    assert response.status_code == 415
    mock_firebase_auth.assert_called_once()
    mock_firestore_client['user_profiles'].document.assert_not_called()


def test_api_delete_preset_no_task_name(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"
    headers = {"Authorization": "Bearer valid_jwt_token"}
    payload = {"test": "test"}

    # Act
    response = client.delete(url, json=payload, headers=headers)

    # Assert
    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "task name required"
    mock_firebase_auth.assert_called_once()
    mock_firestore_client['user_profiles'].document.assert_not_called()


def test_api_delete_preset_not_found(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset"
    headers = {"Authorization": "Bearer valid_jwt_token"}
    payload = {"task_name": "study"}

    # Mock user profile document without "Study" preset
    mock_user_doc = MagicMock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {
        "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
    }
    mock_firestore_client['user_profiles'].document.return_value.get.return_value = mock_user_doc

    # Act
    response = client.delete(url, json=payload, headers=headers)

    # Assert
    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "Preset not found"
    mock_firebase_auth.assert_called_once()
    mock_firestore_client['user_profiles'].document.assert_called_once_with('test_user_123')
    mock_firestore_client['user_profiles'].document.return_value.get.assert_called_once()
    mock_firestore_client['user_profiles'].document.return_value.update.assert_not_called()

 # TEST #
def test_api_get_preset_success_2(client, mock_firebase_auth, repo, mock_firestore_client):
    # Arrange
    url = "http://localhost:5000/api/profile/preset/meditation"
    headers = {"Authorization": "Bearer valid_jwt_token"}

    # Mock user profile document with presets
    mock_user_doc = MagicMock()
    mock_user_doc.exists = True
    mock_user_doc.to_dict.return_value = {
        "presets": {"Meditation": {"task_color": "#ffaa00", "task_time": 600}}
    }
    mock_firestore_client['user_profiles'].document.return_value.get.return_value = mock_user_doc

    # Act
    response = client.get(url, headers=headers)

    # Assert
    assert response.status_code == 200
    data = response.get_json()
    assert data["Meditation"] == {"task_color": "#ffaa00", "task_time": 600}
    mock_firebase_auth.assert_called_once()

