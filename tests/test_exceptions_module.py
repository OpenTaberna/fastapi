"""
Tests for the Exception Module.

Tests all exception classes, helper functions, and automatic logging.
"""

from unittest.mock import Mock, patch
from app.shared.exceptions import (
    # Exception classes
    NotFoundError,
    ValidationError,
    DatabaseError,
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError,
    ExternalServiceError,
    InternalError,
    AppException,
    # Enums
    ErrorCode,
    ErrorCategory,
    # Helper functions
    entity_not_found,
    missing_field,
    invalid_format,
    duplicate_entry,
    constraint_violation,
    database_connection_error,
    database_integrity_error,
    token_expired,
    invalid_token,
    authentication_required,
    access_denied,
    insufficient_permissions,
    invalid_state,
    operation_not_allowed,
    external_service_unavailable,
    external_service_timeout,
    configuration_error,
)


# ============================================================================
# Base Exception Tests
# ============================================================================


class TestAppException:
    """Test the base AppException class."""

    @patch("app.shared.logger.get_logger")
    def test_basic_exception_creation(self, mock_get_logger):
        """Test creating a basic exception."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = AppException(
            message="Test error",
            error_code=ErrorCode.INTERNAL_ERROR,
            category=ErrorCategory.INTERNAL,
        )

        assert exc.message == "Test error"
        assert exc.error_code == ErrorCode.INTERNAL_ERROR
        assert exc.category == ErrorCategory.INTERNAL
        assert exc.context == {}
        assert exc.original_exception is None

    @patch("app.shared.logger.get_logger")
    def test_exception_with_context(self, mock_get_logger):
        """Test exception with additional context."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        context = {"user_id": 123, "action": "delete"}
        exc = AppException(
            message="Test error",
            error_code=ErrorCode.INTERNAL_ERROR,
            category=ErrorCategory.INTERNAL,
            context=context,
        )

        assert exc.context == context
        assert exc.get_context() == context

    @patch("app.shared.logger.get_logger")
    def test_exception_with_original_exception(self, mock_get_logger):
        """Test wrapping another exception."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        original = ValueError("Original error")
        exc = AppException(
            message="Wrapped error",
            error_code=ErrorCode.INTERNAL_ERROR,
            category=ErrorCategory.INTERNAL,
            original_exception=original,
        )

        assert exc.original_exception is original

    @patch("app.shared.logger.get_logger")
    def test_to_dict(self, mock_get_logger):
        """Test converting exception to dictionary."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = AppException(
            message="Test error",
            error_code=ErrorCode.INTERNAL_ERROR,
            category=ErrorCategory.INTERNAL,
            context={"key": "value"},
        )

        result = exc.to_dict()

        assert result["error"]["message"] == "Test error"
        assert result["error"]["code"] == ErrorCode.INTERNAL_ERROR.value
        assert result["error"]["category"] == ErrorCategory.INTERNAL.value
        assert result["error"]["context"]["key"] == "value"

    @patch("app.shared.logger.get_logger")
    def test_automatic_logging_server_error(self, mock_get_logger):
        """Test that server errors are logged with ERROR level."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        AppException(
            message="Server error",
            error_code=ErrorCode.INTERNAL_ERROR,
            category=ErrorCategory.INTERNAL,
        )

        # Verify error was logged
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert "Server error" in call_args[0]
        assert call_args[1]["error_code"] == ErrorCode.INTERNAL_ERROR.value
        assert call_args[1]["category"] == ErrorCategory.INTERNAL.value

    @patch("app.shared.logger.get_logger")
    def test_automatic_logging_client_error(self, mock_get_logger):
        """Test that client errors are logged with WARNING level."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        AppException(
            message="Client error",
            error_code=ErrorCode.INVALID_INPUT,
            category=ErrorCategory.VALIDATION,
        )

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "Client error" in call_args[0]

    @patch("app.shared.logger.get_logger")
    def test_no_logging_when_disabled(self, mock_get_logger):
        """Test that logging can be disabled."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        AppException(
            message="Test error",
            error_code=ErrorCode.INTERNAL_ERROR,
            category=ErrorCategory.INTERNAL,
            should_auto_log=False,
        )

        # Verify no logging occurred
        mock_logger.error.assert_not_called()
        mock_logger.warning.assert_not_called()

    @patch("app.shared.logger.get_logger")
    def test_string_representation(self, mock_get_logger):
        """Test string representation of exception."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = AppException(
            message="Test error",
            error_code=ErrorCode.INTERNAL_ERROR,
            category=ErrorCategory.INTERNAL,
            context={"key": "value"},
        )

        str_repr = str(exc)
        assert "INTERNAL" in str_repr
        assert "internal_error" in str_repr
        assert "Test error" in str_repr


# ============================================================================
# NotFoundError Tests
# ============================================================================


class TestNotFoundError:
    """Test NotFoundError exception."""

    @patch("app.shared.logger.get_logger")
    def test_basic_not_found(self, mock_get_logger):
        """Test basic NotFoundError."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = NotFoundError("User not found")

        assert exc.message == "User not found"
        assert exc.category == ErrorCategory.NOT_FOUND
        assert exc.error_code == ErrorCode.RESOURCE_NOT_FOUND

    @patch("app.shared.logger.get_logger")
    def test_entity_not_found_helper(self, mock_get_logger):
        """Test entity_not_found helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = entity_not_found("User", 123)

        assert "User" in exc.message
        assert "123" in exc.message
        assert exc.error_code == ErrorCode.ENTITY_NOT_FOUND
        assert exc.context["entity_type"] == "User"
        assert exc.context["entity_id"] == "123"


# ============================================================================
# ValidationError Tests
# ============================================================================


class TestValidationError:
    """Test ValidationError exception."""

    @patch("app.shared.logger.get_logger")
    def test_basic_validation_error(self, mock_get_logger):
        """Test basic ValidationError."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = ValidationError("Invalid input")

        assert exc.message == "Invalid input"
        assert exc.category == ErrorCategory.VALIDATION
        assert exc.error_code == ErrorCode.INVALID_INPUT

    @patch("app.shared.logger.get_logger")
    def test_missing_field_helper(self, mock_get_logger):
        """Test missing_field helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = missing_field("email")

        assert "email" in exc.message
        assert exc.error_code == ErrorCode.MISSING_FIELD
        assert exc.context["field"] == "email"

    @patch("app.shared.logger.get_logger")
    def test_invalid_format_helper(self, mock_get_logger):
        """Test invalid_format helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = invalid_format("email", "valid email address")

        assert "email" in exc.message
        assert "valid email address" in exc.message
        assert exc.error_code == ErrorCode.INVALID_FORMAT
        assert exc.context["field"] == "email"
        assert exc.context["expected_format"] == "valid email address"

    @patch("app.shared.logger.get_logger")
    def test_duplicate_entry_helper(self, mock_get_logger):
        """Test duplicate_entry helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = duplicate_entry("User", "email", "test@example.com")

        assert "User" in exc.message
        assert "email" in exc.message
        assert "test@example.com" in exc.message
        assert exc.error_code == ErrorCode.DUPLICATE_ENTRY
        assert exc.context["entity_type"] == "User"
        assert exc.context["field"] == "email"

    @patch("app.shared.logger.get_logger")
    def test_constraint_violation_helper(self, mock_get_logger):
        """Test constraint_violation helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = constraint_violation("price_positive", "Price must be > 0")

        assert "price_positive" in exc.message
        assert exc.error_code == ErrorCode.CONSTRAINT_VIOLATION
        assert exc.context["constraint"] == "price_positive"
        assert exc.context["details"] == "Price must be > 0"


# ============================================================================
# DatabaseError Tests
# ============================================================================


class TestDatabaseError:
    """Test DatabaseError exception."""

    @patch("app.shared.logger.get_logger")
    def test_basic_database_error(self, mock_get_logger):
        """Test basic DatabaseError."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = DatabaseError("Query failed")

        assert exc.message == "Query failed"
        assert exc.category == ErrorCategory.DATABASE
        assert exc.error_code == ErrorCode.DATABASE_QUERY_ERROR

    @patch("app.shared.logger.get_logger")
    def test_database_connection_error_helper(self, mock_get_logger):
        """Test database_connection_error helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        original = ConnectionError("Connection refused")
        exc = database_connection_error("Timeout", original)

        assert "Database connection failed" in exc.message
        assert exc.error_code == ErrorCode.DATABASE_CONNECTION_ERROR
        assert exc.original_exception is original

    @patch("app.shared.logger.get_logger")
    def test_database_integrity_error_helper(self, mock_get_logger):
        """Test database_integrity_error helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = database_integrity_error("Foreign key violation")

        assert "Database integrity error" in exc.message
        assert exc.error_code == ErrorCode.DATABASE_INTEGRITY_ERROR


# ============================================================================
# AuthenticationError Tests
# ============================================================================


class TestAuthenticationError:
    """Test AuthenticationError exception."""

    @patch("app.shared.logger.get_logger")
    def test_basic_authentication_error(self, mock_get_logger):
        """Test basic AuthenticationError."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = AuthenticationError("Invalid credentials")

        assert exc.message == "Invalid credentials"
        assert exc.category == ErrorCategory.AUTHENTICATION
        assert exc.error_code == ErrorCode.INVALID_CREDENTIALS

    @patch("app.shared.logger.get_logger")
    def test_token_expired_helper(self, mock_get_logger):
        """Test token_expired helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = token_expired()

        assert "expired" in exc.message.lower()
        assert exc.error_code == ErrorCode.TOKEN_EXPIRED

    @patch("app.shared.logger.get_logger")
    def test_invalid_token_helper(self, mock_get_logger):
        """Test invalid_token helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = invalid_token()

        assert "Invalid" in exc.message
        assert exc.error_code == ErrorCode.TOKEN_INVALID

    @patch("app.shared.logger.get_logger")
    def test_authentication_required_helper(self, mock_get_logger):
        """Test authentication_required helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = authentication_required()

        assert "required" in exc.message.lower()
        assert exc.error_code == ErrorCode.AUTHENTICATION_REQUIRED


# ============================================================================
# AuthorizationError Tests
# ============================================================================


class TestAuthorizationError:
    """Test AuthorizationError exception."""

    @patch("app.shared.logger.get_logger")
    def test_basic_authorization_error(self, mock_get_logger):
        """Test basic AuthorizationError."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = AuthorizationError("Access denied")

        assert exc.message == "Access denied"
        assert exc.category == ErrorCategory.AUTHORIZATION
        assert exc.error_code == ErrorCode.INSUFFICIENT_PERMISSIONS

    @patch("app.shared.logger.get_logger")
    def test_access_denied_helper(self, mock_get_logger):
        """Test access_denied helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = access_denied(resource="Order", action="delete")

        assert "delete" in exc.message
        assert "Order" in exc.message
        assert exc.error_code == ErrorCode.ACCESS_DENIED
        assert exc.context["resource"] == "Order"
        assert exc.context["action"] == "delete"

    @patch("app.shared.logger.get_logger")
    def test_insufficient_permissions_helper(self, mock_get_logger):
        """Test insufficient_permissions helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = insufficient_permissions(required_role="admin")

        assert "admin" in exc.message
        assert exc.error_code == ErrorCode.INSUFFICIENT_PERMISSIONS
        assert exc.context["required_role"] == "admin"


# ============================================================================
# BusinessRuleError Tests
# ============================================================================


class TestBusinessRuleError:
    """Test BusinessRuleError exception."""

    @patch("app.shared.logger.get_logger")
    def test_basic_business_rule_error(self, mock_get_logger):
        """Test basic BusinessRuleError."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = BusinessRuleError("Invalid operation")

        assert exc.message == "Invalid operation"
        assert exc.category == ErrorCategory.BUSINESS_RULE
        assert exc.error_code == ErrorCode.BUSINESS_RULE_VIOLATION

    @patch("app.shared.logger.get_logger")
    def test_invalid_state_helper(self, mock_get_logger):
        """Test invalid_state helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = invalid_state("cancelled", "active")

        assert "cancelled" in exc.message
        assert exc.error_code == ErrorCode.INVALID_STATE
        assert exc.context["current_state"] == "cancelled"
        assert exc.context["expected_state"] == "active"

    @patch("app.shared.logger.get_logger")
    def test_operation_not_allowed_helper(self, mock_get_logger):
        """Test operation_not_allowed helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = operation_not_allowed("delete", "Order already shipped")

        assert "delete" in exc.message
        assert exc.error_code == ErrorCode.OPERATION_NOT_ALLOWED
        assert exc.context["operation"] == "delete"
        assert exc.context["reason"] == "Order already shipped"


# ============================================================================
# ExternalServiceError Tests
# ============================================================================


class TestExternalServiceError:
    """Test ExternalServiceError exception."""

    @patch("app.shared.logger.get_logger")
    def test_basic_external_service_error(self, mock_get_logger):
        """Test basic ExternalServiceError."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = ExternalServiceError("Payment API failed")

        assert exc.message == "Payment API failed"
        assert exc.category == ErrorCategory.EXTERNAL_SERVICE
        assert exc.error_code == ErrorCode.EXTERNAL_SERVICE_ERROR

    @patch("app.shared.logger.get_logger")
    def test_external_service_unavailable_helper(self, mock_get_logger):
        """Test external_service_unavailable helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = external_service_unavailable("PaymentAPI")

        assert "PaymentAPI" in exc.message
        assert exc.error_code == ErrorCode.EXTERNAL_SERVICE_UNAVAILABLE
        assert exc.context["service_name"] == "PaymentAPI"

    @patch("app.shared.logger.get_logger")
    def test_external_service_timeout_helper(self, mock_get_logger):
        """Test external_service_timeout helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = external_service_timeout("PaymentAPI", 30.0)

        assert "PaymentAPI" in exc.message
        assert "30.0" in exc.message
        assert exc.error_code == ErrorCode.EXTERNAL_SERVICE_TIMEOUT
        assert exc.context["service_name"] == "PaymentAPI"
        assert exc.context["timeout_seconds"] == 30.0


# ============================================================================
# InternalError Tests
# ============================================================================


class TestInternalError:
    """Test InternalError exception."""

    @patch("app.shared.logger.get_logger")
    def test_basic_internal_error(self, mock_get_logger):
        """Test basic InternalError."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = InternalError("Something went wrong")

        assert exc.message == "Something went wrong"
        assert exc.category == ErrorCategory.INTERNAL
        assert exc.error_code == ErrorCode.INTERNAL_ERROR

    @patch("app.shared.logger.get_logger")
    def test_configuration_error_helper(self, mock_get_logger):
        """Test configuration_error helper function."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        exc = configuration_error("DATABASE_URL", "Not set")

        assert "DATABASE_URL" in exc.message
        assert exc.error_code == ErrorCode.CONFIGURATION_ERROR
        assert exc.context["config_key"] == "DATABASE_URL"
        assert exc.context["details"] == "Not set"


# ============================================================================
# Error Category Tests
# ============================================================================


class TestErrorCategory:
    """Test ErrorCategory enum methods."""

    def test_is_client_error(self):
        """Test is_client_error method."""
        assert ErrorCategory.NOT_FOUND.is_client_error()
        assert ErrorCategory.VALIDATION.is_client_error()
        assert ErrorCategory.AUTHENTICATION.is_client_error()
        assert ErrorCategory.AUTHORIZATION.is_client_error()
        assert ErrorCategory.BUSINESS_RULE.is_client_error()

        assert not ErrorCategory.DATABASE.is_client_error()
        assert not ErrorCategory.INTERNAL.is_client_error()

    def test_is_server_error(self):
        """Test is_server_error method."""
        assert ErrorCategory.DATABASE.is_server_error()
        assert ErrorCategory.EXTERNAL_SERVICE.is_server_error()
        assert ErrorCategory.INTERNAL.is_server_error()

        assert not ErrorCategory.NOT_FOUND.is_server_error()
        assert not ErrorCategory.VALIDATION.is_server_error()
