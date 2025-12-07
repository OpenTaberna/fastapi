# Logger Documentation

## Overview

The OpenTaberna logging system is a production-ready, enterprise-grade logger built following SOLID principles. It provides structured logging, sensitive data filtering, context management, and environment-specific configurations out of the box.


## Table of Contents

- [Quick Start](#quick-start)
- [Module Structure](#module-structure)
- [Architecture](#architecture)
- [SOLID Principles](#solid-principles)
- [Core Components](#core-components)
- [Usage Examples](#usage-examples)
- [Configuration](#configuration)
- [Best Practices](#best-practices)
- [Advanced Usage](#advanced-usage)
- [Extending the Logger](#extending-the-logger)

---

## Module Structure

The logger is organized into focused, single-responsibility modules:

```
src/app/shared/logger/
├── __init__.py          # Public API exports
├── enums.py             # Enums & Constants (LogLevel, Environment)
├── interfaces.py        # Abstract base classes (ILogFormatter, ILogFilter, ILogHandler)
├── formatters.py        # Formatter implementations (JSONFormatter, ConsoleFormatter)
├── filters.py           # Filter implementations (SensitiveDataFilter, LevelFilter)
├── handlers.py          # Handler implementations (ConsoleHandler, FileHandler, etc.)
├── config.py            # Configuration classes (LoggerConfig)
├── context.py           # Context management (LogContext)
├── logger.py            # Main AppLogger class
├── factory.py           # Factory functions (get_logger, clear_loggers)
└── README.md            # Module-specific documentation
```

---

## Quick Start

### Basic Usage

```python
from app.shared.logger import get_logger

# Create logger for your module
logger = get_logger(__name__)

# Log messages
logger.debug("Detailed debug information")
logger.info("General information", user_id="123")
logger.warning("Warning message", resource="inventory")
logger.error("Error occurred", error_code="E001")
logger.critical("Critical system failure", system="database")

# Log exceptions with traceback
try:
    risky_operation()
except Exception:
    logger.exception("Operation failed", operation="data_import")
```

### With Context

```python
from app.shared.logger import get_logger, LogContext

logger = get_logger(__name__)

# All logs within this context will include request_id and user_id
with LogContext(request_id="abc-123", user_id="456"):
    logger.info("Processing user request")
    logger.info("Fetching user data")
    # Both logs will have request_id and user_id attached
```

### Performance Tracking

```python
# Automatically log execution time
with logger.measure_time("database_query", table="items", operation="SELECT"):
    results = db.execute(query)
```

---

## Architecture

The logger follows a modular architecture with clear separation of concerns:

```
┌─────────────────┐
│   AppLogger     │  ← Main orchestrator (logger.py)
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼───┐ ┌──▼──────┐ ┌──────────┐
│Format │ │ Handler │ │  Filter  │
│  ter  │ │         │ │          │
└───────┘ └─────────┘ └──────────┘
    │         │            │
    ├─JSON    ├─Console    ├─Sensitive Data
    └─Console ├─File       └─Level
              └─Daily Rotating

Factory (factory.py) ──> Creates & Caches ──> AppLogger
Config (config.py)   ──> Configures ──────> AppLogger
Context (context.py) ──> Adds metadata ───> Logs
```

### Module Responsibilities

| Module | Responsibility | Lines | Principle |
|--------|---------------|-------|-----------|
| `enums.py` | Define LogLevel and Environment enums | ~18 | SRP |
| `interfaces.py` | Abstract base classes for extension | ~40 | ISP, DIP |
| `formatters.py` | Format log records (JSON, Console) | ~98 | SRP, OCP |
| `filters.py` | Filter and sanitize log data | ~68 | SRP, OCP |
| `handlers.py` | Output handlers (Console, File, etc.) | ~96 | SRP, LSP |
| `config.py` | Configuration and environment presets | ~113 | SRP, DIP |
| `context.py` | Thread-safe context management | ~59 | SRP |
| `logger.py` | Main AppLogger orchestration | ~124 | SRP, DIP |
| `factory.py` | Logger creation and caching | ~52 | SRP |
| `__init__.py` | Public API exports | ~73 | - |

### Components Hierarchy

1. **Interfaces (Abstractions)** - `interfaces.py`
   - `ILogFormatter`: Defines formatting behavior
   - `ILogHandler`: Defines handler setup
   - `ILogFilter`: Defines filtering/sanitization

2. **Implementations**
   - **Formatters** (`formatters.py`): `JSONFormatter`, `ConsoleFormatter`
   - **Handlers** (`handlers.py`): `ConsoleHandler`, `FileHandler`, `DailyRotatingFileHandler`
   - **Filters** (`filters.py`): `SensitiveDataFilter`, `LevelFilter`

3. **Configuration** - `config.py`
   - `LoggerConfig`: Composes handlers, formatters, and filters
   - Environment-specific presets (dev, test, staging, production)

4. **Context Management** - `context.py`
   - `LogContext`: Thread-safe context manager
   - Request-scoped metadata storage

5. **Orchestration**
   - **Main Logger** (`logger.py`): `AppLogger` coordinates all components
   - **Factory** (`factory.py`): `get_logger()` creates and caches instances

---

## SOLID Principles

### Single Responsibility Principle (SRP)

Each class has one reason to change:

- **`JSONFormatter`**: Only formats logs as JSON
- **`SensitiveDataFilter`**: Only removes sensitive data
- **`ConsoleHandler`**: Only manages console output
- **`AppLogger`**: Only orchestrates logging operations

### Open/Closed Principle (OCP)

The system is open for extension, closed for modification. Create a new file or add to existing implementation files:

```python
# In formatters.py or new file - Add a new formatter
from app.shared.logger.interfaces import ILogFormatter
import logging

class XMLFormatter(ILogFormatter):
    def format(self, record: logging.LogRecord) -> str:
        # Custom XML formatting
        return f"<log><message>{record.getMessage()}</message></log>"

# In handlers.py or new file - Add a new handler
from app.shared.logger.interfaces import ILogHandler, ILogFormatter

class SlackHandler(ILogHandler):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def setup(self, logger: logging.Logger, formatter: ILogFormatter) -> None:
        # Send logs to Slack
        handler = SlackWebhookHandler(self.webhook_url)
        logger.addHandler(handler)
```

### Liskov Substitution Principle (LSP)

All handlers/formatters/filters are interchangeable:

```python
# Any formatter implementing ILogFormatter works
formatter = JSONFormatter()  # or ConsoleFormatter()

# Any handler implementing ILogHandler works
handler = ConsoleHandler()  # or FileHandler() or DailyRotatingFileHandler()
```

### Interface Segregation Principle (ISP)

Focused, minimal interfaces:

```python
class ILogFormatter(ABC):
    @abstractmethod
    def format(self, record: logging.LogRecord) -> str:
        pass  # Only formatting responsibility

class ILogHandler(ABC):
    @abstractmethod
    def setup(self, logger: logging.Logger, formatter: ILogFormatter) -> None:
        pass  # Only handler setup responsibility
```

### Dependency Inversion Principle (DIP)

Depend on abstractions, not concretions:

```python
class AppLogger:
    def __init__(self, config: LoggerConfig):
        # Depends on ILogHandler interface, not specific handlers
        for handler in config.handlers:  # ILogHandler instances
            handler.setup(self._logger, formatter)
```

---

## Core Components

### Formatters

#### JSONFormatter

Structured JSON output for production environments and log aggregation systems.

```python
from app.shared.logger import JSONFormatter, LoggerConfig, get_logger
from pathlib import Path

config = LoggerConfig(
    name="my_app",
    handlers=[
        FileHandler(Path("/var/log/app.log"))
    ]
)
logger = get_logger("my_app", config=config)
```

**Output:**
```json
{
  "timestamp": "2025-12-06T14:30:45.123456",
  "level": "INFO",
  "logger": "my_app.service",
  "message": "User logged in",
  "module": "auth",
  "function": "login",
  "line": 42,
  "context": {
    "request_id": "abc-123",
    "user_id": "456"
  },
  "extra": {
    "email": "user@example.com"
  }
}
```

#### ConsoleFormatter

Human-readable output with optional colors for development.

```python
from app.shared.logger import ConsoleFormatter

# Automatically used in development environment
logger = get_logger(__name__)
```

**Output:**
```
[2025-12-06 14:30:45] INFO     my_app.service: User logged in | request_id=abc-123 user_id=456
```

### Handlers

#### ConsoleHandler

Outputs to stdout/stderr.

```python
from app.shared.logger import ConsoleHandler, LogLevel

handler = ConsoleHandler(level=LogLevel.INFO)
```

#### FileHandler

Rotating file handler (size-based rotation).

```python
from app.shared.logger import FileHandler
from pathlib import Path

handler = FileHandler(
    filepath=Path("/var/log/app.log"),
    level=LogLevel.INFO,
    max_bytes=10 * 1024 * 1024,  # 10MB
    backup_count=5  # Keep 5 backup files
)
```

#### DailyRotatingFileHandler

Time-based rotation (daily at midnight).

```python
from app.shared.logger import DailyRotatingFileHandler
from pathlib import Path

handler = DailyRotatingFileHandler(
    filepath=Path("/var/log/app.log"),
    level=LogLevel.INFO,
    backup_count=30  # Keep 30 days of logs
)
```

### Filters

#### SensitiveDataFilter

Automatically redacts sensitive information:

- Passwords, tokens, API keys
- Authorization headers
- Credit card numbers, SSNs
- Session IDs, cookies

```python
logger.info("User authenticated", password="secret123", token="xyz789")
# Output: password="***REDACTED***", token="***REDACTED***"
```

**Protected keywords:**
- `password`, `passwd`, `pwd`
- `secret`, `token`, `api_key`, `apikey`
- `authorization`, `auth`, `credential`
- `private_key`, `access_token`, `refresh_token`
- `session_id`, `cookie`, `csrf_token`
- `ssn`, `credit_card`, `cvv`, `pin`

#### LevelFilter

Filter logs by minimum level.

```python
from app.shared.logger import LevelFilter, LogLevel

filter = LevelFilter(min_level=LogLevel.WARNING)
```

---

## Usage Examples

### Basic Logging

```python
from app.shared.logger import get_logger

logger = get_logger(__name__)

# Simple messages
logger.info("Application started")
logger.debug("Debug information", variable=value)

# With structured data
logger.info(
    "Order created",
    order_id="ORD-123",
    user_id="USR-456",
    total_amount=99.99,
    currency="EUR"
)
```

### Exception Logging

```python
try:
    process_payment(order_id)
except PaymentError as e:
    logger.exception(
        "Payment processing failed",
        order_id=order_id,
        error_type=type(e).__name__
    )
    raise

# Or with manual exception info
try:
    risky_operation()
except Exception:
    logger.error(
        "Operation failed",
        exc_info=True,
        operation="data_sync"
    )
```

### Context Management

```python
from app.shared.logger import get_logger, LogContext

logger = get_logger(__name__)

# Request-scoped logging
with LogContext(request_id="req-123", user_id="user-456"):
    logger.info("Request received")
    
    # Nested contexts merge
    with LogContext(order_id="ord-789"):
        logger.info("Processing order")
        # This log has request_id, user_id, AND order_id

# Context automatically cleaned up after block
logger.info("Outside context")  # No request_id here
```

### Performance Measurement

```python
# Measure and log execution time
with logger.measure_time("database_query", query_type="SELECT", table="items"):
    results = database.execute(query)

# Logs:
# [DEBUG] Starting database_query | query_type=SELECT table=items
# [INFO] Completed database_query | query_type=SELECT table=items duration_ms=45.23

# If exception occurs
with logger.measure_time("api_call", endpoint="/users"):
    response = requests.get(url)
    response.raise_for_status()

# On error logs:
# [ERROR] Failed api_call | endpoint=/users duration_ms=1234.56 [+ exception trace]
```

### FastAPI Integration

```python
from fastapi import FastAPI, Request
from app.shared.logger import get_logger, LogContext
import uuid

app = FastAPI()
logger = get_logger(__name__)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    
    with LogContext(
        request_id=request_id,
        path=request.url.path,
        method=request.method
    ):
        logger.info("Request started")
        
        try:
            response = await call_next(request)
            logger.info(
                "Request completed",
                status_code=response.status_code
            )
            return response
        except Exception:
            logger.exception("Request failed")
            raise

@app.get("/items/{item_id}")
async def get_item(item_id: str):
    # All logs here automatically have request context
    logger.info("Fetching item", item_id=item_id)
    
    with logger.measure_time("database_fetch", item_id=item_id):
        item = await database.get_item(item_id)
    
    return item
```

---

## Configuration

### Environment-Based Configuration

The logger automatically configures itself based on the `ENVIRONMENT` variable:

```bash
# Set environment
export ENVIRONMENT=production  # or development, staging, testing
```

```python
from app.shared.logger import get_logger

# Automatically uses appropriate config
logger = get_logger(__name__)
```

### Environment Configurations

#### Development
```python
Environment.DEVELOPMENT
├─ Level: DEBUG
├─ Handlers: Console (colored, human-readable)
├─ Filters: SensitiveDataFilter
└─ Output: Colored console output
```

#### Testing
```python
Environment.TESTING
├─ Level: WARNING (reduced noise)
├─ Handlers: Console
├─ Filters: SensitiveDataFilter
└─ Output: Console warnings and errors only
```

#### Staging
```python
Environment.STAGING
├─ Level: INFO
├─ Handlers:
│  ├─ Console (INFO+)
│  ├─ File: app.log (INFO+, 50MB rotation, 5 backups)
│  └─ File: error.log (ERROR+, 50MB rotation, 5 backups)
├─ Filters: SensitiveDataFilter
└─ Output: Console + rotating files (JSON)
```

#### Production
```python
Environment.PRODUCTION
├─ Level: INFO
├─ Handlers:
│  ├─ Console (WARNING+ only)
│  ├─ DailyFile: app.log (INFO+, 30 days)
│  └─ DailyFile: error.log (ERROR+, 90 days)
├─ Filters: SensitiveDataFilter
└─ Output: JSON logs with daily rotation
```

### Custom Configuration

```python
from app.shared.logger import (
    get_logger,
    LoggerConfig,
    LogLevel,
    ConsoleHandler,
    FileHandler,
    JSONFormatter,
    SensitiveDataFilter,
    Environment
)
from pathlib import Path

# Create custom configuration
config = LoggerConfig(
    name="custom_app",
    level=LogLevel.DEBUG,
    handlers=[
        ConsoleHandler(LogLevel.INFO),
        FileHandler(
            filepath=Path("/custom/path/app.log"),
            level=LogLevel.DEBUG,
            max_bytes=100 * 1024 * 1024,  # 100MB
            backup_count=10
        )
    ],
    filters=[SensitiveDataFilter()],
    environment=Environment.PRODUCTION
)

logger = get_logger("custom_app", config=config)
```

### Manual Environment Configuration

```python
from app.shared.logger import get_logger, Environment
from pathlib import Path

logger = get_logger(
    __name__,
    environment=Environment.PRODUCTION,
    log_dir=Path("/var/log/myapp")
)
```

---

## Best Practices

### 1. Use Module-Level Loggers

```python
# ✅ Good: Use __name__ for automatic module tracking
from app.shared.logger import get_logger

logger = get_logger(__name__)

# ❌ Bad: Hardcoded names
logger = get_logger("my_logger")
```

**Note:** Avoid using reserved LogRecord attribute names as keyword arguments. Reserved names include:
`name`, `msg`, `args`, `created`, `filename`, `funcName`, `levelname`, `levelno`, `lineno`, `module`, `msecs`, `message`, `pathname`, `process`, `processName`, `relativeCreated`, `thread`, `threadName`, `exc_info`, `exc_text`, `stack_info`, `taskName`

```python
# ✅ Good: Use custom names
logger.info("Processing", component="auth", item_count=5)

# ❌ Bad: Using reserved names (will be filtered out)
logger.info("Processing", module="auth", message="test")
```

### 2. Log Structured Data

```python
# ✅ Good: Structured fields for easy querying
logger.info(
    "Order processed",
    order_id="ORD-123",
    user_id="USR-456",
    amount=99.99,
    status="completed"
)

# ❌ Bad: Unstructured string interpolation
logger.info(f"Order {order_id} processed for user {user_id} amount {amount}")
```

### 3. Use Appropriate Log Levels

```python
# DEBUG: Detailed diagnostic information
logger.debug("Variable state", user_dict=user_data)

# INFO: General informational messages
logger.info("User login successful", user_id="123")

# WARNING: Warning messages (recoverable issues)
logger.warning("API rate limit approaching", usage_percent=85)

# ERROR: Error messages (handled exceptions)
logger.error("Failed to process payment", order_id="ORD-123", exc_info=True)

# CRITICAL: Critical errors (system failures)
logger.critical("Database connection lost", attempts=3)
```

### 4. Use Context for Request Tracking

```python
# ✅ Good: All logs in context share common fields
with LogContext(request_id=request_id, user_id=user_id):
    logger.info("Processing request")
    service.process()
    logger.info("Request completed")

# ❌ Bad: Repeating context in every log
logger.info("Processing request", request_id=request_id, user_id=user_id)
logger.info("Request completed", request_id=request_id, user_id=user_id)
```

### 5. Use Exception Logging

```python
# ✅ Good: Include full traceback
try:
    risky_operation()
except Exception:
    logger.exception("Operation failed", operation="import")

# ✅ Also good: Manual exc_info
try:
    risky_operation()
except ValueError as e:
    logger.error("Invalid value", exc_info=True, value=str(e))

# ❌ Bad: Losing stack trace
except Exception as e:
    logger.error(f"Error: {e}")
```

### 6. Measure Performance for Critical Operations

```python
# ✅ Good: Automatic timing and error handling
with logger.measure_time("external_api_call", service="payment"):
    response = payment_api.charge(amount)

# Automatically logs:
# - Start of operation
# - Duration on success
# - Duration and exception on failure
```

### 7. Don't Log Sensitive Data

The logger filters common sensitive fields, but be mindful:

```python
# ✅ Good: Sensitive fields automatically redacted
logger.info("User authenticated", password=pwd, token=token)
# Output: password="***REDACTED***", token="***REDACTED***"

# ✅ Good: Log IDs instead of full data
logger.info("User data updated", user_id=user.id)

# ❌ Bad: Logging entire objects with PII
logger.info("User data", user_data=user.__dict__)
```

### 8. Use Consistent Naming Conventions

```python
# ✅ Good: Consistent field names across codebase
logger.info("Event", user_id="123", order_id="ORD-456")
logger.info("Another event", user_id="789", order_id="ORD-123")

# ❌ Bad: Inconsistent naming
logger.info("Event", user="123", order_id="ORD-456")
logger.info("Another event", user_id="789", order="ORD-123")
```

---

## Advanced Usage

### Custom Formatter

Create your custom formatter in a new file or add to `formatters.py`:

```python
# In src/app/shared/logger/formatters.py or custom file
from app.shared.logger.interfaces import ILogFormatter
import logging

class CustomFormatter(ILogFormatter):
    def format(self, record: logging.LogRecord) -> str:
        return f"[CUSTOM] {record.levelname}: {record.getMessage()}"

# Use custom formatter
from app.shared.logger import get_logger, LoggerConfig, ConsoleHandler

config = LoggerConfig(
    name="custom",
### Custom Handler

Create your custom handler in a new file or add to `handlers.py`:

```python
# In src/app/shared/logger/handlers.py or custom file
from app.shared.logger.interfaces import ILogHandler, ILogFormatter
from app.shared.logger.enums import LogLevel
import logging

class DatabaseHandler(ILogHandler):
    """Log to database."""
    
    def __init__(self, level: LogLevel = LogLevel.ERROR):
        self.level = level
    
    def setup(self, logger: logging.Logger, formatter: ILogFormatter) -> None:
        from app.shared.logger.handlers import _FormatterWrapper
        
        class DBHandler(logging.Handler):
            def __init__(self, db_connection):
                super().__init__()
                self.db = db_connection
            
            def emit(self, record):
                # Save to database
                log_data = self.format(record)
### Custom Filter

Create your custom filter in a new file or add to `filters.py`:

```python
# In src/app/shared/logger/filters.py or custom file
from app.shared.logger.interfaces import ILogFilter
from typing import Any, Dict
import logging

class IPFilter(ILogFilter):
    """Filter logs from specific IP addresses."""
    
    def __init__(self, blocked_ips: list):
        self.blocked_ips = blocked_ips
    
    def filter(self, record: logging.LogRecord) -> bool:
        ip = getattr(record, 'ip_address', None)
        return ip not in self.blocked_ips
    
    def sanitize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # No sanitization needed for this filter
        return data

# Use in config
from app.shared.logger import LoggerConfig

config = LoggerConfig(
    name="filtered",
    filters=[IPFilter(blocked_ips=["192.168.1.100"])]
)
``` 
    def filter(self, record: logging.LogRecord) -> bool:
        ip = getattr(record, 'ip_address', None)
        return ip not in self.blocked_ips
    
    def sanitize(self, data: dict) -> dict:
        return data

# Use in config
config = LoggerConfig(
    name="filtered",
    filters=[IPFilter(blocked_ips=["192.168.1.100"])]
)
```

### Multiple Loggers

```python
# Different loggers for different purposes
app_logger = get_logger("app")
security_logger = get_logger("security")
audit_logger = get_logger("audit")

app_logger.info("Application event")
security_logger.warning("Security event", threat_level="medium")
audit_logger.info("Audit trail", action="user_delete", target_id="123")
```

### Testing with Logger

```python
from app.shared.logger import get_logger, clear_loggers, LoggerConfig, Environment

def test_my_function():
    # Clear any cached loggers
    clear_loggers()
    
    # Use testing environment (WARNING level, less noise)
    logger = get_logger(__name__, environment=Environment.TESTING)
    
    # Your test code
    result = my_function()
    
    assert result is not None
```

---

## Extending the Logger

### Adding a Slack Handler

```python
from app.shared.logger import ILogHandler, ILogFormatter
import logging
import requests

class SlackHandler(ILogHandler):
    """Send critical logs to Slack."""
    
    def __init__(self, webhook_url: str, level=logging.ERROR):
        self.webhook_url = webhook_url
        self.level = level
    
    def setup(self, logger: logging.Logger, formatter: ILogFormatter) -> None:
        handler = SlackWebhookHandler(self.webhook_url)
        handler.setLevel(self.level)
        logger.addHandler(handler)

class SlackWebhookHandler(logging.Handler):
    def __init__(self, webhook_url: str):
        super().__init__()
        self.webhook_url = webhook_url
    
    def emit(self, record: logging.LogRecord):
        message = self.format(record)
        requests.post(
            self.webhook_url,
            json={"text": message}
        )

# Use in production
config = LoggerConfig(
    name="app",
    handlers=[
        ConsoleHandler(),
        SlackHandler(webhook_url="https://hooks.slack.com/...")
    ]
)
```

### Adding Sentry Integration

```python
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

# Initialize Sentry with logging integration
sentry_logging = LoggingIntegration(
    level=logging.INFO,
    event_level=logging.ERROR
)

sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[sentry_logging]
)

# Use logger normally - errors automatically sent to Sentry
logger = get_logger(__name__)
logger.error("This will appear in Sentry")
```

### Adding Metrics Collection

```python
from app.shared.logger import AppLogger
from prometheus_client import Counter

class MetricsLogger(AppLogger):
    """Logger with Prometheus metrics."""
    
    def __init__(self, config):
        super().__init__(config)
        self.error_counter = Counter(
            'app_errors_total',
            'Total application errors',
            ['level']
        )
    
    def error(self, message: str, **kwargs):
        self.error_counter.labels(level='error').inc()
        super().error(message, **kwargs)
    
## Troubleshooting

### Logs Not Appearing

```python
# Check logger configuration
logger = get_logger(__name__)
print(f"Logger level: {logger._logger.level}")
print(f"Handlers: {logger._logger.handlers}")

# Ensure environment is set correctly
import os
print(f"Environment: {os.getenv('ENVIRONMENT', 'not set')}")

# Check if handlers are properly configured
for handler in logger._logger.handlers:
    print(f"Handler: {handler.__class__.__name__}, Level: {handler.level}")
```

### Reserved Attribute Conflicts

If you see `KeyError: "Attempt to overwrite 'X' in LogRecord"`, you're using a reserved attribute name:

```python
# ❌ Bad: Using reserved attribute
logger.info("Message", module="auth")  # 'module' is reserved

# ✅ Good: Use different name
logger.info("Message", component="auth")  # 'component' is safe
```

The logger automatically filters out reserved attributes to prevent this error.ger = get_logger(__name__)
print(f"Logger level: {logger._logger.level}")
print(f"Handlers: {logger._logger.handlers}")

# Ensure environment is set correctly
import os
print(f"Environment: {os.getenv('ENVIRONMENT', 'not set')}")
```

### Sensitive Data Not Filtered

```python
# Check if SensitiveDataFilter is active
from app.shared.logger import SensitiveDataFilter

config = logger.config
has_filter = any(isinstance(f, SensitiveDataFilter) for f in config.filters)
print(f"Has sensitive filter: {has_filter}")

# Add custom sensitive keywords
filter = SensitiveDataFilter()
filter.SENSITIVE_KEYS.add("my_sensitive_field")
```

### Performance Issues

```python
# Use appropriate log levels in production
# Set to INFO or WARNING, not DEBUG

# Use lazy logging
logger.debug("Expensive operation: %s", lambda: expensive_function())

# Or check level before expensive operations
if logger._logger.isEnabledFor(logging.DEBUG):
    debug_data = expensive_debug_info()
    logger.debug("Debug info", data=debug_data)
```

### File Permissions

```bash
# Ensure log directory exists and is writable
sudo mkdir -p /var/log/opentaberna
sudo chown $USER:$USER /var/log/opentaberna
chmod 755 /var/log/opentaberna
```

---

## API Reference

### Functions

#### `get_logger(name, config=None, environment=None, log_dir=None)`

Get or create a logger instance.

**Parameters:**
- `name` (str): Logger name (typically `__name__`)
- `config` (LoggerConfig, optional): Custom configuration
- `environment` (Environment, optional): Environment type
- `log_dir` (Path, optional): Directory for log files

**Returns:** `AppLogger` instance

#### `clear_loggers()`

Clear all cached logger instances. Useful for testing.

#### `setup_request_logging(logger, request_id, **context)`

Setup logging context for a request. Returns a `LogContext` instance.

### Classes

#### `AppLogger`

Main logger class.

**Methods:**
- `debug(message, **kwargs)`: Log debug message
- `info(message, **kwargs)`: Log info message
- `warning(message, **kwargs)`: Log warning message
- `error(message, exc_info=False, **kwargs)`: Log error message
- `critical(message, exc_info=True, **kwargs)`: Log critical message
- `exception(message, **kwargs)`: Log exception with traceback
- `measure_time(operation, **context)`: Context manager for timing

#### `LogContext`

Context manager for adding contextual information.

```python
with LogContext(key1=value1, key2=value2):
    # logs here include key1 and key2
    pass
```

#### `LoggerConfig`

Configuration for logger setup.

**Parameters:**
- `name` (str): Logger name
- `level` (LogLevel): Minimum log level
- `handlers` (List[ILogHandler]): List of handlers
- `filters` (List[ILogFilter]): List of filters
- `environment` (Environment): Deployment environment

**Class Methods:**
- `from_environment(name, env, log_dir)`: Create config from environment

### Enums

#### `LogLevel`

- `DEBUG`
- `INFO`
- `WARNING`
- `ERROR`
- `CRITICAL`

#### `Environment`

- `DEVELOPMENT`
- `TESTING`
- `STAGING`
- `PRODUCTION`

---

## Migration Guide

### From Python's logging module

```python
# Before
import logging
logger = logging.getLogger(__name__)
logger.info("Message")

# After
from app.shared.logger import get_logger
logger = get_logger(__name__)
logger.info("Message")
```

### From Loguru

```python
# Before
from loguru import logger
logger.info("Message", user_id=123)

# After
from app.shared.logger import get_logger
logger = get_logger(__name__)
logger.info("Message", user_id=123)
## Performance Considerations

- **Log Level**: Use INFO or WARNING in production (avoid DEBUG)
- **Structured Data**: Pass objects as kwargs, not in message strings
- **Context**: Use `LogContext` instead of repeating fields
- **File Rotation**: Use daily rotation in production for better performance
- **Async Operations**: Logger is synchronous; for high-volume async apps, consider buffering
- **Reserved Attributes**: Automatically filtered (minimal overhead)

---

## Module Development

### Adding New Components

The modular structure makes it easy to add new components:

1. **New Formatter**: Add to `formatters.py` or create new file implementing `ILogFormatter`
2. **New Handler**: Add to `handlers.py` or create new file implementing `ILogHandler`
3. **New Filter**: Add to `filters.py` or create new file implementing `ILogFilter`
4. **Export**: Add to `__init__.py` if it should be part of public API

### Running Tests

```bash
# Set PYTHONPATH
export PYTHONPATH=/path/to/fastapi_opentaberna/src:$PYTHONPATH

# Run tests
python3 tests/test_logger_module.py

# Run examples
python3 examples/logger_usage.py
```

---

## Performance Considerations

- **Log Level**: Use INFO or WARNING in production (avoid DEBUG)
- **Structured Data**: Pass objects as kwargs, not in message strings
- **Context**: Use `LogContext` instead of repeating fields
- **File Rotation**: Use daily rotation in production for better performance
- **Async Operations**: Logger is synchronous; for high-volume async apps, consider buffering
