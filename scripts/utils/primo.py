"""Primo discovery URL generation utility.

Extracted from ``app/api/metadata.py`` so that both the API layer and the
scholar pipeline executor can generate Primo links without circular imports.
"""

from __future__ import annotations

import os
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Default Primo configuration
# ---------------------------------------------------------------------------

_PRIMO_DEFAULT_BASE_URL = "https://tau.primo.exlibrisgroup.com/nde/search"
_PRIMO_VID = "972TAU_INST:NDE"
_PRIMO_TAB = "TAU"
_PRIMO_SEARCH_SCOPE = "TAU"


def generate_primo_url(mms_id: str, base_url: str | None = None) -> str:
    """Generate a Primo discovery URL for the given MMS ID.

    Uses the TAU Primo NDE search pattern:
    https://tau.primo.exlibrisgroup.com/nde/search?query=<mms_id>&tab=TAU&search_scope=TAU&vid=972TAU_INST:NDE

    Args:
        mms_id: The MMS ID (e.g. "990009748710204146").
        base_url: Optional override for the Primo base URL. Falls back to
                  the PRIMO_BASE_URL env var, then the built-in default.

    Returns:
        Full Primo URL to the record.
    """
    resolved_base = (
        base_url
        or os.environ.get("PRIMO_BASE_URL", "")
        or _PRIMO_DEFAULT_BASE_URL
    )

    params = {
        "query": mms_id,
        "tab": _PRIMO_TAB,
        "search_scope": _PRIMO_SEARCH_SCOPE,
        "vid": _PRIMO_VID,
    }

    query_parts = []
    for key, value in params.items():
        query_parts.append(f"{key}={quote(str(value), safe='')}")

    return f"{resolved_base}?{'&'.join(query_parts)}"
