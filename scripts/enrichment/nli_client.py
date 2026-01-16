"""NLI Authority Client for extracting external identifiers.

This module handles fetching external identifiers (Wikidata, VIAF, etc.)
from NLI authority records.

Architecture:
-----------
1. Authority URI in MARC $0 subfield contains NLI ID:
   https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities/{NLI_ID}.jsonld

2. **Primary Method**: Query Wikidata using NLI ID (P8189 - J9U ID property)
   - Wikidata stores NLI authority IDs for many entities
   - This gives us the Wikidata QID, from which we can get all other IDs
   - Example: NLI 987007261327805171 → Wikidata Q705482 (David Frischmann)

3. NLI Authority HTML page (blocked by Cloudflare):
   https://www.nli.org.il/en/authorities/{NLI_ID}
   Contains external IDs but requires manual access

4. JSONLD endpoint (works but lacks external IDs):
   Returns name/label data only

External identifiers available via Wikidata:
   - Wikidata (Q123456)
   - VIAF (12345678)
   - ISNI (0000 0001 2345 6789)
   - LOC/NAF (n12345678)

Note on Cloudflare:
------------------
NLI web pages use Cloudflare Turnstile protection.
The NLI search API also requires Cloudflare clearance.
However, we can bypass this entirely by querying Wikidata!
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from scripts.enrichment.models import (
    NLIAuthorityIdentifiers,
    EnrichmentSource,
)


# =============================================================================
# Constants
# =============================================================================

# NLI endpoints
NLI_JSONLD_BASE = "https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities"
NLI_HTML_BASE = "https://www.nli.org.il/en/authorities"

# Manual mapping file path
MANUAL_MAPPING_PATH = Path("data/enrichment/nli_manual_mapping.json")


# =============================================================================
# URI Parsing
# =============================================================================


def extract_nli_id_from_uri(uri: str) -> Optional[str]:
    """Extract NLI authority ID from MARC $0 URI.

    Args:
        uri: Full authority URI from MARC $0 subfield

    Returns:
        NLI ID string or None if not parseable

    Examples:
        >>> extract_nli_id_from_uri(
        ...     "https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities/987007261327805171.jsonld"
        ... )
        '987007261327805171'
        >>> extract_nli_id_from_uri("https://example.com/other")
        None
    """
    if not uri:
        return None

    # Pattern: /authorities/{id}.jsonld or /authorities/{id}
    patterns = [
        r"/authorities/(\d+)\.jsonld",
        r"/authorities/(\d+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, uri)
        if match:
            return match.group(1)

    return None


def build_nli_urls(nli_id: str) -> dict:
    """Build NLI URLs for an authority ID.

    Args:
        nli_id: NLI authority identifier

    Returns:
        Dict with 'jsonld' and 'html' URLs
    """
    return {
        "jsonld": f"{NLI_JSONLD_BASE}/{nli_id}.jsonld",
        "html": f"{NLI_HTML_BASE}/{nli_id}",
    }


# =============================================================================
# JSONLD Endpoint (Works, but lacks external IDs)
# =============================================================================


async def fetch_nli_jsonld(nli_id: str, timeout: float = 10.0) -> Optional[dict]:
    """Fetch NLI authority data from JSONLD endpoint.

    Note: This endpoint works without Cloudflare issues but does NOT
    contain external identifiers (Wikidata, VIAF, etc.). Use for:
    - Preferred label/name
    - Alternative name forms
    - Basic authority metadata

    Args:
        nli_id: NLI authority identifier
        timeout: Request timeout in seconds

    Returns:
        JSONLD data dict or None if fetch failed
    """
    url = f"{NLI_JSONLD_BASE}/{nli_id}.jsonld"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=timeout)
            if response.status_code == 200:
                return response.json()
        except (httpx.TimeoutException, httpx.RequestError, json.JSONDecodeError):
            pass

    return None


def parse_jsonld_label(jsonld_data: dict) -> Optional[str]:
    """Extract preferred label from JSONLD response.

    Args:
        jsonld_data: JSONLD response from NLI

    Returns:
        Preferred label string or None
    """
    if not jsonld_data:
        return None

    # Try different label fields
    for field in ["prefLabel", "http://www.w3.org/2004/02/skos/core#prefLabel"]:
        if field in jsonld_data:
            label = jsonld_data[field]
            if isinstance(label, list) and label:
                return str(label[0].get("@value", label[0]))
            elif isinstance(label, dict):
                return str(label.get("@value", label))
            elif isinstance(label, str):
                return label

    return None


# =============================================================================
# Wikidata NLI ID Lookup (Primary Method)
# =============================================================================

# Wikidata SPARQL endpoint
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIDATA_USER_AGENT = "RareBooksBot/1.0 (https://github.com/rare-books-bot; educational research)"


async def get_wikidata_id_from_nli(nli_id: str) -> Optional[str]:
    """Look up Wikidata ID from NLI authority ID via SPARQL.

    This is the primary method for resolving NLI IDs to external identifiers.
    Wikidata stores NLI J9U IDs as property P8189.

    Args:
        nli_id: NLI authority ID (e.g., "987007261327805171")

    Returns:
        Wikidata QID (e.g., "Q705482") or None if not found

    Example:
        >>> await get_wikidata_id_from_nli("987007261327805171")
        'Q705482'  # David Frischmann
    """
    query = f'''
    SELECT ?item WHERE {{
      ?item wdt:P8189 "{nli_id}" .
    }}
    LIMIT 1
    '''

    headers = {
        "User-Agent": WIKIDATA_USER_AGENT,
        "Accept": "application/sparql-results+json",
    }

    params = {
        "query": query,
        "format": "json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                WIKIDATA_SPARQL_ENDPOINT,
                params=params,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            bindings = data.get("results", {}).get("bindings", [])
            if bindings:
                uri = bindings[0].get("item", {}).get("value", "")
                # Extract QID from URI
                match = re.search(r"(Q\d+)$", uri)
                if match:
                    return match.group(1)
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError):
            pass

    return None


async def lookup_nli_via_wikidata(nli_id: str) -> Optional[NLIAuthorityIdentifiers]:
    """Look up NLI authority identifiers via Wikidata.

    This queries Wikidata using the NLI ID (P8189) to find the entity,
    then extracts all available external identifiers.

    Args:
        nli_id: NLI authority ID

    Returns:
        NLIAuthorityIdentifiers with Wikidata ID and other IDs, or None
    """
    wikidata_id = await get_wikidata_id_from_nli(nli_id)

    if not wikidata_id:
        return None

    # Query Wikidata for all identifiers
    query = f'''
    SELECT ?viafId ?isniId ?locId WHERE {{
      BIND(wd:{wikidata_id} AS ?item)
      OPTIONAL {{ ?item wdt:P214 ?viafId . }}
      OPTIONAL {{ ?item wdt:P213 ?isniId . }}
      OPTIONAL {{ ?item wdt:P244 ?locId . }}
    }}
    LIMIT 1
    '''

    headers = {
        "User-Agent": WIKIDATA_USER_AGENT,
        "Accept": "application/sparql-results+json",
    }

    params = {
        "query": query,
        "format": "json",
    }

    viaf_id = None
    isni_id = None
    loc_id = None

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                WIKIDATA_SPARQL_ENDPOINT,
                params=params,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            bindings = data.get("results", {}).get("bindings", [])
            if bindings:
                b = bindings[0]
                viaf_id = b.get("viafId", {}).get("value")
                isni_id = b.get("isniId", {}).get("value")
                loc_id = b.get("locId", {}).get("value")
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError):
            pass

    return NLIAuthorityIdentifiers(
        nli_id=nli_id,
        wikidata_id=wikidata_id,
        viaf_id=viaf_id,
        isni_id=isni_id,
        loc_id=loc_id,
        fetched_at=datetime.now(timezone.utc),
        fetch_method="wikidata_sparql",
    )


# =============================================================================
# Manual Mapping File
# =============================================================================


def load_manual_mapping() -> dict:
    """Load manual NLI ID to external ID mapping.

    The mapping file should be JSON with structure:
    {
        "987007261327805171": {
            "wikidata_id": "Q1234",
            "viaf_id": "12345678",
            "isni_id": "0000 0001 2345 6789",
            "loc_id": "n12345678",
            "label": "David Frishman",
            "updated_at": "2026-01-16T12:00:00Z"
        },
        ...
    }

    Returns:
        Dict mapping NLI IDs to identifier dicts
    """
    if not MANUAL_MAPPING_PATH.exists():
        return {}

    try:
        with open(MANUAL_MAPPING_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_manual_mapping(mapping: dict) -> None:
    """Save manual mapping to file.

    Args:
        mapping: Dict mapping NLI IDs to identifier dicts
    """
    MANUAL_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANUAL_MAPPING_PATH, "w") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)


def add_manual_mapping(
    nli_id: str,
    wikidata_id: Optional[str] = None,
    viaf_id: Optional[str] = None,
    isni_id: Optional[str] = None,
    loc_id: Optional[str] = None,
    label: Optional[str] = None,
) -> None:
    """Add or update a manual mapping entry.

    Args:
        nli_id: NLI authority identifier
        wikidata_id: Wikidata Q-number (e.g., "Q1234")
        viaf_id: VIAF number (e.g., "12345678")
        isni_id: ISNI number (e.g., "0000 0001 2345 6789")
        loc_id: Library of Congress ID (e.g., "n12345678")
        label: Human-readable label
    """
    mapping = load_manual_mapping()

    entry = mapping.get(nli_id, {})
    if wikidata_id:
        entry["wikidata_id"] = wikidata_id
    if viaf_id:
        entry["viaf_id"] = viaf_id
    if isni_id:
        entry["isni_id"] = isni_id
    if loc_id:
        entry["loc_id"] = loc_id
    if label:
        entry["label"] = label
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()

    mapping[nli_id] = entry
    save_manual_mapping(mapping)


# =============================================================================
# Main Lookup Function
# =============================================================================


async def lookup_nli_identifiers(
    nli_id: str,
    use_wikidata: bool = True,
    use_manual_mapping: bool = True,
    use_jsonld: bool = True,
) -> Optional[NLIAuthorityIdentifiers]:
    """Look up external identifiers for an NLI authority ID.

    This function tries multiple sources in order:
    1. Wikidata SPARQL (primary - queries P8189 NLI J9U ID property)
    2. Manual mapping file (fallback for entities not in Wikidata)
    3. JSONLD endpoint (for label only, doesn't have external IDs)

    The Wikidata method is now the primary approach because:
    - Wikidata stores NLI IDs for ~820,000+ entities
    - No Cloudflare blocking
    - Gives us Wikidata QID which unlocks all other identifiers

    Args:
        nli_id: NLI authority identifier
        use_wikidata: Whether to query Wikidata (recommended)
        use_manual_mapping: Whether to check manual mapping file
        use_jsonld: Whether to fetch from JSONLD endpoint

    Returns:
        NLIAuthorityIdentifiers or None if not found
    """
    # 1. Try Wikidata first (primary method)
    if use_wikidata:
        wikidata_result = await lookup_nli_via_wikidata(nli_id)
        if wikidata_result and wikidata_result.wikidata_id:
            return wikidata_result

    # 2. Check manual mapping as fallback
    if use_manual_mapping:
        mapping = load_manual_mapping()
        if nli_id in mapping:
            entry = mapping[nli_id]
            result = NLIAuthorityIdentifiers(
                nli_id=nli_id,
                wikidata_id=entry.get("wikidata_id"),
                viaf_id=entry.get("viaf_id"),
                isni_id=entry.get("isni_id"),
                loc_id=entry.get("loc_id"),
                fetched_at=datetime.now(timezone.utc),
                fetch_method="manual_mapping",
            )
            # If we have any external ID, return
            if any([result.wikidata_id, result.viaf_id, result.isni_id, result.loc_id]):
                return result

    # 3. Try JSONLD for label (no external IDs available there)
    if use_jsonld:
        jsonld_data = await fetch_nli_jsonld(nli_id)
        if jsonld_data:
            return NLIAuthorityIdentifiers(
                nli_id=nli_id,
                nli_uri=f"{NLI_JSONLD_BASE}/{nli_id}.jsonld",
                fetched_at=datetime.now(timezone.utc),
                fetch_method="jsonld",
            )

    return None


# =============================================================================
# HTML Parsing (For Manual/Assisted Extraction)
# =============================================================================


def parse_nli_html_for_identifiers(html_content: str) -> dict:
    """Parse NLI authority HTML page for external identifiers.

    This function extracts identifiers from the
    <div class="additional-identity-container"> element.

    Note: Due to Cloudflare, this HTML must be obtained manually
    (e.g., saved from browser, or via assisted Playwright session).

    Args:
        html_content: Full HTML content of NLI authority page

    Returns:
        Dict with extracted identifiers:
        {
            "wikidata_id": "Q1234" or None,
            "viaf_id": "12345678" or None,
            "isni_id": "0000 0001 2345 6789" or None,
            "loc_id": "n12345678" or None,
            "other_ids": {"gnd": "123", ...}
        }
    """
    identifiers = {
        "wikidata_id": None,
        "viaf_id": None,
        "isni_id": None,
        "loc_id": None,
        "other_ids": {},
    }

    # Pattern for the additional-identity-container section
    container_match = re.search(
        r'<div[^>]*class="[^"]*additional-identity-container[^"]*"[^>]*>(.*?)</div>',
        html_content,
        re.DOTALL | re.IGNORECASE
    )

    if not container_match:
        return identifiers

    container_html = container_match.group(1)

    # Extract Wikidata ID (Q followed by numbers)
    wikidata_match = re.search(r'wikidata[^>]*>.*?(Q\d+)', container_html, re.IGNORECASE | re.DOTALL)
    if wikidata_match:
        identifiers["wikidata_id"] = wikidata_match.group(1)

    # Extract VIAF ID (numeric)
    viaf_match = re.search(r'viaf[^>]*>.*?(\d{5,})', container_html, re.IGNORECASE | re.DOTALL)
    if viaf_match:
        identifiers["viaf_id"] = viaf_match.group(1)

    # Extract ISNI (pattern: 0000 0000 0000 0000 or similar)
    isni_match = re.search(r'isni[^>]*>.*?(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})', container_html, re.IGNORECASE | re.DOTALL)
    if isni_match:
        identifiers["isni_id"] = isni_match.group(1)

    # Extract LOC ID (pattern: n or no followed by numbers)
    loc_match = re.search(r'(?:loc|library of congress)[^>]*>.*?(n[or]?\d+)', container_html, re.IGNORECASE | re.DOTALL)
    if loc_match:
        identifiers["loc_id"] = loc_match.group(1)

    return identifiers


def batch_extract_from_saved_html(html_dir: Path) -> dict:
    """Extract identifiers from a directory of saved HTML files.

    For manual bulk extraction:
    1. Manually save NLI authority pages to a directory
    2. Name files as {nli_id}.html
    3. Run this function to extract all identifiers
    4. Results saved to manual mapping file

    Args:
        html_dir: Directory containing saved HTML files

    Returns:
        Dict mapping NLI IDs to extracted identifiers
    """
    results = {}

    for html_file in html_dir.glob("*.html"):
        nli_id = html_file.stem
        try:
            html_content = html_file.read_text(encoding="utf-8")
            identifiers = parse_nli_html_for_identifiers(html_content)
            if any(v for k, v in identifiers.items() if k != "other_ids"):
                results[nli_id] = identifiers
                # Also update manual mapping
                add_manual_mapping(
                    nli_id=nli_id,
                    wikidata_id=identifiers.get("wikidata_id"),
                    viaf_id=identifiers.get("viaf_id"),
                    isni_id=identifiers.get("isni_id"),
                    loc_id=identifiers.get("loc_id"),
                )
        except Exception:
            continue

    return results
