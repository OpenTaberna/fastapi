# TODO — OpenTaberna API Implementation Roadmap

Ordered by dependency. Each phase builds on the previous.  
CRUD for items (`crud-item-store`) is handled by a partner and not listed here.

**Status:** Phases 0–3 are complete and merged. Phase 4 (operational hardening) is the
current work. Auth is the one cross-cutting gap: every protected route still uses a
development header shim rather than Keycloak — see the Auth section below.

---

## Shared Infrastructure (already done ✅)

- [x] Config module (`shared/config/`)
- [x] Logger module (`shared/logger/`)
- [x] Exceptions module (`shared/exceptions/`)
- [x] Responses module (`shared/responses/`)
- [x] Database module (`shared/database/`) — async SQLAlchemy 2.0, BaseRepository, session, health
- [ ] Keycloak auth (`authorize/keycloak.py`) — module exists but is unwired legacy code:
      it reads `os.getenv` directly instead of `shared/config`, and nothing imports it.
      Every protected route currently uses a header shim instead. See **Auth** below.
- [x] FastAPI app skeleton (`main.py`)

---

## Model Convention

Each entity has **two** model layers, and they are deliberately separate:

- **ORM models** — `*_db_models.py`, mapping the table with SQLAlchemy 2.0
  `DeclarativeBase`. `shared/database/base.py` defines the shared `Base` and
  `TimestampMixin`. These own the schema.
- **Pydantic schemas** — `*_models.py`, owning the API contract: validation of input and
  shape of output.

```
services/customers/models/
├── customers_db_models.py     # CustomerDB(Base), AddressDB(Base)  — the tables
└── customers_models.py        # CustomerBase / Create / Update / Response — the API
```

Response models set `model_config = ConfigDict(from_attributes=True)` so an ORM row maps
straight through `Model.model_validate(row)`. Timestamps (`created_at`, `updated_at`) and
primary keys appear on response models only, never on Create/Update schemas.

Data access goes through `BaseRepository` (`shared/database/repository.py`), which is
typed to the **ORM** model. Business rules live in the repository, not in routers.

### Schema creation

There is no Alembic setup. `src/app/db_models.py` imports every ORM module so
`Base.metadata.create_all()` sees the full schema, and the app creates tables on startup.
This is fine for development but does not handle column changes to existing tables —
introducing Alembic is a real outstanding task, tracked in Phase 4.

---

## Phase 0 — Domain Models & DB Schema ✅

> Complete. Tables are created by `Base.metadata.create_all()` on startup, not Alembic.

### 0.1 Customer & Address ✅

- [x] `CustomerDB`, `AddressDB` ORM models (`services/customers/models/customers_db_models.py`)
- [x] `CustomerBase` / `Create` / `Update` / `Response` and the Address equivalents
- [x] `CustomerRepository`, `AddressRepository` — includes the one-default-address rule

### 0.2 Inventory ✅

- [x] `InventoryItemDB`, `StockReservationDB` ORM models
- [x] `InventoryItem*` and `StockReservation*` Pydantic schemas, `ReservationStatus` enum
- [x] `InventoryRepository` — enforces `on_hand >= reserved` and blocks deleting an item
      that still has active reservations
- [x] `StockReservationRepository`

### 0.3 Order & OrderItem ✅

- [x] `OrderStatus` enum: `DRAFT` → `PENDING_PAYMENT` → `PAID` → `READY_TO_SHIP` → `SHIPPED` → `CANCELLED`
- [x] `OrderDB`, `OrderItemDB` ORM models with `deleted_at` soft delete
- [x] Order and OrderItem Pydantic schemas
- [x] `OrderRepository`, `OrderItemRepository`

### 0.4 Payment ✅

- [x] `PaymentStatus` (PENDING / SUCCEEDED / FAILED / REFUNDED) and `PaymentProvider` enums
- [x] `PaymentDB` ORM model + Pydantic schemas
- [x] `PaymentRepository`

### 0.5 Webhook Event Inbox ✅

- [x] `WebhookEventDB` ORM model, unique on `(provider, event_id)` for idempotency
- [x] `WebhookEventRepository`

### 0.6 Shipment ✅

- [x] `Carrier` (DHL / MANUAL) and `ShipmentStatus` (PENDING / LABEL_CREATED / HANDED_OVER) enums
- [x] `ShipmentDB` ORM model + Pydantic schemas
- [x] `ShipmentRepository`

---

## Phase 1 — Checkout & Payment (`services/orders/`) ✅

### 1.1 Cart / Draft Order API ✅

- [x] `POST /v1/orders` — create draft order with price snapshot per line
- [x] `GET /v1/orders/{id}` — customer-scoped retrieval
- [x] `DELETE /v1/orders/{id}` — cancel a draft order
- [x] Router registered in `main.py`

### 1.2 Inventory Reservation ✅

- [x] `reserve_inventory` — atomic check-and-reserve in one transaction
- [x] `release_reservation` — RELEASED, decrement `reserved`
- [x] `commit_reservation` — COMMITTED, decrement `on_hand` + `reserved`
- [x] `expire_reservations` — sweep releasing TTL-exceeded reservations
- [x] `reservation_ttl_minutes` in `Settings`
- [ ] **Not scheduled yet.** `expire_reservations` exists as a function but nothing calls
      it periodically — see Phase 4.2.

### 1.3 Checkout Endpoint ✅

- [x] `POST /v1/orders/{id}/checkout` — `DRAFT` → `PENDING_PAYMENT`, reserves stock,
      creates the payment intent, returns the client secret

### 1.4 PSP Integration ✅

- [x] `PaymentProviderAdapter` interface + `StripeAdapter`
- [x] `stripe_secret_key`, `stripe_webhook_secret`, `stripe_payment_methods` in `Settings`

### 1.5 Webhook Endpoint ✅

- [x] `POST /v1/webhooks/stripe` — raw body, signature verified before parsing
- [x] Idempotency via the `webhook_events` inbox
- [x] `payment_intent.succeeded` → Payment SUCCEEDED, Order PAID, commit reservation
- [x] `payment_intent.payment_failed` → Payment FAILED, Order CANCELLED, release reservation
- [x] Router registered in `main.py`

---

## Phase 2 — Admin Fulfillment (`services/admin/`) ✅

### 2.1 Admin Order Management ✅

- [x] `GET /v1/admin/orders` — paginated, filterable by status
- [x] `GET /v1/admin/orders/{id}` — detail with items, customer, address, payment, shipment
- [x] `PATCH /v1/admin/orders/{id}/status` — manual override, reason written to the audit log

### 2.2 Pick & Pack Documents ✅

- [x] `GET /v1/admin/orders/{id}/packing-slip` — print-friendly HTML
- [x] `GET /v1/admin/orders/pick-list` — batch pick list aggregated by SKU across PAID orders
- [x] All user-controlled values HTML-escaped before interpolation

### 2.3 Manual Shipment Marking ✅

- [x] `POST /v1/admin/orders/{id}/shipments` — create shipment, Order → `READY_TO_SHIP`
- [x] `POST /v1/admin/orders/{id}/ship` — Order → `SHIPPED`, sends the tracking email

### 2.4 Customer Notification Email ✅

- [x] `functions/send_tracking_email.py` — multipart text + HTML, HTML part escaped
- [x] `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `email_from` in `Settings`
- [x] Blocking SMTP wrapped in `asyncio.to_thread`; empty `smtp_host` skips sending in dev
- [ ] Optional: swap `smtplib` for `aiosmtplib` and move the body to a template

---

## Phase 3 — Automated Label Generation (`services/fulfillment/`) ✅

### 3.1 Background Job System ✅

- [x] ARQ worker (`src/app/worker.py`, `worker_main.py`), Redis-backed
- [x] `create_label` job with retries, exponential backoff and a dead-letter hook
- [x] `arq_max_jobs`, `arq_job_timeout`, `arq_max_tries` in `Settings`

### 3.2 Carrier Abstraction Layer ✅

- [x] `CarrierAdapter` interface returning `LabelResult`
- [x] `ManualCarrierAdapter`

### 3.3 DHL Adapter ✅

- [x] `DhlAdapter(CarrierAdapter)` against the DHL Parcel DE Shipping API
- [x] `dhl_*` settings incl. billing number and default label format
- [x] Labels stored in MinIO via `StorageAdapter`; `storage_*` settings
- [x] DHL errors raise `CarrierError`

### 3.4 Admin Label Workflow ✅

- [x] `POST /v1/admin/orders/{id}/label` — trigger or re-trigger label creation
- [x] `GET /v1/admin/orders/{id}/label` — download the stored label
- [x] Idempotency guard: a shipment that already has a tracking number is never sent to
      the carrier again, so a re-delivered job cannot buy a second label

### 3.5 Outbox Pattern ✅

- [x] `OutboxEventDB` + `OutboxRepository`
- [x] Webhook handler inserts an outbox row in the same transaction as the order update
- [x] `poll_outbox` cron sweeps PENDING rows into ARQ, honouring `outbox_poll_interval`
- [x] Attempt ceiling: past `outbox_max_attempts` a row is marked `FAILED` and skipped.
      `FAILED` (never reached the queue) is deliberately distinct from `DEAD` (ran and
      exhausted retries); `list_failed()` gives maintainers the first category

---

## Customers & Inventory APIs ✅

> Not in the original plan; added alongside Phases 2–3.

- [x] `GET`/`PATCH /v1/customers/me` — profile, auto-created on first call
- [x] `GET`/`POST`/`PATCH`/`DELETE /v1/customers/me/addresses` — address management
- [x] Full admin CRUD for inventory under `/v1/admin/inventory`

---

## Auth — the current gap

Every protected route uses a development header shim. This is the single largest piece of
outstanding work, and it is deliberately isolated so the swap touches few files.

- [ ] Replace `X-Keycloak-User-ID` with a validated JWT — `services/customers/dependencies.py`
      (`get_keycloak_id`, `get_creation_claims`). Tracked in #16.
- [ ] Replace `X-Admin-Key` with a Keycloak `role=admin` check — `services/admin/dependencies.py`
      (`require_admin`, now shared by the admin and inventory services).
- [ ] Rework `authorize/keycloak.py`: it reads `os.getenv` directly rather than
      `shared/config`, and nothing imports it. Both shims should end up there.

---

## Phase 4 — Operational Hardening

> Current focus. Nothing in this phase is on `main` yet, apart from the one item marked
> done in 4.5.

### 4.1 Observability

- [ ] Correlation ID middleware injecting `X-Request-ID` into the log context
- [ ] Structured log fields (`order_id`, `payment_id`, `user_id`) on all relevant statements
- [ ] Health endpoints: `GET /health` (liveness) and `GET /health/ready` (DB + Redis)
- [ ] Prometheus metrics endpoint (optional)

### 4.2 Reservation Expiry Job

- [ ] Schedule the existing `expire_reservations` as an ARQ cron job — the function is
      written and tested, only the schedule is missing
- [ ] Alert on repeated expiry failures

### 4.3 Payment Reversals / Refunds

- [ ] Handle `charge.refunded` and `payment_intent.canceled` webhooks
- [ ] Payment → REFUNDED, Order → CANCELLED, release the reservation if not yet committed
- [ ] If already shipped: create a `Refund` record and flag for manual review
- [ ] Note: `PaymentStatus.REFUNDED` already exists, but nothing sets it

### 4.4 Returns & RMA

- [ ] `ReturnStatus` enum: REQUESTED / APPROVED / RECEIVED / REFUNDED
- [ ] `Return` ORM model + schemas
- [ ] `POST /v1/orders/{id}/returns` — customer requests a return
- [ ] `PATCH /v1/admin/returns/{id}` — admin approves and processes

### 4.5 Security Hardening

- [x] `secret_key` startup validation rejects the default in production
- [ ] Restrict CORS — `main.py` still sets `origins = ["*"]`
- [ ] Rate limiting, at minimum on the webhook endpoint
- [ ] Enable Trivy/Bandit as *blocking* checks — both are `continue-on-error: true`, so
      findings never fail the build

### 4.6 Schema Migrations

- [ ] Introduce Alembic. `create_all()` cannot alter existing tables, so any column change
      currently requires dropping the database — unacceptable once there is real data.

---

## Cross-Cutting Tasks (do as you go)

- [x] Register every new service router in `main.py`
- [x] Keep `Settings` the single source of truth for env vars — no hardcoded values
- [x] Use `shared/exceptions/` for all error cases — never raw `HTTPException` in business logic
- [x] Use `shared/responses/` factory helpers in routers
- [ ] Write pytest tests for every new service module (mirror `tests/` structure) — held so
      far; keep it that way
- [ ] Document new env vars in **both** `.env.example` and `docs/config.md`
- [ ] Commit with LF line endings and run `ruff format` — the CI lint job is
      `continue-on-error`, so it will not catch drift for you
