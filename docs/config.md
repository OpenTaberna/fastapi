# Configuration Module

## Overview

The configuration module provides **environment-based configuration management** with support for multiple secret sources:

- **Environment Variables** - Standard `.env` files
- **Docker Secrets** - Files in `/run/secrets/`
- **Kubernetes Secrets** - Files in `/var/run/secrets/`
- **Default Values** - Built-in defaults

## Table of Contents

- [Quick Start](#quick-start)
- [Module Structure](#module-structure)
- [Configuration Sources](#configuration-sources)
- [Available Settings](#available-settings)
- [Usage Examples](#usage-examples)
- [Secret Loading](#secret-loading)
- [Environment-Specific Config](#environment-specific-config)
- [Testing](#testing)
- [Best Practices](#best-practices)

---

## Quick Start

### Basic Usage

```python
from app.shared.config import get_settings

# Get settings (cached singleton)
settings = get_settings()

print(settings.app_name)          # "OpenTaberna API"
print(settings.database_url)      # "postgresql+asyncpg://..."
print(settings.environment)       # Environment.DEVELOPMENT
```

### With FastAPI

```python
from fastapi import Depends
from app.shared.config import Settings, get_settings

@app.get("/info")
def get_info(settings: Settings = Depends(get_settings)):
    """Get application info."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }
```

---

## Module Structure

```
shared/config/
├── __init__.py          # Public API
├── enums.py             # Environment enum
├── settings.py          # Settings class
├── loader.py            # Secret loader
└── factory.py           # get_settings() singleton
```

**Components:**
- `Environment` - Enum for environments (development, testing, staging, production)
- `Settings` - Pydantic BaseSettings class with all configuration
- `load_secret()` - Load secrets from Docker/K8s/env
- `get_settings()` - Cached singleton factory

---

## Configuration Sources

Settings are loaded in **priority order**:

1. **Docker/K8s Secrets** (highest priority)
   - `/run/secrets/{secret_name}` (Docker)
   - `/var/run/secrets/{secret_name}` (Kubernetes)

2. **Environment Variables**
   - `UPPERCASE_WITH_UNDERSCORES`

3. **.env File**
   - `.env` in project root

4. **Default Values** (lowest priority)
   - Built into `Settings` class

### Example Priority

```bash
# .env file
DATABASE_URL=postgresql://localhost/dev

# Docker secret
echo "postgresql://prod-host/prod-db" > /run/secrets/database_url

# Result: Uses Docker secret (higher priority)
```

---

## Available Settings

### Application

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `app_name` | str | `"OpenTaberna API"` | Application name |
| `app_version` | str | `"0.1.0"` | Application version |
| `environment` | Environment | `DEVELOPMENT` | Environment (dev/test/staging/prod) |
| `debug` | bool | `False` | Debug mode |
| `secret_key` | str | ⚠️ Required | Secret key for JWT/sessions |

### Server

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `host` | str | `"0.0.0.0"` | Server host |
| `port` | int | `8000` | Server port |
| `workers` | int | `1` | Number of worker processes |
| `reload` | bool | `False` | Auto-reload on changes |

### Database

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `database_url` | str | `postgresql+asyncpg://...` | Database connection URL |
| `database_pool_size` | int | `20` | Connection pool size |
| `database_max_overflow` | int | `40` | Pool max overflow |
| `database_pool_timeout` | int | `30` | Pool timeout (seconds) |
| `database_echo` | bool | `False` | Echo SQL queries |

### Redis

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `redis_url` | str | `redis://localhost:6379/0` | Redis connection URL |
| `redis_password` | str\|None | `None` | Redis password (from secrets) |

### Keycloak

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `keycloak_url` | str | `http://localhost:8080` | Keycloak server URL |
| `keycloak_realm` | str | `opentaberna` | Keycloak realm |
| `keycloak_client_id` | str | `opentaberna-api` | Client ID |
| `keycloak_client_secret` | str | Empty | Client secret (from secrets) |

### CORS

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `cors_origins` | list[str] | `["*"]` | Allowed CORS origins |
| `cors_credentials` | bool | `True` | Allow credentials |

### Logging

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `log_level` | str | `"INFO"` | Log level |
| `log_format` | str | `"console"` | Format (console/json) |
| `log_file` | str\|None | `None` | Log file path |

### Feature Flags

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `feature_webhooks_enabled` | bool | `False` | Enable webhooks |

---

## Usage Examples

### Basic Configuration

```python
from app.shared.config import get_settings

settings = get_settings()

# Database
print(settings.database_url)
print(settings.database_pool_size)

# Check environment
if settings.is_production:
    print("Running in production!")

# Hide password in logs
safe_url = settings.get_database_url(hide_password=True)
print(safe_url)  # postgresql://user:***@host/db
```

### Environment-Based Logic

```python
from app.shared.config import get_settings, Environment

settings = get_settings()

if settings.environment == Environment.PRODUCTION:
    # Production-specific logic
    enable_monitoring()
elif settings.environment.is_development():
    # Development-specific logic
    enable_debug_toolbar()
```

### FastAPI Dependency

```python
from fastapi import FastAPI, Depends
from app.shared.config import Settings, get_settings

app = FastAPI()

@app.get("/health")
def health_check(settings: Settings = Depends(get_settings)):
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "version": settings.app_version,
    }
```

### Feature Flags

```python
from app.shared.config import get_settings

settings = get_settings()

@app.post("/register")
def register_user(user: UserCreate):
    """Register new user."""
    if not settings.feature_registration_enabled:
        raise HTTPException(
            status_code=403,
            detail="Registration is currently disabled"
        )
    
    # Registration logic...
```

---

## Secret Loading

### Docker Secrets

Create secrets:

```bash
# Create secret file
echo "my-secret-password" | docker secret create db_password -

# Use in docker-compose.yml
services:
  api:
    secrets:
      - database_url
      - redis_password

secrets:
  database_url:
    file: ./secrets/database_url.txt
  redis_password:
    external: true
```

Settings automatically loads from `/run/secrets/database_url`.

### Kubernetes Secrets

Create secret:

```bash
kubectl create secret generic opentaberna-secrets \
  --from-literal=database_url='postgresql://...' \
  --from-literal=redis_password='secret123'
```

Mount in deployment:

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: api
    volumeMounts:
    - name: secrets
      mountPath: /var/run/secrets
      readOnly: true
  volumes:
  - name: secrets
    secret:
      secretName: opentaberna-secrets
```

### Manual Secret Loading

```python
from app.shared.config.loader import load_secret, load_secret_or_raise

# Load with default
api_key = load_secret("api_key", default="dev-key")

# Load or raise error
db_password = load_secret_or_raise("database_password")

# Check if secrets available
from app.shared.config.loader import secrets_available

if secrets_available():
    print("Running with Docker/K8s secrets")
```

---

## Environment-Specific Config

### Development (.env.development)

```bash
ENVIRONMENT=development
DEBUG=true
RELOAD=true

DATABASE_URL=postgresql+asyncpg://dev:dev@localhost:5432/opentaberna_dev
REDIS_URL=redis://localhost:6379/0

LOG_LEVEL=DEBUG
LOG_FORMAT=console
```

### Production (.env.production)

```bash
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<generate-with-openssl-rand-base64-32>

# Use Docker/K8s secrets for sensitive data
# DATABASE_URL loaded from /run/secrets/database_url
# REDIS_PASSWORD loaded from /run/secrets/redis_password

LOG_LEVEL=INFO
LOG_FORMAT=json

CORS_ORIGINS=["https://yourdomain.com"]
```

### Load Specific .env File

```bash
# Development
export ENV_FILE=.env.development
python -m uvicorn app.main:app

# Production
export ENV_FILE=.env.production
python -m uvicorn app.main:app
```

---

## Testing

### Test with Custom Settings

```python
import pytest
from app.shared.config import get_settings, clear_settings_cache, Settings

def test_settings():
    """Test settings loading."""
    settings = get_settings()
    
    assert settings.app_name == "OpenTaberna API"
    assert settings.environment in [
        Environment.DEVELOPMENT,
        Environment.TESTING,
    ]

def test_custom_settings(monkeypatch):
    """Test with custom environment."""
    clear_settings_cache()
    
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "test-key-123")
    
    settings = get_settings()
    assert settings.is_production
    assert not settings.debug

def test_database_url_hiding():
    """Test password hiding in DB URL."""
    settings = get_settings()
    
    safe_url = settings.get_database_url(hide_password=True)
    assert "***" in safe_url
    assert "password" not in safe_url.lower()
```

### Test Environment Variables

```python
import os
from app.shared.config import Settings

def test_env_vars():
    """Test environment variable loading."""
    os.environ["APP_NAME"] = "Test App"
    os.environ["PORT"] = "9000"
    
    settings = Settings()
    
    assert settings.app_name == "Test App"
    assert settings.port == 9000
```

---

## Best Practices

### 1. Never Commit Secrets

```bash
# .gitignore
.env
.env.local
.env.production
secrets/
```

### 2. Use Secrets for Sensitive Data

```python
# ❌ Bad - Hardcoded
DATABASE_URL = "postgresql://user:password@host/db"

# ✅ Good - From secrets
settings = get_settings()
db_url = settings.database_url  # Loaded from Docker/K8s secret
```

### 3. Validate Production Config

```python
from app.shared.config import get_settings

settings = get_settings()

# Settings validates SECRET_KEY in production
# Raises ValueError if not changed
```

### 4. Use Environment Check

```python
from app.shared.config import get_settings

settings = get_settings()

if settings.is_production:
    # Production-only code
    enable_monitoring()
    disable_debug_mode()
```

### 5. Inject Settings as Dependency

```python
# ✅ Good - Testable with FastAPI dependency override
@app.get("/items")
def get_items(settings: Settings = Depends(get_settings)):
    cache_enabled = settings.cache_enabled
    # ...

# ❌ Bad - Global import, hard to test
settings = get_settings()

@app.get("/items")
def get_items():
    cache_enabled = settings.cache_enabled
```

### 6. Document Environment Variables

Create `.env.example`:

```bash
# Application
APP_NAME=OpenTaberna API
ENVIRONMENT=development

# Database (use Docker secret in production)
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/db

# Required in production
SECRET_KEY=CHANGE_ME_IN_PRODUCTION
```

---

## Troubleshooting

### Settings Not Loading

```python
from app.shared.config import clear_settings_cache, get_settings

# Clear cache and reload
clear_settings_cache()
settings = get_settings()
```

### Secret Not Found

```python
from app.shared.config.loader import secrets_available, load_secret

# Check if secrets directory exists
if not secrets_available():
    print("No Docker/K8s secrets found, using env vars")

# Debug secret loading
secret = load_secret("database_url")
if secret is None:
    print("Secret not found in /run/secrets/ or env vars")
```

### Environment Not Detected

```bash
# Set explicitly
export ENVIRONMENT=production

# Check
python -c "from app.shared.config import get_settings; print(get_settings().environment)"
```

---

## Summary

The config module provides:

✅ **Multiple secret sources** - Docker, K8s, env vars  
✅ **Type-safe settings** - Pydantic validation  
✅ **Environment-based** - dev/test/staging/prod  
✅ **Production-ready** - Secret validation  
✅ **Testable** - Easy to mock and override  
✅ **Cached singleton** - Efficient access  

**Next Steps:**
- Create `.env` file from `.env.example`
- Set `SECRET_KEY` for production
- Configure database URL
- Add feature flags as needed
