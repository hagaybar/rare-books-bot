"""Shared utilities for metadata API routers.

Contains common helper functions used across metadata_*.py modules.
"""

import os
from pathlib import Path


def _get_db_path() -> Path:
    """Resolve the bibliographic database path from environment."""
    return Path(
        os.environ.get("BIBLIOGRAPHIC_DB_PATH", "data/index/bibliographic.db").strip()
    )
