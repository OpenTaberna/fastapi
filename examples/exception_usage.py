"""
Exception Module Usage Examples.

Demonstrates real-world usage patterns of the exception module.
"""

from typing import Optional
from app.shared.exceptions import (
    # Exception classes
    NotFoundError,
    ValidationError,
    DatabaseError,
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError,
    # Helper functions
    entity_not_found,
    missing_field,
    invalid_format,
    duplicate_entry,
    constraint_violation,
    database_connection_error,
    token_expired,
    access_denied,
    insufficient_permissions,
    invalid_state,
    operation_not_allowed,
)


# ============================================================================
# Example 1: Basic CRUD Operations
# ============================================================================


def get_user_by_id(user_id: int):
    """Get user by ID - demonstrates NotFoundError."""
    # Simulate database query
    user = None  # db.query(User).filter(User.id == user_id).first()

    if not user:
        raise entity_not_found("User", user_id)

    return user


def create_user(email: str, password: str, name: Optional[str] = None):
    """Create user - demonstrates validation errors."""
    # Validate required fields
    if not email:
        raise missing_field("email")

    if not password:
        raise missing_field("password")

    # Validate email format
    if "@" not in email:
        raise invalid_format("email", "valid email address")

    # Check for duplicate email
    existing_user = None  # db.query(User).filter(User.email == email).first()
    if existing_user:
        raise duplicate_entry("User", "email", email)

    # Validate password strength
    if len(password) < 8:
        raise constraint_violation(
            "password_length", "Password must be at least 8 characters"
        )

    # Create user...
    return {"id": 1, "email": email, "name": name}


# ============================================================================
# Example 2: Database Operations
# ============================================================================


def connect_to_database(host: str, port: int):
    """Connect to database - demonstrates DatabaseError."""
    try:
        # Simulate connection
        # connection = psycopg2.connect(host=host, port=port)
        raise ConnectionError("Connection refused")
    except ConnectionError as e:
        raise database_connection_error(
            f"Failed to connect to {host}:{port}", original_exception=e
        )


def execute_query(query: str):
    """Execute database query - demonstrates error wrapping."""
    try:
        # Simulate query execution
        # cursor.execute(query)
        pass
    except Exception as e:
        raise DatabaseError(
            "Query execution failed",
            context={"query": query[:100]},  # First 100 chars
            original_exception=e,
        )


# ============================================================================
# Example 3: Authentication & Authorization
# ============================================================================


def verify_token(token: str) -> dict:
    """Verify authentication token."""
    if not token:
        raise AuthenticationError(
            "Authentication token required", context={"header": "Authorization"}
        )

    # Simulate token verification
    if token == "expired":
        raise token_expired()

    if token != "valid":
        raise AuthenticationError(
            "Invalid authentication token", context={"token_prefix": token[:10]}
        )

    return {"user_id": 1, "role": "user"}


def check_admin_permission(user: dict):
    """Check if user has admin permissions."""
    if user.get("role") != "admin":
        raise insufficient_permissions(required_role="admin")


def delete_order(order_id: int, user: dict):
    """Delete order - demonstrates authorization."""
    # Get order
    order = {"id": order_id, "user_id": 123, "status": "shipped"}

    # Check if user owns the order
    if order["user_id"] != user["id"] and user["role"] != "admin":
        raise access_denied(resource="Order", action="delete")

    # Business rule: can't delete shipped orders
    if order["status"] == "shipped":
        raise operation_not_allowed("delete", "Cannot delete shipped orders")

    # Delete order...
    return {"message": "Order deleted"}


# ============================================================================
# Example 4: Business Rules
# ============================================================================


def cancel_order(order_id: int):
    """Cancel order - demonstrates business rule validation."""
    # Get order
    order = {"id": order_id, "status": "delivered"}

    # Can only cancel pending or processing orders
    if order["status"] not in ["pending", "processing"]:
        raise invalid_state(
            current_state=order["status"], expected_state="pending or processing"
        )

    # Update order status...
    return {"message": "Order cancelled"}


def process_refund(order_id: int, amount: float):
    """Process refund - demonstrates constraint validation."""
    order = {"id": order_id, "total": 100.0, "refunded": 20.0}

    # Validate refund amount
    if amount <= 0:
        raise constraint_violation("amount_positive", "Refund amount must be positive")

    # Check if refund exceeds remaining amount
    remaining = order["total"] - order["refunded"]
    if amount > remaining:
        raise constraint_violation(
            "refund_exceeds_remaining",
            f"Refund amount ({amount}) exceeds remaining amount ({remaining})",
        )

    # Process refund...
    return {"message": "Refund processed"}


# ============================================================================
# Example 5: FastAPI Router Integration
# ============================================================================


def fastapi_router_example():
    """
    Example of how to use exceptions in FastAPI routers.

    Note: This is pseudo-code showing the pattern.
    """

    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from app.shared.exceptions import AppException

    app = FastAPI()

    # Global exception handler
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        """Handle all application exceptions."""
        # Map category to HTTP status code
        status_map = {
            "not_found": 404,
            "validation": 422,
            "authentication": 401,
            "authorization": 403,
            "business_rule": 400,
            "database": 500,
            "external_service": 502,
            "internal": 500,
        }

        status_code = status_map.get(exc.category.value, 500)

        return JSONResponse(status_code=status_code, content=exc.to_dict())

    # Router endpoint
    @app.get("/users/{user_id}")
    async def get_user(user_id: int):
        """Get user endpoint."""
        # Just raise the exception - it will be caught and handled
        user = get_user_by_id(user_id)
        return user

    @app.post("/users")
    async def create_user_endpoint(email: str, password: str):
        """Create user endpoint."""
        user = create_user(email, password)
        return user


# ============================================================================
# Example 6: Service Layer Pattern
# ============================================================================


class UserService:
    """User service demonstrating exception usage in service layer."""

    def get(self, user_id: int):
        """Get user by ID."""
        user = None  # self.repository.find_by_id(user_id)

        if not user:
            raise entity_not_found("User", user_id)

        return user

    def create(self, email: str, password: str):
        """Create new user."""
        # Validation
        if not email or not password:
            raise ValidationError(
                "Email and password are required",
                context={"email": bool(email), "password": bool(password)},
            )

        # Check duplicate
        existing = None  # self.repository.find_by_email(email)
        if existing:
            raise duplicate_entry("User", "email", email)

        # Create user...
        return {"id": 1, "email": email}

    def update(self, user_id: int, **kwargs):
        """Update user."""
        user = self.get(user_id)

        # Update fields...
        return user

    def delete(self, user_id: int, current_user: dict):
        """Delete user."""
        user = self.get(user_id)

        # Authorization check
        if user["id"] != current_user["id"] and current_user["role"] != "admin":
            raise access_denied(resource="User", action="delete")

        # Delete user...
        return {"message": "User deleted"}


# ============================================================================
# Example 7: Custom Exception
# ============================================================================


class PaymentProcessingError(BusinessRuleError):
    """Custom exception for payment processing."""

    def __init__(
        self,
        message: str = "Payment processing failed",
        payment_id: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        context = {}
        if payment_id:
            context["payment_id"] = payment_id
        if reason:
            context["reason"] = reason

        super().__init__(message=message, context=context if context else None)


def process_payment(payment_id: str, amount: float):
    """Process payment - demonstrates custom exception."""
    if amount <= 0:
        raise PaymentProcessingError(
            "Invalid payment amount",
            payment_id=payment_id,
            reason="Amount must be positive",
        )

    # Simulate payment processing
    success = False

    if not success:
        raise PaymentProcessingError(
            "Payment gateway error", payment_id=payment_id, reason="Gateway timeout"
        )

    return {"payment_id": payment_id, "status": "completed"}


# ============================================================================
# Run Examples
# ============================================================================


if __name__ == "__main__":
    print("Exception Module Examples")
    print("=" * 50)

    # Example 1: NotFoundError
    print("\n1. NotFoundError example:")
    try:
        get_user_by_id(999)
    except NotFoundError as e:
        print(f"   {e}")
        print(f"   Context: {e.context}")

    # Example 2: ValidationError
    print("\n2. ValidationError example:")
    try:
        create_user("invalid-email", "short")
    except ValidationError as e:
        print(f"   {e}")
        print(f"   Error code: {e.error_code.value}")

    # Example 3: DatabaseError
    print("\n3. DatabaseError example:")
    try:
        connect_to_database("localhost", 5432)
    except DatabaseError as e:
        print(f"   {e}")
        print(f"   Original error: {e.original_exception}")

    # Example 4: AuthorizationError
    print("\n4. AuthorizationError example:")
    try:
        user = {"id": 1, "role": "user"}
        check_admin_permission(user)
    except AuthorizationError as e:
        print(f"   {e}")
        print(f"   Context: {e.context}")

    # Example 5: BusinessRuleError
    print("\n5. BusinessRuleError example:")
    try:
        cancel_order(123)
    except BusinessRuleError as e:
        print(f"   {e}")
        print(f"   Context: {e.context}")

    print("\n" + "=" * 50)
    print("All examples completed successfully!")
