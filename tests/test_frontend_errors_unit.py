"""
Unit tests for frontend error reporting — schema and user-agent reduction.

The report endpoint is public, so its schema is a boundary. And the whole point
of reducing the user agent is that a fingerprint never reaches storage, which is
a property worth pinning rather than trusting.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.services.frontend_errors.functions import coarse_browser
from app.services.frontend_errors.models import (
    MAX_ERRORS_PER_BATCH,
    MAX_STACK_CHARS,
    FrontendErrorBatch,
    FrontendErrorInput,
)


def _error(**overrides) -> dict:
    base = {
        "app": "storefront",
        "name": "TypeError",
        "message": "undefined is not a function",
        "occurred_at": datetime.now(UTC),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# The user agent is reduced, never stored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_agent,expected",
    [
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/18.3 Safari/605.1.15",
            "Safari 18",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "Chrome 140",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/133.0",
            "Firefox 133",
        ),
    ],
)
def test_common_browsers_are_reduced_to_family_and_major(user_agent, expected):
    assert coarse_browser(user_agent) == expected


def test_edge_is_not_reported_as_chrome():
    """
    Edge, Opera and Chrome all claim to be one another. The most specific
    pattern has to win, or every error looks like it came from Chrome.
    """
    edge = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"
    )
    assert coarse_browser(edge) == "Edge 140"


def test_nothing_from_the_original_string_survives():
    """
    The reduction is the privacy guarantee. Whatever a client sends, the result
    is a known family name and an integer — never a fragment of the input.
    """
    hostile = "Mozilla/5.0 Chrome/140 user=alice@example.com token=abc123"
    result = coarse_browser(hostile)

    assert result == "Chrome 140"
    assert "alice@example.com" not in result
    assert "abc123" not in result


def test_an_unrecognised_agent_is_unknown_not_stored_verbatim():
    assert coarse_browser("something entirely made up") == "unknown"
    assert coarse_browser(None) == "unknown"
    assert coarse_browser("") == "unknown"


# ---------------------------------------------------------------------------
# The schema as a boundary
# ---------------------------------------------------------------------------


def test_query_strings_are_stripped_from_the_path():
    error = FrontendErrorInput(**_error(path="/checkout?token=secret&email=a@b.c"))
    assert error.path == "/checkout"


def test_a_huge_stack_is_truncated_rather_than_rejected():
    """
    A stack trace is unbounded input from a public endpoint, and also the most
    useful field here. Cutting it keeps the top frames, where the fault is.
    """
    error = FrontendErrorInput(**_error(stack="x" * (MAX_STACK_CHARS * 3)))

    assert len(error.stack) < MAX_STACK_CHARS + 100
    assert error.stack.endswith("truncated")


def test_unknown_apps_are_refused():
    """A closed set, so the field cannot become free text from a public endpoint."""
    with pytest.raises(PydanticValidationError):
        FrontendErrorInput(**_error(app="not-an-app"))


def test_extra_fields_are_refused():
    with pytest.raises(PydanticValidationError):
        FrontendErrorInput(**_error(user_agent="Mozilla/5.0"))

    with pytest.raises(PydanticValidationError):
        FrontendErrorInput(**_error(customer_id="123"))


def test_batch_size_is_capped():
    """
    A component throwing inside a render loop is the normal failure mode, and
    it will report as fast as the browser can loop.
    """
    with pytest.raises(PydanticValidationError):
        FrontendErrorBatch(errors=[_error() for _ in range(MAX_ERRORS_PER_BATCH + 1)])


def test_message_length_is_bounded():
    with pytest.raises(PydanticValidationError):
        FrontendErrorInput(**_error(message="x" * 5000))
