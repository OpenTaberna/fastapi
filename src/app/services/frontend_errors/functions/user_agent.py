"""
Coarse browser identification.

A raw user-agent string is a fingerprint: combined with a handful of other
signals it identifies a device, which is exactly what the rest of this system
refuses to collect. But "which browser?" is genuinely diagnostic — half of all
frontend bugs are one engine behaving differently — so throwing it away entirely
makes the error reports much less useful.

The compromise is to reduce the string to a family and a major version at the
boundary and store only that. "Safari 18" is enough to reproduce a bug and not
enough to recognise anyone.
"""

from __future__ import annotations

import re

_UNKNOWN = "unknown"

# Order matters. Edge and Opera both claim to be Chrome, and Chrome claims to be
# Safari, so the most specific pattern has to win.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Edge", re.compile(r"Edg(?:e|A|iOS)?/(\d+)")),
    ("Opera", re.compile(r"OPR/(\d+)")),
    ("Samsung Internet", re.compile(r"SamsungBrowser/(\d+)")),
    ("Firefox", re.compile(r"Firefox/(\d+)")),
    ("Chrome", re.compile(r"Chrome/(\d+)")),
    ("Safari", re.compile(r"Version/(\d+).*Safari")),
)


def coarse_browser(user_agent: str | None) -> str:
    """
    Reduce a user-agent string to "Family Major", or "unknown".

    Never returns anything derived from the original string beyond the family
    name and an integer, so no amount of unusual input can smuggle a fingerprint
    through.
    """
    if not user_agent:
        return _UNKNOWN

    for family, pattern in _PATTERNS:
        match = pattern.search(user_agent)
        if match:
            return f"{family} {match.group(1)}"

    return _UNKNOWN
