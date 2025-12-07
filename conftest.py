"""
Pytest configuration for the fastapi_opentaberna project.

This file configures pytest to properly find and import modules.
"""

import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))
