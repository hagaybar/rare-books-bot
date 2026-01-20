"""Configuration for the Chat UI.

Contains Primo URL configuration and other UI settings.
"""

from urllib.parse import quote

# Primo base URL configuration for Tel Aviv University
PRIMO_BASE_URL = "https://tau.primo.exlibrisgroup.com/nde/fulldisplay"
PRIMO_VID = "972TAU_INST:NDE"
PRIMO_TAB = "TAU"
PRIMO_SEARCH_SCOPE = "TAU"


def generate_primo_url(mms_id: str) -> str:
    """Generate a Primo URL for a given MMS ID.

    Args:
        mms_id: The MMS ID (e.g., "990009748710204146")

    Returns:
        Full Primo URL to the record
    """
    params = {
        "query": f"{mms_id} ",  # Note: trailing space is intentional
        "tab": PRIMO_TAB,
        "search_scope": PRIMO_SEARCH_SCOPE,
        "searchInFulltext": "true",
        "vid": PRIMO_VID,
        "docid": f"alma{mms_id}",
        "adaptor": "Local Search Engine",
        "context": "L",
        "isFrbr": "false",
        "isHighlightedRecord": "false",
        "state": "",
    }

    # Build query string manually to preserve order and encoding
    query_parts = []
    for key, value in params.items():
        query_parts.append(f"{key}={quote(str(value), safe='')}")

    return f"{PRIMO_BASE_URL}?{'&'.join(query_parts)}"
