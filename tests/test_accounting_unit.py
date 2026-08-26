"""Unit tests for the provider-neutral accounting service."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.accounting import accounting_api_router
from app.services.accounting.dependencies import get_accounting_operations
from app.services.accounting.functions import AccountingOperations
from app.services.accounting.models import AccountingStatus, DocumentUpdate
from app.services.admin.dependencies import require_admin
from app.shared.config.settings import Settings
from app.shared.exceptions import ValidationError


def _app(operations: AccountingOperations) -> FastAPI:
    app = FastAPI()
    app.include_router(accounting_api_router, prefix="/v1")
    app.dependency_overrides[require_admin] = lambda: {"sub": "admin"}
    app.dependency_overrides[get_accounting_operations] = lambda: operations
    return app


def test_document_list_forwards_admin_filters() -> None:
    operations = AsyncMock(spec=AccountingOperations)
    operations.list_documents.return_value = {
        "count": 0,
        "next": None,
        "previous": None,
        "results": [],
    }

    response = TestClient(_app(operations)).get(
        "/v1/admin/accounting/documents?query=invoice&tags=2&tags=3&page_size=25"
    )

    assert response.status_code == 200
    # "query", not "text": Paperless has no `text` filter and ignores unknown
    # names, so the old value made every search return the whole collection.
    operations.list_documents.assert_awaited_once_with(
        {"page": 1, "page_size": 25, "query": "invoice", "tags__id__all": "2,3"}
    )


@pytest.mark.asyncio
async def test_status_does_not_call_provider_unless_probe_requested() -> None:
    adapter = AsyncMock()
    operations = AccountingOperations(
        adapter, Settings(paperless_url="http://paperless", paperless_token="secret")
    )

    status = await operations.status()

    assert status == AccountingStatus(configured=True)
    adapter.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_document_update_only_sends_supplied_fields() -> None:
    adapter = AsyncMock()
    adapter.patch.return_value = {"id": 7, "title": "Invoice", "tags": []}
    operations = AccountingOperations(adapter, Settings())

    await operations.update_document(7, DocumentUpdate(title="Invoice"))

    adapter.patch.assert_awaited_once_with("documents/7/", {"title": "Invoice"})


@pytest.mark.asyncio
async def test_upload_limit_is_enforced_before_provider_call() -> None:
    adapter = AsyncMock()
    operations = AccountingOperations(adapter, Settings(paperless_max_upload_bytes=3))

    with pytest.raises(ValidationError):
        await operations.upload("invoice.pdf", "application/pdf", b"1234", {})

    adapter.post.assert_not_awaited()


def test_resource_crud_route_maps_frontend_name_to_paperless_name() -> None:
    operations = AsyncMock(spec=AccountingOperations)
    operations.create_resource.return_value = {"id": 4, "name": "Invoice"}

    response = TestClient(_app(operations)).post(
        "/v1/admin/accounting/resources/document-types", json={"name": "Invoice"}
    )

    assert response.status_code == 201
    operations.create_resource.assert_awaited_once()
