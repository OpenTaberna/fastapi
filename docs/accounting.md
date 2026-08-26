# Accounting documents

OpenTaberna exposes an admin-only, provider-neutral document API at
`/v1/admin/accounting`. Paperless-ngx performs storage, OCR, full-text search,
classification, and task processing; its credentials never reach the frontend.

## Development setup

`docker-compose.dev.yml` starts Paperless at `http://localhost:8010`. Sign in with
`PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` (both default to `admin` for
local development), create an API token under **My Profile**, and set
`PAPERLESS_TOKEN` in the API `.env`. Production deployments must set unique
`PAPERLESS_SECRET_KEY`, database password, administrator credentials, and a
fixed trusted Paperless image version.

API configuration:

- `PAPERLESS_URL` — internal Paperless base URL
- `PAPERLESS_TOKEN` — token used only by the backend adapter
- `PAPERLESS_TIMEOUT_SECONDS` — upstream timeout (default 30)
- `PAPERLESS_MAX_UPLOAD_BYTES` — upload limit (default 50 MiB)

## Admin frontend surface

- `GET /status` — configuration and optional connectivity probe
- `GET|POST /documents`, `GET|PATCH|DELETE /documents/{id}`
- `GET /documents/{id}/file?variant=original|preview|thumbnail`
- `POST /documents/bulk-edit`
- `GET /tasks` — poll asynchronous ingestion and bulk operations
- CRUD `/resources/{type}` for tags, correspondents, document types, storage
  paths, and custom fields

Every route requires the existing Keycloak admin role and admin-client token.
Uploads return `202` with a task ID; the frontend should poll `/tasks?task_id=...`
until Paperless reports completion or failure.
