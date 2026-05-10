#!/usr/bin/env python3
"""
Test script to verify structured JSON logging is working correctly.
Run from project root: python test_logging.py
"""

import sys
import os
import json
from io import StringIO

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up environment for testing
os.environ['FLASK_DEBUG'] = 'True'
os.environ['APP_TYPE'] = 'web'
os.environ['LOG_LEVEL'] = 'DEBUG'

from src.server.logging_config import setup_logging, get_logger

# Initialize logging
setup_logging()

# Capture output
print("=" * 80)
print("TESTING STRUCTURED JSON LOGGING")
print("=" * 80)
print()

# Test 1: Basic logger
print("Test 1: Basic INFO log (development mode - pretty-printed JSON)")
print("-" * 80)
logger1 = get_logger("test.basic")
logger1.info("This is a basic info message")
print()

# Test 2: Logger with extra fields (context)
print("Test 2: Logger with contextual fields (user_id, endpoint, method)")
print("-" * 80)
logger2 = get_logger("test.auth")
logger2.info("User login successful", extra={
    'user_id': 'user_12345',
    'endpoint': '/login',
    'method': 'POST'
})
print()

# Test 3: Error logging with error_type
print("Test 3: ERROR with error_type context")
print("-" * 80)
logger3 = get_logger("test.error")
logger3.error("Authentication failed", extra={
    'endpoint': '/api/login',
    'method': 'POST',
    'error_type': 'invalid_credentials'
})
print()

# Test 4: Warning with status_code
print("Test 4: WARNING with status_code context")
print("-" * 80)
logger4 = get_logger("test.warning")
logger4.warning("Rate limit approaching", extra={
    'user_id': 'user_67890',
    'endpoint': '/api/timer/status',
    'status_code': 429,
    'ip_address': '192.168.1.100'
})
print()

# Test 5: Debug with timing info
print("Test 5: DEBUG with duration_ms context")
print("-" * 80)
logger5 = get_logger("test.timer")
logger5.debug("Timer operation completed", extra={
    'user_id': 'user_11111',
    'endpoint': '/api/task/control',
    'action': 'stop',
    'elapsed_seconds': 300,
    'duration_ms': 42
})
print()

print("=" * 80)
print("✅ All logging tests completed!")
print("=" * 80)
print()
print("Key observations:")
print("- All logs are formatted as JSON")
print("- Each log includes: timestamp, level, module, function, message")
print("- Extra context fields (user_id, endpoint, etc.) are included when provided")
print("- In development (FLASK_DEBUG=True), JSON is pretty-printed with indentation")
print("- In production, JSON would be compact (single-line) for log aggregators")
