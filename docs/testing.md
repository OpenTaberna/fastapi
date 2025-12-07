# Testing Documentation

## Overview

This document describes the testing setup for the OpenTaberna FastAPI project. The project uses pytest with automatic module path configuration, allowing you to test any component without manual PYTHONPATH management.

## Table of Contents

- [Setup](#setup)
- [Running Tests](#running-tests)
- [Writing Tests](#writing-tests)
- [Test Structure](#test-structure)
- [Best Practices](#best-practices)
- [Debugging](#debugging)

---

## Setup

### Installation

```bash
# Install dependencies (pytest is included)
uv sync
# or
pip install -e .
```

### How It Works

The project uses `conftest.py` in the root directory to automatically configure Python's import path:

```
fastapi_opentaberna/
├── conftest.py              # Auto-configures imports for pytest
├── src/
│   └── app/                 # Your application code here
├── tests/                   # Your tests here
└── pyproject.toml
```

**`conftest.py`** adds `src/` to the Python path, so you can import modules naturally:

```python
from app.shared.logger import get_logger
from app.services.crud import ItemService
from app.models import Item
```

**No manual PYTHONPATH needed!** Just run `pytest` and imports work automatically.

---

## Running Tests

```bash
# Run all tests
pytest

# Verbose output (recommended)
pytest -v

# Run specific test file
pytest tests/test_something.py

# Run specific test function
pytest tests/test_something.py::test_function_name

# Run tests matching a keyword
pytest -k "auth"

# Stop on first failure
pytest -x

# Show print statements (disable output capture)
pytest -s

# See which tests exist without running
pytest --co -q
```

### Advanced Options

```bash
# Parallel execution (faster)
pytest -n auto

# With coverage report
pytest --cov=app --cov-report=html

# Watch mode (re-run on file changes)
ptw
```

---

## Writing Tests

### File Naming

- Test files: `test_*.py` or `*_test.py`
- Test functions: `test_*()`
- Test classes: `Test*`

### Basic Test Template

```python
def test_something():
    """Always include a docstring describing what you're testing."""
    # Arrange - Set up test data
    value = 42
    
    # Act - Execute the code being tested
    result = some_function(value)
    
    # Assert - Verify the result
    assert result == expected_value
```

### Importing Your Code

Thanks to `conftest.py`, imports work naturally:

```python
# Import from any module in src/app/
from app.shared.logger import get_logger
from app.services.items import ItemService
from app.models.user import User
from app.authorize.keycloak import verify_token
```

### Common Test Patterns

#### Testing Functions

```python
from app.services.calculator import add

def test_add_two_numbers():
    """Test that add function works correctly."""
    result = add(2, 3)
    assert result == 5
```

#### Testing Classes

```python
from app.services.user_service import UserService

def test_user_service_create():
    """Test user creation."""
    service = UserService()
    user = service.create(username="john", email="john@example.com")
    
    assert user.username == "john"
    assert user.email == "john@example.com"
```

#### Testing with Fixtures

```python
import pytest

@pytest.fixture
def sample_user():
    """Provide a sample user for tests."""
    return {"username": "john", "email": "john@example.com"}

def test_with_fixture(sample_user):
    """Use the fixture in your test."""
    assert sample_user["username"] == "john"
```

#### Testing Exceptions

```python
def test_division_by_zero():
    """Test that division by zero raises ValueError."""
    with pytest.raises(ValueError):
        result = divide(10, 0)
```

#### Capturing Output

```python
def test_logging_output(capsys):
    """Test that correct message is logged."""
    from app.shared.logger import get_logger
    
    logger = get_logger("test")
    logger.info("Hello World")
    
    captured = capsys.readouterr()
    assert "Hello World" in captured.out
```

#### Parameterized Tests

```python
@pytest.mark.parametrize("input,expected", [
    (2, 4),
    (3, 9),
    (4, 16),
])
def test_square(input, expected):
    """Test square function with multiple inputs."""
    assert square(input) == expected
```

#### Using Mocks

```python
from unittest.mock import Mock, patch

def test_with_mock():
    """Test using a mock object."""
    with patch('app.services.external_api.call') as mock_call:
        mock_call.return_value = {"status": "success"}
        
        result = my_function()
        
        assert result["status"] == "success"
        mock_call.assert_called_once()
```

---

## Test Structure

### Organize Tests by Module

```
tests/
├── test_logger.py           # Logger tests
├── test_user_service.py     # User service tests
├── test_item_service.py     # Item service tests
├── test_api.py              # API endpoint tests
└── integration/             # Integration tests
    └── test_full_flow.py
```

### Use Classes for Grouping

```python
class TestUserService:
    """All tests for UserService."""
    
    def test_create_user(self):
        """Test user creation."""
        pass
    
    def test_update_user(self):
        """Test user update."""
        pass
    
    def test_delete_user(self):
        """Test user deletion."""
        pass
```

---

## Best Practices

### 1. Descriptive Names

```python
# ✅ Good
def test_user_service_creates_user_with_valid_email():
    pass

# ❌ Bad
def test_user():
    pass
```

### 2. One Assertion Per Test (when possible)

```python
# ✅ Good
def test_user_has_email():
    user = create_user()
    assert user.email == "test@example.com"

def test_user_has_username():
    user = create_user()
    assert user.username == "testuser"

# ❌ Bad
def test_user():
    user = create_user()
    assert user.email == "test@example.com"
    assert user.username == "testuser"
    assert user.created_at is not None
```

### 3. Arrange-Act-Assert Pattern

```python
def test_something():
    # Arrange - Set up data
    value = 10
    
    # Act - Execute function
    result = multiply(value, 2)
    
    # Assert - Verify result
    assert result == 20
```

### 4. Use Fixtures for Setup

```python
@pytest.fixture
def database():
    """Setup and teardown database."""
    db = create_test_db()
    yield db
    db.cleanup()

def test_with_db(database):
    result = database.query("SELECT 1")
    assert result is not None
```

### 5. Test Independence

Each test should be able to run alone and in any order:

```python
# ✅ Good - Each test is self-contained
def test_feature_a():
    setup = create_setup()
    result = test_feature_a(setup)
    assert result is True

def test_feature_b():
    setup = create_setup()
    result = test_feature_b(setup)
    assert result is True
```

### 6. Avoid Testing Implementation Details

```python
# ❌ Bad - Testing internal implementation
def test_uses_specific_algorithm():
    assert service.internal_method() == "quicksort"

# ✅ Good - Testing behavior
def test_sorts_items_correctly():
    items = [3, 1, 2]
    result = service.sort(items)
    assert result == [1, 2, 3]
```

### 7. Use Parametrization

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("", ""),
])
def test_uppercase(input, expected):
    assert uppercase(input) == expected
```

---

## Debugging

### Debug Failed Tests

```bash
# See full output (no capture)
pytest -s

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l

# Drop into debugger on failure
pytest --pdb

# More verbose output
pytest -vv
```

### Debug Specific Issues

```python
# Add print statements (use -s flag)
def test_something():
    print(f"Debug: value = {value}")
    assert value > 0

# Use pytest's built-in debugging
import pytest
def test_something():
    pytest.set_trace()  # Debugger will stop here
    result = my_function()
```

### Test Markers

```python
# Mark tests to skip
@pytest.mark.skip(reason="Not ready yet")
def test_future_feature():
    pass

# Mark slow tests
@pytest.mark.slow
def test_long_running():
    time.sleep(10)

# Run only non-slow tests
# pytest -m "not slow"
```

---

## Common Issues

### Module Not Found

**Error:** `ModuleNotFoundError: No module named 'app'`

**Solution:** Make sure `conftest.py` exists in project root.

### Tests Not Discovered

**Error:** `collected 0 items`

**Solution:** 
- Test files must be named `test_*.py` or `*_test.py`
- Test functions must start with `test_`
- Test classes must start with `Test`

### Import Errors

If imports don't work, check:
1. `conftest.py` exists in project root
2. Your code is in `src/app/` directory
3. You're running pytest from project root

---

## Quick Reference

```bash
# Essential Commands
pytest                    # Run all tests
pytest -v                 # Verbose output
pytest -x                 # Stop on first failure
pytest -s                 # Show print statements
pytest tests/test_file.py # Run specific file
pytest -k "keyword"       # Run tests matching keyword

# Common Patterns in Tests
from app.module import MyClass        # Import your code
assert value == expected              # Basic assertion
with pytest.raises(ValueError):       # Test exceptions
@pytest.fixture                       # Create reusable setup
def test_name(capsys):               # Capture output
```

That's it! Write your tests, run `pytest`, and iterate.
