import pytest
from src.server.utils.validation import validate_login_data, validate_preset, validate_user_info, normalize_task_color, parse_time

@pytest.mark.parametrize("email, password, confirm_password, expected",
    [
        # Valid partition
        ("breid@my.bcit.ca", "password1", "password1", []),
        # Email too long (51 characters)
        ("01234567890123456789012345678901234567890@gmail.com", "password1", "password1", ["Email must be 50 chars or less"]),
        # Email None
        (None, "password1", "password1", ["email cannot be None"]),
        # Password None
        ("breid@my.bcit.ca", None, "password1", ["password cannot be None"]),
        # Confirmation Password None
        ("breid@my.bcit.ca", "password1", None, ["confirm_password cannot be None"]),
        # Password too short
        ("breid@my.bcit.ca", "pass1", "password1", ["Password invalid"]),
        # Password too long (51 characters)
        ("breid@my.bcit.ca", "password1234567890123456789012345678901234567890123", "password1", ["Password invalid"]),
        # Password no numbers
        ("breid@my.bcit.ca", "passwordone", "password1", ["Password invalid"]),
        # Password no letters
        ("breid@my.bcit.ca", "1234567890", "password1", ["Password invalid"]),
        # Password with non-alphanumeric characters
        ("breid@my.bcit.ca", "password@", "password1", ["Password invalid"]),
        # Confirmation Password too short
        ("breid@my.bcit.ca", "password1", "pass1", ["Confirmation Password invalid"]),
        # Confirmation Password too long (51 characters)
        ("breid@my.bcit.ca", "password1", "password1234567890123456789012345678901234567890123", ["Confirmation Password invalid"]),
        # Confirmation Password no numbers
        ("breid@my.bcit.ca", "password1", "passwordone", ["Confirmation Password invalid"]),
        # Confirmation Password no letters
        ("breid@my.bcit.ca", "password1", "1234567890", ["Confirmation Password invalid"]),
        # Confirmation Password with non-alphanumeric characters
        ("breid@my.bcit.ca", "password1", "password@", ["Confirmation Password invalid"]),
    ]
)
def test_validate_login_data(email, password, confirm_password, expected):
    data = {"email": email, "password": password, "confirm_password": confirm_password}
    assert validate_login_data(data) == expected
    # Whitelist Check - reject unknown fields
    data = {"unknown": "breid@my.bcit.ca", "password": "password1", "confirm_password": "password1"}
    assert validate_login_data(data) == ["Unknown fields: {'unknown'}"]


@pytest.mark.parametrize("task_name, task_time, task_color, expected",
    [
        # Valid partition
        ("meditate", 30, "#0000ff", []),
        # Valid partition 2
        ("meditate", 30, "#0000ffff", []),
        # task_name None
        (None, 30, "#0000ff", ["task_name cannot be None"]),
        # task_time None
        ("meditate", None, "#0000ff", ["task_time cannot be None"]),
        # task_color None
        ("meditate", 30, None, ["task_color cannot be None"]),
        # task_name must be string type
        (30, 30, "#0000ff", ["task_name must be a string"]),
        # task_name too long (31 chars)
        ("meditate12345678901234567890123", 30, "#0000ff", ["task_name must be 30 chars or less"]),
        # task_time invalid type
        ("meditate", "30", "#0000ff", ["Task time must be a positive integer"]),
        # task_time negative integer
        ("meditate", -30, "#0000ff", ["Task time must be a positive integer"]),
        # task_time too big
        ("meditate", 5941, "#0000ff", ["Task time must be less then 99 minutes"]),
        # task_time zero
        ("meditate", 0, "#0000ff", ["Task time must be greater than zero"]),
        # task_color invalid type
        ("meditate", 30, 223344, ["Task color must be a valid hex RGB or RGBW string (e.g., '#0000ff' or '#0000ffff')"]),
        # task_color no #
        ("meditate", 30, "0000ff", ["Task color must be a valid hex RGB or RGBW string (e.g., '#0000ff' or '#0000ffff')"]),
        # task_color out of bounds letters
        ("meditate", 30, "#0000fg", ["Task color must be a valid hex RGB or RGBW string (e.g., '#0000ff' or '#0000ffff')"]),
        # task_color too long
        ("meditate", 30, "#0000fff", ["Task color must be a valid hex RGB or RGBW string (e.g., '#0000ff' or '#0000ffff')"]),
        # task_color too short
        ("meditate", 30, "#0000f", ["Task color must be a valid hex RGB or RGBW string (e.g., '#0000ff' or '#0000ffff')"]),
    ]
)
def test_validate_preset(task_name, task_time, task_color, expected):
    data = {"task_name": task_name, "task_time": task_time, "task_color": task_color}
    assert validate_preset(data) == expected
    # Whitelist Check - reject unknown fields
    data = {"task_name": "meditate", "unknown": "unknown"}
    assert validate_preset(data) == ["Unknown fields: {'unknown'}"]


@pytest.mark.parametrize("first_name, last_name, expected",
    [
        # Valid partition
        ("Bryce", "Reid", []),
        # first_name None
        (None, "Reid", ["first_name cannot be None"]),
        # last_name None
        ("Bryce", None, ["last_name cannot be None"]),
        # first_name too long (51 chars)
        ("Bryce1234567890123456789012345678901234567890123456", "Reid", ["first_name must be 50 chars or less"]),
        # last_name too long (51 chars)
        ("Bryce", "Reid12345678901234567890123456789012345678901234567", ["last_name must be 50 chars or less"]),
    ]
)
def test_validate_user_info(first_name, last_name, expected):
    data = {"first_name": first_name, "last_name": last_name}
    assert validate_user_info(data) == expected
    # Whitelist Check - reject unknown fields
    data = {"unknown": "unknown"}
    assert validate_user_info(data) == ["Unknown fields: {'unknown'}"]


@pytest.mark.parametrize("task_color, expected",
    [
        # Valid partition
        ("#0000ff", "#0000ffff"),
        # Valid partition 2
        ("#0000ffff", "#0000ffff"),
        # task_color None
        (None, None),
        # task_color not string
        (42, 42),
        # task_color with white spaces
        (" #0000ff ", "#0000ffff"),
        # task_color with upper case
        ("#0000FF", "#0000ffff"),
    ]
)
def test_normalize_task_color(task_color, expected):
    assert normalize_task_color(task_color) == expected


@pytest.mark.parametrize("time, expected",
    [
        # Valid time
        (73, (1,13)),
        # Valid time
        (35, (0,35)),
        # zero time input
        (0, (None,None)),
        # negative time input
        (-1, (None,None)),
        # noninteger time input
        ("45", (None,None)),
    ]
)
def test_parse_time(time, expected):
    assert parse_time(time) == expected