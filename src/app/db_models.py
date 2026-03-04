"""
Database Model Registry

Imports ALL SQLAlchemy ORM models so that Base.metadata knows about every
table. This module must be imported before calling Base.metadata.create_all().

Why this file exists:
    SQLAlchemy's Base.metadata only knows about a table after its ORM class
    has been imported. If a model is never imported, its table is never created.
    Centralising all imports here means you only need to import this one module
    to guarantee that create_all() sees the full schema.

Usage:
    import app.db_models  # noqa: F401  — side-effect import
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
"""

# Item store (partner service)
from app.services.crud_item_store.models.item_db_models import ItemDB  # noqa: F401

# Customers
from app.services.customers.models.customers_db_models import AddressDB, CustomerDB  # noqa: F401

# Inventory
from app.services.inventory.models.inventory_db_models import InventoryItemDB, StockReservationDB  # noqa: F401

# Orders
from app.services.orders.models.orders_db_models import OrderDB, OrderItemDB  # noqa: F401

# Payments
from app.services.payments.models.payments_db_models import PaymentDB  # noqa: F401

# Webhooks
from app.services.webhooks.models.webhooks_db_models import WebhookEventDB  # noqa: F401

# Shipments
from app.services.shipments.models.shipments_db_models import ShipmentDB  # noqa: F401
