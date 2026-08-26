"""
Unit tests for the Paperless document filter mapping.

Paperless ignores filter names it does not recognise instead of rejecting them,
so a wrong name does not produce an error — the request succeeds and returns the
entire collection. A search that quietly matches everything looks like a search
that worked.

That is not hypothetical: `query` was mapped onto `text`, which Paperless has
never had, and `?query=Barolo` returned all 183 seeded documents instead of 25.
"""

import pytest

from app.services.accounting.functions import (
    FULL_TEXT_FILTER,
    PAPERLESS_FILTERS,
    build_document_filters,
)


def test_full_text_search_uses_a_filter_paperless_honours():
    """
    The regression itself. `text` is accepted by the HTTP layer, matched by
    nothing, and therefore returns everything.
    """
    filters = build_document_filters(page=1, page_size=50, query="Barolo")

    assert filters[FULL_TEXT_FILTER] == "Barolo"
    assert "text" not in filters, (
        "`text` is not a Paperless filter; it matches everything"
    )


def test_the_full_text_filter_is_the_documented_one():
    assert FULL_TEXT_FILTER == "query"


def test_every_filter_sent_is_one_paperless_recognises():
    """
    Guards the whole mapping, not just search. Any name added here that
    Paperless does not know widens the result set silently.
    """
    filters = build_document_filters(
        page=2,
        page_size=25,
        query="Champagne",
        correspondent=3,
        document_type=1,
        storage_path=2,
        tags=[4, 5],
        ordering="-created",
    )

    unknown = set(filters) - PAPERLESS_FILTERS
    assert not unknown, f"filters Paperless would ignore: {sorted(unknown)}"


def test_unset_parameters_are_omitted_entirely():
    """
    Sending `correspondent__id=None` would filter on the literal string "None"
    and return nothing — the opposite failure, equally silent.
    """
    filters = build_document_filters(page=1, page_size=50)

    assert filters == {"page": 1, "page_size": 50}
    assert "correspondent__id" not in filters
    assert FULL_TEXT_FILTER not in filters


def test_tags_are_sent_as_a_comma_separated_all_match():
    filters = build_document_filters(page=1, page_size=50, tags=[7, 9, 11])
    assert filters["tags__id__all"] == "7,9,11"


def test_an_empty_tag_list_is_not_sent():
    """An empty `tags__id__all=` would match nothing rather than everything."""
    filters = build_document_filters(page=1, page_size=50, tags=[])
    assert "tags__id__all" not in filters


@pytest.mark.parametrize(
    "field,value,expected_key",
    [
        ("correspondent", 3, "correspondent__id"),
        ("document_type", 1, "document_type__id"),
        ("storage_path", 2, "storage_path__id"),
    ],
)
def test_id_filters_carry_the_double_underscore_suffix(field, value, expected_key):
    """Paperless filters relations by `<field>__id`; the bare name is ignored."""
    filters = build_document_filters(page=1, page_size=50, **{field: value})

    assert filters[expected_key] == value
    assert field not in filters
