"""
Translate this API's document query parameters into Paperless filter names.

Extracted from the router so it can be tested without a running Paperless. That
matters more than it sounds: Paperless **ignores** filter names it does not
recognise rather than rejecting them, so a wrong name does not fail — it returns
the entire collection and looks like a search that matched a lot.

That is exactly what happened with `text`, which Paperless has never had.
"""

from __future__ import annotations

from typing import Any

# Filters this service sends, and what each means upstream. Anything not in
# here is a name Paperless would silently discard.
FULL_TEXT_FILTER = "query"

PAPERLESS_FILTERS: frozenset[str] = frozenset(
    {
        "page",
        "page_size",
        "ordering",
        FULL_TEXT_FILTER,
        "correspondent__id",
        "document_type__id",
        "storage_path__id",
        "tags__id__all",
    }
)


def build_document_filters(
    *,
    page: int,
    page_size: int,
    query: str | None = None,
    correspondent: int | None = None,
    document_type: int | None = None,
    storage_path: int | None = None,
    tags: list[int] | None = None,
    ordering: str | None = None,
) -> dict[str, Any]:
    """
    Build the upstream query string, dropping anything unset.

    `query` becomes Paperless' `query`, which searches the OCR'd content and the
    title. It is deliberately not `text`: that name is accepted by the HTTP
    layer, matched by nothing, and therefore returns every document.
    """
    candidates: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        FULL_TEXT_FILTER: query,
        "correspondent__id": correspondent,
        "document_type__id": document_type,
        "storage_path__id": storage_path,
        "tags__id__all": ",".join(map(str, tags)) if tags else None,
        "ordering": ordering,
    }
    return {key: value for key, value in candidates.items() if value is not None}
