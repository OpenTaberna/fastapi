"""Async Paperless-ngx REST adapter."""

from typing import Any

import httpx

from app.shared.config.settings import Settings
from app.shared.exceptions import ExternalServiceError, NotFoundError, ValidationError

from .interface import AccountingAdapter, Download


class PaperlessAccountingAdapter(AccountingAdapter):
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.paperless_url.rstrip("/")
        self._token = settings.paperless_token
        self._timeout = settings.paperless_timeout_seconds

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Token {self._token}"},
            timeout=self._timeout,
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self._base_url or not self._token:
            raise ExternalServiceError(
                "Accounting service is not configured",
                context={"provider": "paperless_ngx"},
            )
        try:
            async with self._client() as client:
                response = await client.request(
                    method, f"/api/{path.lstrip('/')}", **kwargs
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "Paperless-ngx is unavailable",
                context={"provider": "paperless_ngx"},
                original_exception=exc,
            ) from exc
        if response.status_code == 404:
            raise NotFoundError("Accounting resource not found")
        if response.status_code in {400, 409, 422}:
            raise ValidationError(
                "Paperless-ngx rejected the request",
                context={"provider_status": response.status_code},
            )
        if response.is_error:
            raise ExternalServiceError(
                "Paperless-ngx request failed",
                context={"provider_status": response.status_code},
            )
        return response

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return (await self._request("GET", path, params=params)).json()

    async def post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> Any:
        return (
            await self._request("POST", path, json=json, data=data, files=files)
        ).json()

    async def patch(self, path: str, json: dict[str, Any]) -> Any:
        return (await self._request("PATCH", path, json=json)).json()

    async def delete(self, path: str) -> None:
        await self._request("DELETE", path)

    async def download(self, path: str) -> Download:
        response = await self._request("GET", path)
        disposition = response.headers.get("content-disposition", "")
        filename = None
        if "filename=" in disposition:
            filename = disposition.split("filename=", 1)[1].strip('" ')
        return Download(
            content=response.content,
            content_type=response.headers.get(
                "content-type", "application/octet-stream"
            ),
            filename=filename,
        )
