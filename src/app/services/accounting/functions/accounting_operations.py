"""Provider-neutral accounting document use cases."""

from typing import Any

from app.shared.config.settings import Settings
from app.shared.exceptions import ValidationError

from ..adapters import AccountingAdapter, Download
from ..models import AccountingStatus, BulkEditRequest, DocumentUpdate, ResourceWrite

RESOURCE_PATHS = {
    "tags": "tags",
    "correspondents": "correspondents",
    "document-types": "document_types",
    "storage-paths": "storage_paths",
    "custom-fields": "custom_fields",
}


class AccountingOperations:
    def __init__(self, adapter: AccountingAdapter, settings: Settings) -> None:
        self._adapter = adapter
        self._settings = settings

    @property
    def max_upload_bytes(self) -> int:
        """Maximum bytes the HTTP layer should read from one upload."""
        return self._settings.paperless_max_upload_bytes

    async def status(self, probe: bool = False) -> AccountingStatus:
        configured = bool(
            self._settings.paperless_url and self._settings.paperless_token
        )
        if not probe or not configured:
            return AccountingStatus(configured=configured)
        result = await self._adapter.get("status/")
        return AccountingStatus(
            configured=True,
            reachable=True,
            version=result.get("version") if isinstance(result, dict) else None,
        )

    async def list_documents(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._adapter.get("documents/", params)

    async def get_document(self, document_id: int) -> dict[str, Any]:
        return await self._adapter.get(f"documents/{document_id}/")

    async def update_document(
        self, document_id: int, payload: DocumentUpdate
    ) -> dict[str, Any]:
        return await self._adapter.patch(
            f"documents/{document_id}/",
            payload.model_dump(exclude_unset=True, mode="json"),
        )

    async def delete_document(self, document_id: int) -> None:
        await self._adapter.delete(f"documents/{document_id}/")

    async def upload(
        self, filename: str, content_type: str, content: bytes, fields: dict[str, Any]
    ) -> str:
        if len(content) > self._settings.paperless_max_upload_bytes:
            raise ValidationError(
                "Document exceeds the configured upload limit",
                context={"max_bytes": self._settings.paperless_max_upload_bytes},
            )
        result = await self._adapter.post(
            "documents/post_document/",
            data={key: value for key, value in fields.items() if value is not None},
            files={"document": (filename, content, content_type)},
        )
        return str(result)

    async def download(self, document_id: int, variant: str) -> Download:
        endpoint = {"original": "download", "preview": "preview", "thumbnail": "thumb"}[
            variant
        ]
        return await self._adapter.download(f"documents/{document_id}/{endpoint}/")

    async def bulk_edit(self, payload: BulkEditRequest) -> Any:
        return await self._adapter.post(
            "documents/bulk_edit/", json=payload.model_dump(mode="json")
        )

    async def list_tasks(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._adapter.get("tasks/", params)

    def _resource_path(self, resource: str) -> str:
        try:
            return RESOURCE_PATHS[resource]
        except KeyError as exc:
            raise ValidationError("Unsupported accounting resource") from exc

    async def list_resources(
        self, resource: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._adapter.get(f"{self._resource_path(resource)}/", params)

    async def create_resource(
        self, resource: str, payload: ResourceWrite
    ) -> dict[str, Any]:
        return await self._adapter.post(
            f"{self._resource_path(resource)}/",
            json=payload.model_dump(exclude_unset=True),
        )

    async def update_resource(
        self, resource: str, resource_id: int, payload: ResourceWrite
    ) -> dict[str, Any]:
        return await self._adapter.patch(
            f"{self._resource_path(resource)}/{resource_id}/",
            payload.model_dump(exclude_unset=True),
        )

    async def delete_resource(self, resource: str, resource_id: int) -> None:
        await self._adapter.delete(f"{self._resource_path(resource)}/{resource_id}/")
