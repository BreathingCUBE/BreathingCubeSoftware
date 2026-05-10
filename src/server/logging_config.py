"""
Structured Logging Configuration for CUBE Application.
Provides JSON-formatted logging with contextual information.
"""

import logging
import json
import sys
from datetime import datetime
import os


class CustomJsonFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    Pretty-prints in development, compact in production.
    
    Security: Filters out sensitive data to prevent accidental secret leakage.
    """
    
    # Sensitive field names that should be masked in logs
    SENSITIVE_FIELDS = {
        'token', 'jwt', 'authorization', 'x-api-key', 'api_key', 'secret',
        'password', 'passwd', 'pwd', 'apikey', 'access_token', 'refresh_token',
        'key', 'private_key', 'secret_key', 'firebase', 'credentials'
    }

    def __init__(self):
        super().__init__()
        self.is_dev = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    def _sanitize_value(self, key, value):
        """Return sanitized value if key is sensitive, otherwise return original."""
        if isinstance(key, str) and key.lower() in self.SENSITIVE_FIELDS:
            return "[REDACTED]"
        return value

    def format(self, record):
        """Format log record as JSON with context and security filtering."""
        try:
            log_obj = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': record.levelname,
                'module': record.module,
                'function': record.funcName,
                'message': record.getMessage(),
            }

            # Add extra fields if present (request context, user info, etc.)
            # Use try/except to handle non-serializable objects
            # AND filter sensitive data
            if hasattr(record, 'user_id'):
                log_obj['user_id'] = self._sanitize_value('user_id', record.user_id)
            if hasattr(record, 'endpoint'):
                log_obj['endpoint'] = self._sanitize_value('endpoint', record.endpoint)
            if hasattr(record, 'method'):
                log_obj['method'] = self._sanitize_value('method', record.method)
            if hasattr(record, 'status_code'):
                log_obj['status_code'] = self._sanitize_value('status_code', record.status_code)
            if hasattr(record, 'duration_ms'):
                log_obj['duration_ms'] = self._sanitize_value('duration_ms', record.duration_ms)
            if hasattr(record, 'ip_address'):
                log_obj['ip_address'] = self._sanitize_value('ip_address', record.ip_address)
            if hasattr(record, 'error_type'):
                log_obj['error_type'] = self._sanitize_value('error_type', record.error_type)

            # Pretty-print in development, compact in production
            if self.is_dev:
                return json.dumps(log_obj, indent=2, default=str)
            else:
                return json.dumps(log_obj, separators=(',', ':'), default=str)
        except Exception as e:
            # Fallback if JSON formatting fails
            return json.dumps({
                'timestamp': datetime.utcnow().isoformat(),
                'level': 'ERROR',
                'module': 'logging_config',
                'function': 'CustomJsonFormatter.format',
                'message': f'Log formatting failed: {str(e)}',
                'original_message': record.getMessage()
            })


def setup_logging(app=None):
    """
    Setup structured logging for the Flask application.
    Call this early in your application initialization.
    """
    try:
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(os.getenv('LOG_LEVEL', 'DEBUG'))

        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Create console handler with custom formatter
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(CustomJsonFormatter())
        root_logger.addHandler(console_handler)
        
        # Create file handler - write to logs/app.log
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        
        log_file = os.path.join(logs_dir, 'app.log')
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(CustomJsonFormatter())
        root_logger.addHandler(file_handler)
        
        # Add RequestContextFilter to both handlers
        console_handler.addFilter(RequestContextFilter())
        file_handler.addFilter(RequestContextFilter())

        # Log initialization success
        root_logger.info("Structured logging initialized", extra={
            'app_type': os.getenv('APP_TYPE', 'web'),
            'environment': 'development' if os.getenv('FLASK_DEBUG', 'False').lower() == 'true' else 'production',
            'log_level': os.getenv('LOG_LEVEL', 'DEBUG'),
            'log_file': log_file
        })
    except Exception as e:
        # Fallback: print to stderr if logging setup fails
        print(f"CRITICAL: Logging setup failed: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise


def get_logger(name):
    """
    Get a logger instance with the specified name.
    Use: logger = get_logger(__name__)
    """
    return logging.getLogger(name)


class RequestContextFilter(logging.Filter):
    """
    Logging filter that adds request context to log records.
    Use in Flask request handlers to automatically add user/request info.
    """

    def filter(self, record):
        """Add request context to log record if available."""
        try:
            from flask import request, has_request_context, session

            if has_request_context():
                record.endpoint = request.endpoint or 'unknown'
                record.method = request.method
                record.ip_address = request.remote_addr
                
                # Add user_id if available in session
                if 'uid' in session:
                    record.user_id = session['uid']
                elif hasattr(request, 'user_id'):
                    record.user_id = request.user_id
        except Exception:
            # Silently ignore if request context is not available
            pass
        
        return True
