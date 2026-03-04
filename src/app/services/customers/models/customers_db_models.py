"""
Customers Database Models

SQLAlchemy ORM models for the customers service.
These define the DB schema only — no business logic lives here.
"""

from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base, TimestampMixin


class CustomerDB(Base, TimestampMixin):
    """
    Customer database model.

    One customer per Keycloak user. Created automatically on first
    authenticated request via GET /customers/me.

    Columns:
        id:                 Internal UUID primary key.
        keycloak_user_id:   The 'sub' claim from the Keycloak JWT. Unique.
        email:              Customer email address. Unique.
        first_name:         Given name.
        last_name:          Family name.
        created_at:         Inherited from TimestampMixin.
        updated_at:         Inherited from TimestampMixin.
    """

    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Internal unique identifier",
    )

    keycloak_user_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        doc="Keycloak subject claim (sub) — links DB record to identity provider",
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        doc="Customer email address",
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Given name",
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Family name",
    )

    def __repr__(self) -> str:
        return (
            f"CustomerDB(id={self.id}, email={self.email!r}, "
            f"keycloak_user_id={self.keycloak_user_id!r})"
        )


class AddressDB(Base, TimestampMixin):
    """
    Address database model.

    A customer may have multiple addresses. At most one may be the default.

    Columns:
        id:          Internal UUID primary key.
        customer_id: FK → customers.id.
        street:      Street name and house number.
        city:        City name.
        zip_code:    Postal / ZIP code.
        country:     ISO 3166-1 alpha-2 country code (e.g. 'DE').
        is_default:  Whether this is the customer's default shipping address.
        created_at:  Inherited from TimestampMixin.
        updated_at:  Inherited from TimestampMixin.
    """

    __tablename__ = "addresses"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Internal unique identifier",
    )

    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="FK to the owning customer",
    )

    street: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Street name and house number",
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="City name",
    )

    zip_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Postal / ZIP code",
    )

    country: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        doc="ISO 3166-1 alpha-2 country code (e.g. 'DE')",
    )

    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether this is the customer's default shipping address",
    )

    def __repr__(self) -> str:
        return (
            f"AddressDB(id={self.id}, customer_id={self.customer_id}, "
            f"city={self.city!r}, country={self.country!r})"
        )
