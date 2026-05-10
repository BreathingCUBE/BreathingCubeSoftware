# Security Audit & Fixes Report

## Executive Summary
**Status:** 4 Critical Security Issues Found & Fixed ✅  
**Severity:** HIGH  
**Date:** April 2, 2026  
**Recommendation:** Review and test security changes before production deployment

---

## Vulnerabilities Found & Fixed

### 🔴 **CRITICAL #1: /health Endpoint Information Disclosure**

**Vulnerability Type:** Information Disclosure (CWE-200)

**Original Code (INSECURE):**
```python
@app.route('/health')
def health():
    return {'status': 'healthy', 'app_type': os.getenv('APP_TYPE', 'web')}, 200
```

**Issue:**
- Endpoint is **unauthenticated** and publicly accessible
- Returns `app_type` field revealing deployment architecture (web vs api)
- Helps attackers understand service topology
- Health checks are often kept intentionally vague in production

**Fix Applied:**
```python
@app.route('/health')
def health():
    # Security: Do not expose internal app configuration
    return {'status': 'healthy'}, 200
```

**Risk Reduced:** ✅ No longer reveals deployment architecture

---

### 🔴 **CRITICAL #2: API Key Logic Bug in require_api_key Decorator**

**Vulnerability Type:** Authentication Bypass + Information Exposure (CWE-287, CWE-522)

**Original Code (BROKEN):**
```python
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        expected_key = os.environ.get("CUBE_API_KEY")
        provided_key = request.headers.get("X-API-Key")
        
        if provided_key != expected_key:
            return jsonify({"error": "Unauthorized"}), 401
        
        # SECURITY BUG: Passes API key as cube_uuid!
        return f(*args, cube_uuid=provided_key, **kwargs)  # ❌ WRONG!
```

**Issues:**
1. Route function receives **API key string** instead of actual cube UUID
2. API key gets logged/exposed in function parameters
3. No protection against timing attacks (direct string comparison)
4. Mixes authentication secret with business logic ID

**Fix Applied:**
```python
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        expected_key = os.environ.get("CUBE_API_KEY")
        provided_key = request.headers.get("X-API-Key")
        
        if not provided_key:
            return jsonify({"error": "Missing X-API-Key header"}), 401
        
        # FIXED: Use constant-time comparison to prevent timing attacks
        import hmac
        if not hmac.compare_digest(provided_key, expected_key):
            return jsonify({"error": "Unauthorized"}), 401
        
        # FIXED: Extract actual cube_uuid from separate header
        # Not from the API key itself
        cube_uuid = request.headers.get("X-Cube-UUID", "unknown")
        return f(*args, cube_uuid=cube_uuid, **kwargs)  # ✅ CORRECT!
```

**Security Improvements:**
- ✅ Uses `hmac.compare_digest()` for timing-attack resistant comparison
- ✅ Separates authentication secret (X-API-Key) from business ID (X-Cube-UUID)
- ✅ API key no longer exposed in function parameters

**Usage:**
```bash
# Correct way to call cube endpoint:
curl -X POST http://localhost:5000/api/task/control \
  -H "X-API-Key: your_actual_api_key" \
  -H "X-Cube-UUID: cube_123456" \
  -H "Content-Type: application/json" \
  -d '{"action": "start"}'
```

---

### 🔴 **CRITICAL #3: Missing Flask Secret Key Enforcement**

**Vulnerability Type:** Weak Cryptography (CWE-326)

**Original Code (INSECURE):**
```python
class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")  # ❌ Default!
```

**Issue:**
- If `FLASK_SECRET_KEY` environment variable is not set, defaults to `"dev-secret-key"`
- All session tokens will be signed with this known default key
- Attackers can forge session tokens and impersonate users
- Affects all Flask features: sessions, CSRF tokens, secure cookies

**Fix Applied:**
```python
class Config:
    # Flask secret key - MUST be set in production
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError(
            "CRITICAL: FLASK_SECRET_KEY environment variable not set. "
            "Session tokens will be vulnerable. Set FLASK_SECRET_KEY in .env or container."
        )
```

**Security Improvements:**
- ✅ App fails to start (loud failure) if FLASK_SECRET_KEY not set
- ✅ Prevents silent vulnerability in production
- ✅ Forces developers to set unique secret key per environment

**Required Action:**
```bash
# Generate a secure key (at least 32 random characters)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set in .env:
FLASK_SECRET_KEY=your_generated_random_key_here

# Or in Docker:
docker run -e FLASK_SECRET_KEY=your_key_here ...
```

---

### 🟡 **MEDIUM #4: No Secret Filtering in Logs**

**Vulnerability Type:** Information Exposure (CWE-532)

**Original Code (RISKY):**
```python
class CustomJsonFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'message': record.getMessage(),
            # ... all fields logged verbatim
        }
        return json.dumps(log_obj)
```

**Issue:**
- Any extra field with 'token', 'key', 'secret', etc. gets logged as-is
- If a developer accidentally logs a JWT token or API key, it's exposed in logs
- Log aggregation systems (ELK, Datadog) would store this forever
- Violates security best practices for secret handling

**Fix Applied:**
```python
class CustomJsonFormatter(logging.Formatter):
    # Sensitive field names that should be masked in logs
    SENSITIVE_FIELDS = {
        'token', 'jwt', 'authorization', 'x-api-key', 'api_key', 'secret',
        'password', 'passwd', 'pwd', 'apikey', 'access_token', 'refresh_token',
        'key', 'private_key', 'secret_key', 'firebase', 'credentials'
    }

    def _sanitize_value(self, key, value):
        """Return sanitized value if key is sensitive, otherwise return original."""
        if isinstance(key, str) and key.lower() in self.SENSITIVE_FIELDS:
            return "[REDACTED]"
        return value

    def format(self, record):
        # ... 
        # All extra fields are sanitized before logging
        if hasattr(record, 'user_id'):
            log_obj['user_id'] = self._sanitize_value('user_id', record.user_id)
        # ... etc
```

**Security Improvements:**
- ✅ Any field matching sensitive keywords is automatically masked
- ✅ Field names are case-insensitive
- ✅ Shows `[REDACTED]` instead of actual secret values
- ✅ Adds defense-in-depth against accidental secret leakage

**Example:**
```python
# This code:
logger.error("Auth failed", extra={'token': 'eyJhbGc...', 'user_id': 'user_123'})

# Produces this log:
{"level": "ERROR", "message": "Auth failed", "token": "[REDACTED]", "user_id": "user_123"}
```

---

## Production Deployment Checklist

Before deploying to production, verify:

- [ ] **FLASK_SECRET_KEY is set** in `.env` or container environment
  ```bash
  # Generate a key:
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

- [ ] **CUBE_API_KEY is set** if using cube endpoints
  ```bash
  export CUBE_API_KEY="your_api_key_here"
  ```

- [ ] **FIREBASE_WEB_API_KEY is set** for Firebase authentication
  ```bash
  export FIREBASE_WEB_API_KEY="your_firebase_key_here"
  ```

- [ ] **serviceAccountKey.json exists** with proper permissions (600)
  ```bash
  chmod 600 serviceAccountKey.json
  ```

- [ ] **Health endpoint doesn't expose sensitive info**
  ```bash
  curl http://localhost:5000/health
  # Should return: {"status": "healthy"}
  # NOT: {"status": "healthy", "app_type": "web"}
  ```

- [ ] **.env file is NOT committed to git**
  ```bash
  # Verify .env is in .gitignore
  grep ".env" .gitignore
  ```

- [ ] **Logs don't contain secrets**
  ```bash
  # Review docker logs for [REDACTED]:
  docker logs cube-web | grep REDACTED
  ```

---

## Additional Security Recommendations

### 1. **Environment Variable Validation**
Consider adding validation for all required environment variables at startup.

### 2. **Rate Limiting**
Add rate limiting middleware to prevent brute force attacks on `/login` and `/api/task/control`.

### 3. **HTTPS Only**
In production, ensure HTTPS is enforced. Add to Dockerfile:
```dockerfile
ENV SECURE_HSTS_SECONDS=31536000
ENV SECURE_HSTS_INCLUDE_SUBDOMAINS=True
```

### 4. **CORS Configuration**
Explicitly configure CORS to only allow trusted origins:
```python
from flask_cors import CORS
CORS(app, origins=["https://yourdomain.com"])
```

### 5. **API Key Rotation**
Implement a mechanism to rotate CUBE_API_KEY without downtime.

### 6. **Audit Logging**
Log all authentication attempts and API calls with user context.

---

## Security Testing

### Test Fixed Vulnerabilities

**Test 1: /health endpoint doesn't expose app_type**
```bash
curl http://localhost:5000/health
# Expected: {"status":"healthy"}
# NOT OK: {"status":"healthy","app_type":"web"}
```

**Test 2: require_api_key uses constant-time comparison**
```bash
# Valid key:
curl -H "X-API-Key: correct_key" http://localhost:5000/api/task/control

# Invalid key (should fail):
curl -H "X-API-Key: wrong_key" http://localhost:5000/api/task/control
```

**Test 3: FLASK_SECRET_KEY is required**
```bash
# Without FLASK_SECRET_KEY set, app should fail to start:
unset FLASK_SECRET_KEY
python run.py
# Expected: ValueError: CRITICAL: FLASK_SECRET_KEY environment variable not set
```

**Test 4: Sensitive fields are redacted in logs**
```bash
# Make a request and check logs:
docker logs cube-web | grep REDACTED
# Should see [REDACTED] for any token/key fields
```

---

## Summary

| Issue | Severity | Status | Impact |
|-------|----------|--------|--------|
| /health exposes app_type | HIGH | ✅ FIXED | Information disclosure prevented |
| require_api_key logic bug | CRITICAL | ✅ FIXED | Auth bypass prevented, constants-time comparison added |
| Missing FLASK_SECRET_KEY | CRITICAL | ✅ FIXED | Session forge attacks prevented |
| No log filtering | MEDIUM | ✅ FIXED | Secret leakage in logs prevented |

**All critical security issues have been addressed.** ✅

Deployment is now safer, but remember to:
1. Set `FLASK_SECRET_KEY` in production
2. Keep `serviceAccountKey.json` secure (not in git)
3. Monitor logs for any sensitive data leakage
4. Implement additional defenses (rate limiting, HTTPS, CORS)
