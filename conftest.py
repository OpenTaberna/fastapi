"""
Pytest configuration for the fastapi_opentaberna project.

This file configures pytest to properly find and import modules.
"""

import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))


import pytest

from app.shared.config.factory import clear_settings_cache


@pytest.fixture(autouse=True)
def _isolate_settings_cache():
    """
    Stop one test's Settings from leaking into the next.

    get_settings() is an lru_cache singleton. Tests in test_config.py clear it
    while environment variables are monkeypatched, so the instance left in the
    cache afterwards was built under that temporary environment - production,
    in some cases. monkeypatch restores the variables but cannot restore the
    cache, so unrelated tests later read a stale configuration.

    Clearing on the way out keeps each test honest and makes ordering
    irrelevant.
    """
    yield
    clear_settings_cache()
