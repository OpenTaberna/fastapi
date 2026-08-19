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
| `keycloak_public_url` | str | Empty | URL appearing in the token `iss` claim; empty falls back to `keycloak_url` |
| `keycloak_admin_role` | str | `admin` | Realm role required by admin endpoints |
| `keycloak_admin_client_ids` | list[str] | `["opentaberna-admin-ui"]` | Clients whose tokens may reach admin endpoints (matched on `azp`) |
| `keycloak_jwks_cache_seconds` | int | `300` | Signing-key cache lifetime |

Two Keycloak URLs exist on purpose. Inside Docker the API reaches Keycloak over
the compose network (`http://opentaberna-keycloak:8080`) while a browser reaches
it on `http://localhost:8080`, so the address the API fetches keys from is not
the one that ends up in the token's `iss` claim. `keycloak_url` is used for the
JWKS fetch, `keycloak_public_url` for issuer validation. Getting this wrong
shows up as every token being rejected.

`keycloak_admin_client_ids` is what makes "admin endpoints are reachable only
from the admin frontend" true. Roles alone are not enough: an administrator
browsing the storefront still carries the `admin` role, so a shop-side script
could otherwise drive the back office.


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

### Email (Tracking Notifications)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `smtp_host` | str | Empty | SMTP server host. Empty disables sending |
| `smtp_port` | int | `587` | SMTP port (587 uses STARTTLS) |
| `smtp_user` | str | Empty | SMTP username |
| `smtp_password` | str | Empty | SMTP password |
| `email_from` | str | `noreply@opentaberna.local` | Envelope sender address |

### Object Storage (MinIO / S3)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `storage_endpoint_url` | str | `http://localhost:9000` | S3-compatible endpoint |
| `storage_access_key` | str | `minioadmin` | Access key |
| `storage_secret_key` | str | `minioadmin` | Secret key |
| `storage_bucket_labels` | str | `labels` | Bucket holding carrier labels |
| `storage_bucket_items` | str | `item-images` | Bucket holding product images |
| `storage_max_image_bytes` | int | `5242880` | Largest product image accepted (5 MB) |
| `storage_region` | str | `us-east-1` | Region name |

### DHL (Carrier Adapter)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `dhl_api_base_url` | str | DHL sandbox | DHL shipping API base URL |
| `dhl_client_id` | str | `CHANGE_ME` | OAuth2 client ID |
| `dhl_client_secret` | str | `CHANGE_ME` | OAuth2 client secret |
| `dhl_billing_number` | str | `CHANGE_ME` | EKP billing number |
| `dhl_default_label_format` | str | `pdf` | Label format: `pdf` or `zpl` |

### ARQ Worker

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `arq_max_jobs` | int | `10` | Concurrent jobs per worker process |
| `arq_job_timeout` | int | `300` | Seconds a job may run before it is killed |
| `arq_max_tries` | int | `5` | Delivery attempts before a job is dead-lettered (`DEAD`) |

### Transactional Outbox

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `outbox_poll_interval` | int | `30` | Seconds between outbox sweeps |
| `outbox_max_attempts` | int | `5` | Enqueue attempts before an event is marked `FAILED` |

`outbox_poll_interval` drives the poller's schedule directly. ARQ matches
calendar fields rather than sleeping, so the value is translated into second-,
minute- or hour-marks: below 60 it fires at `{0, n, 2n, ...}` seconds of every
minute, below 3600 at the equivalent minute-marks, and above that at
hour-marks. Changing the setting changes the cadence — it is not advisory.

`outbox_max_attempts` bounds how often the poller retries one event. Past the
ceiling the row is marked `FAILED` and skipped, which is what stops a
permanently broken event from being retried on every sweep forever.

**`FAILED` and `DEAD` are not the same state.** `FAILED` means the poller never
managed to hand the event to ARQ, so no job ever ran. `DEAD` means the job did
run and exhausted `arq_max_tries`. Keeping them apart lets maintainers filter
for the two failure classes separately — `OutboxRepository.list_failed()`
returns the first kind.

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
