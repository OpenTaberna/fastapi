# Mail Service

## Overview

The admin mail service provides a provider-neutral HTTP API for a future
webmail frontend. The current adapter uses IMAP for mailbox access and SMTP for
sending. Hosted and self-hosted standard mail servers can use the same adapter;
other providers can be integrated behind `MailAdapter`.

All routes are below `/v1/admin/mail` and require an administrator token issued
to an allowed admin frontend client.

## Architecture

The mail service follows the project's mini-API layering rules:

```text
HTTP request
    → router (HTTP validation and shared response envelope)
    → MailOperations (provider-neutral use case and audit logging)
    → MailAdapter (external protocol contract)
    → ImapSmtpMailAdapter (IMAP/SMTP implementation)
```

- `models/` contains provider-neutral Pydantic request and response schemas.
- `functions/` contains mailbox use cases and structured audit logging.
- `adapters/` contains external mail-server integration.
- `responses/` contains programmatically generated OpenAPI error examples.
- `routers/` contains only FastAPI and HTTP response concerns.

Message bodies, credentials, and recipient addresses are not written to audit
logs. Mutations record folder, UID, flag names, recipient counts, and generated
message identifiers where applicable.

## Response contract

Successful JSON endpoints use the shared `DataResponse[T]` model documented in
[`responses.md`](responses.md). Resource data is always located in `data`:

```json
{
  "success": true,
  "message": "Mail message retrieved",
  "timestamp": "2026-08-26T13:30:00Z",
  "request_id": null,
  "metadata": null,
  "data": {
    "uid": 1,
    "subject": "OpenTaberna development test"
  }
}
```

Errors use the shared `ErrorResponse` or `ValidationErrorResponse` through the
application's global exception handlers. Endpoint-specific `403`, `404`, `422`,
`500`, and `502` responses are declared in `responses/mail_docs.py`; examples
are serialized from the real shared response models to avoid schema drift.

Two response types are intentionally not wrapped:

- attachment downloads return their original binary content and media type;
- successful move, flag, and delete operations return `204 No Content`.

## Endpoints

| Method | Path | Successful response |
|---|---|---|
| `GET` | `/status` | `DataResponse[MailStatus]` |
| `GET` | `/folders` | `DataResponse[list[MailFolder]]` |
| `POST` | `/folders` | `DataResponse[MailFolder]` (`201`) |
| `GET` | `/folders/{folder}/messages` | `DataResponse[MailMessagePage]` |
| `GET` | `/folders/{folder}/messages/{uid}` | `DataResponse[MailMessage]` |
| `GET` | `/folders/{folder}/messages/{uid}/attachments/{part_id}` | Binary response |
| `POST` | `/messages` | `DataResponse[SendMailResponse]` |
| `POST` | `/folders/{folder}/messages/{uid}/move` | `204 No Content` |
| `PATCH` | `/folders/{folder}/messages/{uid}/flags` | `204 No Content` |
| `DELETE` | `/folders/{folder}/messages/{uid}` | `204 No Content` |
| `PATCH` | `/folders/{folder}` | `DataResponse[MailFolder]` |
| `DELETE` | `/folders/{folder}` | `204 No Content` |

## Folder management

Folder management is exposed through OpenTaberna rather than directly through
provider APIs. This keeps provider credentials on the backend, preserves
Keycloak admin authorization and audit logging, and lets the frontend work with
IMAP/SMTP or a future provider adapter without changing its API calls.

Create a folder:

```http
POST /v1/admin/mail/folders
```

```json
{"name": "Archive"}
```

Rename it:

```http
PATCH /v1/admin/mail/folders/Archive
```

```json
{"name": "Processed"}
```

Delete it:

```http
DELETE /v1/admin/mail/folders/Processed
```

`INBOX` is protected from creation, rename, and deletion by default. Additional
provider-specific folders can be protected with `MAIL_PROTECTED_FOLDERS`.

Message listing retains its IMAP-friendly offset and limit metadata inside the
`data` object:

```json
{
  "success": true,
  "message": "Mail messages retrieved",
  "timestamp": "2026-08-26T13:30:00Z",
  "request_id": null,
  "metadata": null,
  "data": {
    "messages": [],
    "total": 0,
    "offset": 0,
    "limit": 50
  }
}
```

## Development configuration

The development Compose stack includes GreenMail with SMTP on port `3025`,
IMAP on `3143`, and its web interface on `8081`. Configure the API with the
`MAIL_*` variables listed in `.env.example`.

Run unit tests with:

```bash
pytest -q tests/test_mail_unit.py
```

Run the opt-in GreenMail round-trip integration test with:

```bash
docker compose -f docker-compose.dev.yml up -d opentaberna-mail
RUN_MAIL_INTEGRATION_TESTS=1 pytest -q tests/test_mail_integration.py
```
