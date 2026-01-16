"""Wikidata Client for entity enrichment via SPARQL.

This module provides enrichment data from Wikidata:
- Agent information (birth/death dates, nationality, occupations)
- Place information (coordinates, country, historical names)
- Entity relationships and external identifiers

Usage:
------
# Lookup by Wikidata ID (most accurate)
result = await enrich_agent_by_id("Q1234")

# Search by name (less accurate, may need disambiguation)
results = await search_agent_by_name("Aldus Manutius")

# Lookup place
result = await enrich_place_by_id("Q641")  # Venice
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from scripts.enrichment.models import (
    EnrichmentResult,
    EnrichmentSource,
    EntityType,
    ExternalIdentifier,
    PersonInfo,
    PlaceInfo,
)


# =============================================================================
# Constants
# =============================================================================

WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIDATA_API_ENDPOINT = "https://www.wikidata.org/w/api.php"

# User agent as required by Wikidata
USER_AGENT = "RareBooksBot/1.0 (https://github.com/rare-books-bot; educational research)"

# Rate limiting: Wikidata allows ~60 requests/minute for SPARQL
REQUEST_DELAY_SECONDS = 1.0


# =============================================================================
# SPARQL Queries
# =============================================================================

AGENT_SPARQL_BY_ID = """
SELECT ?item ?itemLabel ?itemDescription
       ?birthDate ?deathDate ?birthPlace ?birthPlaceLabel
       ?deathPlace ?deathPlaceLabel
       ?nationality ?nationalityLabel
       ?occupation ?occupationLabel
       ?viafId ?isniId ?locId ?image
WHERE {{
  BIND(wd:{qid} AS ?item)

  OPTIONAL {{ ?item wdt:P569 ?birthDate . }}
  OPTIONAL {{ ?item wdt:P570 ?deathDate . }}
  OPTIONAL {{ ?item wdt:P19 ?birthPlace . }}
  OPTIONAL {{ ?item wdt:P20 ?deathPlace . }}
  OPTIONAL {{ ?item wdt:P27 ?nationality . }}
  OPTIONAL {{ ?item wdt:P106 ?occupation . }}

  OPTIONAL {{ ?item wdt:P214 ?viafId . }}
  OPTIONAL {{ ?item wdt:P213 ?isniId . }}
  OPTIONAL {{ ?item wdt:P244 ?locId . }}
  OPTIONAL {{ ?item wdt:P18 ?image . }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,he". }}
}}
LIMIT 50
"""

AGENT_SEARCH_SPARQL = """
SELECT DISTINCT ?item ?itemLabel ?itemDescription
       ?birthDate ?deathDate
       ?occupation ?occupationLabel
WHERE {{
  ?item rdfs:label "{name}"@en .
  ?item wdt:P31 wd:Q5 .  # Instance of human

  OPTIONAL {{ ?item wdt:P569 ?birthDate . }}
  OPTIONAL {{ ?item wdt:P570 ?deathDate . }}
  OPTIONAL {{ ?item wdt:P106 ?occupation . }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,he". }}
}}
LIMIT 10
"""

PLACE_SPARQL_BY_ID = """
SELECT ?item ?itemLabel ?itemDescription
       ?country ?countryLabel
       ?coord
       ?population
       ?image
WHERE {{
  BIND(wd:{qid} AS ?item)

  OPTIONAL {{ ?item wdt:P17 ?country . }}
  OPTIONAL {{ ?item wdt:P625 ?coord . }}
  OPTIONAL {{ ?item wdt:P1082 ?population . }}
  OPTIONAL {{ ?item wdt:P18 ?image . }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,he". }}
}}
LIMIT 1
"""

PLACE_SEARCH_SPARQL = """
SELECT DISTINCT ?item ?itemLabel ?itemDescription
       ?country ?countryLabel
       ?coord
WHERE {{
  ?item rdfs:label "{name}"@en .
  {{ ?item wdt:P31/wdt:P279* wd:Q515 . }}  # City or subclass
  UNION
  {{ ?item wdt:P31/wdt:P279* wd:Q56061 . }}  # Administrative entity

  OPTIONAL {{ ?item wdt:P17 ?country . }}
  OPTIONAL {{ ?item wdt:P625 ?coord . }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,he". }}
}}
LIMIT 10
"""


# =============================================================================
# HTTP Client
# =============================================================================


async def execute_sparql(
    query: str,
    timeout: float = 30.0,
) -> Optional[Dict[str, Any]]:
    """Execute a SPARQL query against Wikidata.

    Args:
        query: SPARQL query string
        timeout: Request timeout in seconds

    Returns:
        Query results as dict or None if failed
    """
    headers = {
        "User-Agent": USER_AGENT,
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
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as e:
            print(f"SPARQL query failed: {e}")
            return None


async def search_wikidata_api(
    search_term: str,
    entity_type: str = "item",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Search Wikidata using the API (faster for simple searches).

    Args:
        search_term: Text to search for
        entity_type: "item" or "property"
        limit: Max results to return

    Returns:
        List of search results
    """
    headers = {
        "User-Agent": USER_AGENT,
    }

    params = {
        "action": "wbsearchentities",
        "search": search_term,
        "type": entity_type,
        "language": "en",
        "limit": limit,
        "format": "json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                WIKIDATA_API_ENDPOINT,
                params=params,
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("search", [])
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError):
            return []


# =============================================================================
# Result Parsing
# =============================================================================


def parse_wikidata_date(date_str: Optional[str]) -> Optional[int]:
    """Parse Wikidata date to year.

    Args:
        date_str: Date string in ISO format or Wikidata format

    Returns:
        Year as integer or None
    """
    if not date_str:
        return None

    # Handle various date formats
    patterns = [
        r"^(\d{4})-\d{2}-\d{2}",  # 1459-01-15
        r"^(\d{4})",  # Just year
        r"^-?(\d+)",  # Negative years (BCE)
    ]

    for pattern in patterns:
        match = re.match(pattern, str(date_str))
        if match:
            try:
                year = int(match.group(1))
                # Handle BCE dates
                if date_str.startswith("-"):
                    year = -year
                return year
            except ValueError:
                continue

    return None


def parse_coordinates(coord_str: Optional[str]) -> Optional[Dict[str, float]]:
    """Parse Wikidata coordinate point.

    Args:
        coord_str: Coordinate string like "Point(12.4924 41.8902)"

    Returns:
        Dict with lat/lon or None
    """
    if not coord_str:
        return None

    match = re.search(r"Point\(([+-]?\d+\.?\d*)\s+([+-]?\d+\.?\d*)\)", str(coord_str))
    if match:
        try:
            lon = float(match.group(1))
            lat = float(match.group(2))
            return {"lat": lat, "lon": lon}
        except ValueError:
            pass

    return None


def extract_qid(uri: str) -> Optional[str]:
    """Extract Wikidata QID from URI.

    Args:
        uri: Wikidata entity URI

    Returns:
        QID string (e.g., "Q1234") or None
    """
    if not uri:
        return None

    match = re.search(r"(Q\d+)$", str(uri))
    return match.group(1) if match else None


# =============================================================================
# Agent Enrichment
# =============================================================================


async def enrich_agent_by_id(
    wikidata_id: str,
    normalize_key: Optional[str] = None,
) -> Optional[EnrichmentResult]:
    """Enrich an agent by Wikidata ID.

    Args:
        wikidata_id: Wikidata QID (e.g., "Q1234")
        normalize_key: Normalized lookup key for caching

    Returns:
        EnrichmentResult or None if not found
    """
    # Ensure QID format
    qid = wikidata_id.upper()
    if not qid.startswith("Q"):
        qid = f"Q{qid}"

    query = AGENT_SPARQL_BY_ID.format(qid=qid)
    results = await execute_sparql(query)

    if not results or not results.get("results", {}).get("bindings"):
        return None

    bindings = results["results"]["bindings"]
    first = bindings[0]

    # Extract person info
    birth_year = parse_wikidata_date(first.get("birthDate", {}).get("value"))
    death_year = parse_wikidata_date(first.get("deathDate", {}).get("value"))

    # Collect occupations (may have multiple results)
    occupations = list(set(
        b.get("occupationLabel", {}).get("value")
        for b in bindings
        if b.get("occupationLabel", {}).get("value")
    ))

    # Collect nationalities
    nationalities = list(set(
        b.get("nationalityLabel", {}).get("value")
        for b in bindings
        if b.get("nationalityLabel", {}).get("value")
    ))

    person_info = PersonInfo(
        birth_year=birth_year,
        death_year=death_year,
        birth_place=first.get("birthPlaceLabel", {}).get("value"),
        death_place=first.get("deathPlaceLabel", {}).get("value"),
        nationality=nationalities[0] if nationalities else None,
        occupations=occupations[:5],  # Limit to 5
        description=first.get("itemDescription", {}).get("value"),
    )

    # External identifiers
    external_ids = []
    if first.get("viafId", {}).get("value"):
        external_ids.append(ExternalIdentifier(
            source=EnrichmentSource.VIAF,
            identifier=first["viafId"]["value"],
            url=f"https://viaf.org/viaf/{first['viafId']['value']}"
        ))
    if first.get("isniId", {}).get("value"):
        external_ids.append(ExternalIdentifier(
            source=EnrichmentSource.ISNI,
            identifier=first["isniId"]["value"],
        ))
    if first.get("locId", {}).get("value"):
        external_ids.append(ExternalIdentifier(
            source=EnrichmentSource.LOC,
            identifier=first["locId"]["value"],
            url=f"https://id.loc.gov/authorities/names/{first['locId']['value']}"
        ))

    # Build result
    return EnrichmentResult(
        entity_type=EntityType.AGENT,
        entity_value=first.get("itemLabel", {}).get("value", "Unknown"),
        normalized_key=normalize_key or qid.lower(),
        wikidata_id=qid,
        viaf_id=first.get("viafId", {}).get("value"),
        isni_id=first.get("isniId", {}).get("value"),
        loc_id=first.get("locId", {}).get("value"),
        external_ids=external_ids,
        person_info=person_info,
        label=first.get("itemLabel", {}).get("value"),
        description=first.get("itemDescription", {}).get("value"),
        image_url=first.get("image", {}).get("value"),
        wikipedia_url=f"https://en.wikipedia.org/wiki/Special:GoToLinkedPage/enwiki/{qid}",
        sources_used=[EnrichmentSource.WIKIDATA],
        confidence=0.95,
        fetched_at=datetime.now(timezone.utc),
        raw_data={"sparql_results": bindings[:5]},  # Keep first 5 for debugging
    )


async def search_agent_by_name(
    name: str,
    limit: int = 5,
) -> List[EnrichmentResult]:
    """Search for agents by name.

    Note: This is less accurate than lookup by ID. Multiple results
    may be returned for disambiguation.

    Args:
        name: Agent name to search
        limit: Maximum results to return

    Returns:
        List of EnrichmentResult (may be empty)
    """
    # First try API search (faster)
    api_results = await search_wikidata_api(name, limit=limit)

    results = []
    for item in api_results[:limit]:
        qid = item.get("id")
        if not qid:
            continue

        # Get full details via SPARQL
        full_result = await enrich_agent_by_id(qid, normalize_key=name.lower())
        if full_result:
            # Reduce confidence for search results
            full_result.confidence = 0.7
            results.append(full_result)

        # Rate limiting
        await asyncio.sleep(REQUEST_DELAY_SECONDS)

    return results


# =============================================================================
# Place Enrichment
# =============================================================================


async def enrich_place_by_id(
    wikidata_id: str,
    normalize_key: Optional[str] = None,
) -> Optional[EnrichmentResult]:
    """Enrich a place by Wikidata ID.

    Args:
        wikidata_id: Wikidata QID (e.g., "Q641" for Venice)
        normalize_key: Normalized lookup key for caching

    Returns:
        EnrichmentResult or None if not found
    """
    qid = wikidata_id.upper()
    if not qid.startswith("Q"):
        qid = f"Q{qid}"

    query = PLACE_SPARQL_BY_ID.format(qid=qid)
    results = await execute_sparql(query)

    if not results or not results.get("results", {}).get("bindings"):
        return None

    first = results["results"]["bindings"][0]

    # Extract place info
    coordinates = parse_coordinates(first.get("coord", {}).get("value"))

    place_info = PlaceInfo(
        country=first.get("countryLabel", {}).get("value"),
        coordinates=coordinates,
        modern_name=first.get("itemLabel", {}).get("value"),
        description=first.get("itemDescription", {}).get("value"),
    )

    return EnrichmentResult(
        entity_type=EntityType.PLACE,
        entity_value=first.get("itemLabel", {}).get("value", "Unknown"),
        normalized_key=normalize_key or qid.lower(),
        wikidata_id=qid,
        place_info=place_info,
        label=first.get("itemLabel", {}).get("value"),
        description=first.get("itemDescription", {}).get("value"),
        image_url=first.get("image", {}).get("value"),
        wikipedia_url=f"https://en.wikipedia.org/wiki/Special:GoToLinkedPage/enwiki/{qid}",
        sources_used=[EnrichmentSource.WIKIDATA],
        confidence=0.95,
        fetched_at=datetime.now(timezone.utc),
        raw_data={"sparql_results": [first]},
    )


async def search_place_by_name(
    name: str,
    limit: int = 5,
) -> List[EnrichmentResult]:
    """Search for places by name.

    Args:
        name: Place name to search
        limit: Maximum results to return

    Returns:
        List of EnrichmentResult (may be empty)
    """
    # Escape name for SPARQL
    escaped_name = name.replace('"', '\\"')
    query = PLACE_SEARCH_SPARQL.format(name=escaped_name)
    results = await execute_sparql(query)

    if not results or not results.get("results", {}).get("bindings"):
        # Fall back to API search
        api_results = await search_wikidata_api(name, limit=limit)
        enriched = []
        for item in api_results[:limit]:
            qid = item.get("id")
            if qid:
                result = await enrich_place_by_id(qid, normalize_key=name.lower())
                if result:
                    result.confidence = 0.7
                    enriched.append(result)
                await asyncio.sleep(REQUEST_DELAY_SECONDS)
        return enriched

    enriched = []
    for binding in results["results"]["bindings"][:limit]:
        qid = extract_qid(binding.get("item", {}).get("value"))
        if qid:
            result = await enrich_place_by_id(qid, normalize_key=name.lower())
            if result:
                result.confidence = 0.8  # Higher than API search
                enriched.append(result)
            await asyncio.sleep(REQUEST_DELAY_SECONDS)

    return enriched


# =============================================================================
# Convenience Functions
# =============================================================================


async def get_wikidata_id_for_viaf(viaf_id: str) -> Optional[str]:
    """Look up Wikidata ID from VIAF ID.

    Args:
        viaf_id: VIAF identifier

    Returns:
        Wikidata QID or None
    """
    query = f"""
    SELECT ?item WHERE {{
      ?item wdt:P214 "{viaf_id}" .
    }}
    LIMIT 1
    """

    results = await execute_sparql(query)
    if results and results.get("results", {}).get("bindings"):
        uri = results["results"]["bindings"][0].get("item", {}).get("value")
        return extract_qid(uri)

    return None


async def get_wikidata_id_for_isni(isni_id: str) -> Optional[str]:
    """Look up Wikidata ID from ISNI.

    Args:
        isni_id: ISNI identifier

    Returns:
        Wikidata QID or None
    """
    # Normalize ISNI (remove spaces/dashes)
    normalized = re.sub(r"[\s-]", "", isni_id)

    query = f"""
    SELECT ?item WHERE {{
      ?item wdt:P213 "{normalized}" .
    }}
    LIMIT 1
    """

    results = await execute_sparql(query)
    if results and results.get("results", {}).get("bindings"):
        uri = results["results"]["bindings"][0].get("item", {}).get("value")
        return extract_qid(uri)

    return None
