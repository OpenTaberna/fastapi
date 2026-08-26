"""
Unit tests for storefront analytics — schema validation, no DB, no network.

The ingest endpoint is public, so its schema is a security boundary rather than
a convenience. These pin the parts that keep it one.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.services.storefront_analytics.models import (
    MAX_EVENTS_PER_BATCH,
    StorefrontEventBatch,
    StorefrontEventInput,
    StorefrontEventType,
)


def _event(**overrides) -> dict:
    base = {
        "session_id": "abcdefgh1234",
        "event_type": "page_view",
        "occurred_at": datetime.now(UTC),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Query strings are where personal data arrives by accident
# ---------------------------------------------------------------------------


def test_query_string_is_stripped_before_storage():
    """
    An email in a share link, a token in a redirect — a query string is how PII
    reaches an analytics table without anyone deciding to send it. Dropping it
    at the boundary means it cannot be stored, rather than trusting the client.
    """
    event = StorefrontEventInput(
        **_event(path="/shop?utm_source=mail&email=someone@example.com")
    )

    assert event.path == "/shop"
    assert "email" not in event.path


def test_fragment_is_stripped_too():
    event = StorefrontEventInput(**_event(path="/shop/red-wine#reviews"))
    assert event.path == "/shop/red-wine"


def test_plain_path_is_untouched():
    event = StorefrontEventInput(**_event(path="/shop/red-wine"))
    assert event.path == "/shop/red-wine"


def test_path_is_length_bounded():
    event = StorefrontEventInput(**_event(path="/" + "x" * 500))
    assert len(event.path) <= 255


# ---------------------------------------------------------------------------
# The event vocabulary is closed
# ---------------------------------------------------------------------------


def test_unknown_event_types_are_rejected():
    """
    An open string would let any client write arbitrary values into a table an
    administrator later reads, and would let the funnel definition drift as the
    frontend changed.
    """
    with pytest.raises(PydanticValidationError):
        StorefrontEventInput(**_event(event_type="admin_password_grab"))


def test_every_declared_event_type_is_accepted():
    for event_type in StorefrontEventType:
        event = StorefrontEventInput(**_event(event_type=event_type.value))
        assert event.event_type is event_type


# ---------------------------------------------------------------------------
# Nothing unexpected gets through
# ---------------------------------------------------------------------------


def test_extra_fields_are_refused_rather_than_ignored():
    """
    Silently dropping an unknown field would let a client believe it is sending
    an email address that the API is quietly discarding. Refusing says so.
    """
    with pytest.raises(PydanticValidationError):
        StorefrontEventInput(**_event(email="someone@example.com"))

    with pytest.raises(PydanticValidationError):
        StorefrontEventInput(**_event(ip_address="203.0.113.4"))


def test_session_id_is_length_bounded_in_both_directions():
    with pytest.raises(PydanticValidationError):
        StorefrontEventInput(**_event(session_id="short"))

    with pytest.raises(PydanticValidationError):
        StorefrontEventInput(**_event(session_id="x" * 200))


# ---------------------------------------------------------------------------
# Batch limits
# ---------------------------------------------------------------------------


def test_batch_size_is_capped():
    """An open write endpoint must not accept an unbounded insert."""
    with pytest.raises(PydanticValidationError):
        StorefrontEventBatch(events=[_event() for _ in range(MAX_EVENTS_PER_BATCH + 1)])


def test_a_full_batch_is_accepted():
    batch = StorefrontEventBatch(events=[_event() for _ in range(MAX_EVENTS_PER_BATCH)])
    assert len(batch.events) == MAX_EVENTS_PER_BATCH


def test_empty_batch_is_rejected():
    with pytest.raises(PydanticValidationError):
        StorefrontEventBatch(events=[])
