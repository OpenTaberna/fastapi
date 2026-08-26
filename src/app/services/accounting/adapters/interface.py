"""Provider boundary for accounting document management."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Download:
    content: bytes
    content_type: str
    filename: str | None


class AccountingAdapter(ABC):
    @abstractmethod
    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any: ...

    @abstractmethod
    async def post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> Any: ...

    @abstractmethod
    async def patch(self, path: str, json: dict[str, Any]) -> Any: ...

    @abstractmethod
    async def delete(self, path: str) -> None: ...

    @abstractmethod
    async def download(self, path: str) -> Download: ...
