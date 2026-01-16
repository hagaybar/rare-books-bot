"""Enrichment Service - Main interface for entity enrichment.

This module provides the primary interface for enriching entities with
external data from Wikidata, VIAF, and other sources.

Features:
- Cache-first lookups (SQLite cache with TTL)
- Multi-source fallback (NLI → Wikidata → VIAF)
- Batch enrichment with rate limiting
- Background queue processing

Usage:
------
from scripts.enrichment.enrichment_service import EnrichmentService

service = EnrichmentService(cache_db_path=Path("data/enrichment/cache.db"))

# Single entity enrichment
result = await service.enrich_entity(
    entity_type=EntityType.AGENT,
    entity_value="Aldus Manutius",
    nli_authority_uri="https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities/987007261327805171.jsonld"
)

# Batch enrichment
results = await service.enrich_batch([
    EnrichmentRequest(entity_type=EntityType.AGENT, entity_value="Aldus Manutius"),
    EnrichmentRequest(entity_type=EntityType.PLACE, entity_value="Venice"),
])
"""

import asyncio
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.enrichment.models import (
    EnrichmentRequest,
    EnrichmentResult,
    EnrichmentSource,
    EntityType,
    NLIAuthorityIdentifiers,
    CacheEntry,
)
from scripts.enrichment.nli_client import (
    extract_nli_id_from_uri,
    lookup_nli_identifiers,
)
from scripts.enrichment.wikidata_client import (
    enrich_agent_by_id,
    enrich_place_by_id,
    search_agent_by_name,
    search_place_by_name,
    get_wikidata_id_for_viaf,
)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_TTL_DAYS = 30  # Cache entries valid for 30 days
RATE_LIMIT_DELAY = 1.0  # Seconds between requests


# =============================================================================
# Cache Database Operations
# =============================================================================


def init_cache_db(db_path: Path) -> sqlite3.Connection:
    """Initialize the enrichment cache database.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Database connection
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Read and execute schema
    schema_path = Path(__file__).parent / "schema.sql"
    if schema_path.exists():
        with open(schema_path) as f:
            conn.executescript(f.read())

    return conn


def normalize_key(entity_type: EntityType, entity_value: str) -> str:
    """Create normalized lookup key for caching.

    Args:
        entity_type: Type of entity
        entity_value: Entity value

    Returns:
        Normalized key string
    """
    # Basic normalization: lowercase, strip whitespace
    key = entity_value.lower().strip()
    # Remove common punctuation
    for char in ".,;:!?()[]{}":
        key = key.replace(char, "")
    return key


def cache_get(
    conn: sqlite3.Connection,
    entity_type: EntityType,
    normalized_key: str,
    source: Optional[EnrichmentSource] = None,
) -> Optional[EnrichmentResult]:
    """Retrieve cached enrichment result.

    Args:
        conn: Database connection
        entity_type: Type of entity
        normalized_key: Normalized lookup key
        source: Optional specific source to check

    Returns:
        EnrichmentResult or None if not found/expired
    """
    now = datetime.now(timezone.utc).isoformat()

    if source:
        query = """
        SELECT * FROM enrichment_cache
        WHERE entity_type = ? AND normalized_key = ? AND source = ?
          AND (expires_at IS NULL OR expires_at > ?)
        ORDER BY confidence DESC
        LIMIT 1
        """
        cursor = conn.execute(query, (entity_type.value, normalized_key, source.value, now))
    else:
        query = """
        SELECT * FROM enrichment_cache
        WHERE entity_type = ? AND normalized_key = ?
          AND (expires_at IS NULL OR expires_at > ?)
        ORDER BY confidence DESC
        LIMIT 1
        """
        cursor = conn.execute(query, (entity_type.value, normalized_key, now))

    row = cursor.fetchone()
    if not row:
        return None

    # Reconstruct EnrichmentResult from cache
    try:
        result = EnrichmentResult(
            entity_type=EntityType(row["entity_type"]),
            entity_value=row["entity_value"],
            normalized_key=row["normalized_key"],
            wikidata_id=row["wikidata_id"],
            viaf_id=row["viaf_id"],
            isni_id=row["isni_id"],
            loc_id=row["loc_id"],
            nli_id=row["nli_id"],
            label=row["label"],
            description=row["description"],
            image_url=row["image_url"],
            wikipedia_url=row["wikipedia_url"],
            sources_used=[EnrichmentSource(row["source"])],
            confidence=row["confidence"] or 0.0,
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
        )

        # Parse JSON fields
        if row["person_info"]:
            from scripts.enrichment.models import PersonInfo
            result.person_info = PersonInfo(**json.loads(row["person_info"]))
        if row["place_info"]:
            from scripts.enrichment.models import PlaceInfo
            result.place_info = PlaceInfo(**json.loads(row["place_info"]))
        if row["external_links"]:
            result.external_links = json.loads(row["external_links"])

        return result
    except Exception:
        return None


def cache_put(
    conn: sqlite3.Connection,
    result: EnrichmentResult,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> None:
    """Store enrichment result in cache.

    Args:
        conn: Database connection
        result: EnrichmentResult to cache
        ttl_days: Time-to-live in days
    """
    fetched_at = result.fetched_at.isoformat() if result.fetched_at else datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()

    # Determine source
    source = result.sources_used[0].value if result.sources_used else EnrichmentSource.CACHE.value

    # Serialize complex fields
    person_info_json = json.dumps(result.person_info.model_dump()) if result.person_info else None
    place_info_json = json.dumps(result.place_info.model_dump()) if result.place_info else None
    external_links_json = json.dumps(result.external_links) if result.external_links else None
    raw_data_json = json.dumps(result.raw_data) if result.raw_data else None

    query = """
    INSERT OR REPLACE INTO enrichment_cache (
        entity_type, entity_value, normalized_key,
        wikidata_id, viaf_id, isni_id, loc_id, nli_id,
        person_info, place_info, label, description,
        image_url, wikipedia_url, external_links,
        source, confidence, raw_data, fetched_at, expires_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    conn.execute(query, (
        result.entity_type.value,
        result.entity_value,
        result.normalized_key,
        result.wikidata_id,
        result.viaf_id,
        result.isni_id,
        result.loc_id,
        result.nli_id,
        person_info_json,
        place_info_json,
        result.label,
        result.description,
        result.image_url,
        result.wikipedia_url,
        external_links_json,
        source,
        result.confidence,
        raw_data_json,
        fetched_at,
        expires_at,
    ))
    conn.commit()


def cache_nli_identifiers(
    conn: sqlite3.Connection,
    nli_ids: NLIAuthorityIdentifiers,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> None:
    """Cache NLI identifier mapping.

    Args:
        conn: Database connection
        nli_ids: NLI authority identifiers
        ttl_days: Time-to-live in days
    """
    fetched_at = nli_ids.fetched_at.isoformat() if nli_ids.fetched_at else datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()

    query = """
    INSERT OR REPLACE INTO nli_identifiers (
        nli_id, nli_uri, wikidata_id, viaf_id, isni_id, loc_id,
        other_ids, fetch_method, fetched_at, expires_at, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    conn.execute(query, (
        nli_ids.nli_id,
        nli_ids.nli_uri,
        nli_ids.wikidata_id,
        nli_ids.viaf_id,
        nli_ids.isni_id,
        nli_ids.loc_id,
        json.dumps(nli_ids.other_ids) if nli_ids.other_ids else None,
        nli_ids.fetch_method,
        fetched_at,
        expires_at,
        "success",
    ))
    conn.commit()


def get_cached_nli_identifiers(
    conn: sqlite3.Connection,
    nli_id: str,
) -> Optional[NLIAuthorityIdentifiers]:
    """Get cached NLI identifier mapping.

    Args:
        conn: Database connection
        nli_id: NLI authority ID

    Returns:
        NLIAuthorityIdentifiers or None
    """
    now = datetime.now(timezone.utc).isoformat()

    query = """
    SELECT * FROM nli_identifiers
    WHERE nli_id = ? AND (expires_at IS NULL OR expires_at > ?)
    LIMIT 1
    """

    cursor = conn.execute(query, (nli_id, now))
    row = cursor.fetchone()

    if not row:
        return None

    return NLIAuthorityIdentifiers(
        nli_id=row["nli_id"],
        nli_uri=row["nli_uri"],
        wikidata_id=row["wikidata_id"],
        viaf_id=row["viaf_id"],
        isni_id=row["isni_id"],
        loc_id=row["loc_id"],
        other_ids=json.loads(row["other_ids"]) if row["other_ids"] else {},
        fetch_method=row["fetch_method"],
        fetched_at=datetime.fromisoformat(row["fetched_at"]) if row["fetched_at"] else datetime.now(timezone.utc),
    )


# =============================================================================
# Enrichment Service
# =============================================================================


class EnrichmentService:
    """Main service for entity enrichment with caching."""

    def __init__(
        self,
        cache_db_path: Optional[Path] = None,
        default_ttl_days: int = DEFAULT_TTL_DAYS,
    ):
        """Initialize enrichment service.

        Args:
            cache_db_path: Path to cache database (default: data/enrichment/cache.db)
            default_ttl_days: Default cache TTL in days
        """
        self.cache_db_path = cache_db_path or Path("data/enrichment/cache.db")
        self.default_ttl_days = default_ttl_days
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get database connection (lazy initialization)."""
        if self._conn is None:
            self._conn = init_cache_db(self.cache_db_path)
        return self._conn

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    async def enrich_entity(
        self,
        entity_type: EntityType,
        entity_value: str,
        nli_authority_uri: Optional[str] = None,
        wikidata_id: Optional[str] = None,
        viaf_id: Optional[str] = None,
        skip_cache: bool = False,
        preferred_sources: Optional[List[EnrichmentSource]] = None,
    ) -> Optional[EnrichmentResult]:
        """Enrich a single entity.

        Lookup strategy:
        1. Check cache first (unless skip_cache=True)
        2. If Wikidata ID provided, use it directly
        3. If NLI URI provided, look up NLI → Wikidata mapping
        4. If VIAF ID provided, try to get Wikidata ID
        5. Fall back to name search

        Args:
            entity_type: Type of entity (AGENT, PLACE, etc.)
            entity_value: Entity value (name, place name, etc.)
            nli_authority_uri: Optional NLI authority URI from MARC $0
            wikidata_id: Optional known Wikidata ID
            viaf_id: Optional known VIAF ID
            skip_cache: If True, bypass cache lookup
            preferred_sources: List of preferred sources

        Returns:
            EnrichmentResult or None if not found
        """
        norm_key = normalize_key(entity_type, entity_value)

        # 1. Check cache first
        if not skip_cache:
            cached = cache_get(self.conn, entity_type, norm_key)
            if cached:
                cached.sources_used = [EnrichmentSource.CACHE] + cached.sources_used
                return cached

        # 2. If Wikidata ID provided, use directly
        if wikidata_id:
            result = await self._enrich_from_wikidata(
                entity_type, entity_value, norm_key, wikidata_id
            )
            if result:
                cache_put(self.conn, result, self.default_ttl_days)
                return result

        # 3. If NLI URI provided, try to get identifiers
        if nli_authority_uri:
            nli_id = extract_nli_id_from_uri(nli_authority_uri)
            if nli_id:
                # Check NLI cache first
                nli_ids = get_cached_nli_identifiers(self.conn, nli_id)

                if not nli_ids:
                    # Try to look up (may not have external IDs due to Cloudflare)
                    nli_ids = await lookup_nli_identifiers(nli_id)
                    if nli_ids:
                        cache_nli_identifiers(self.conn, nli_ids)

                # If we got Wikidata ID from NLI, use it
                if nli_ids and nli_ids.wikidata_id:
                    result = await self._enrich_from_wikidata(
                        entity_type, entity_value, norm_key, nli_ids.wikidata_id
                    )
                    if result:
                        result.nli_id = nli_id
                        cache_put(self.conn, result, self.default_ttl_days)
                        return result

                # If we got VIAF ID from NLI, try to get Wikidata
                if nli_ids and nli_ids.viaf_id and not viaf_id:
                    viaf_id = nli_ids.viaf_id

        # 4. If VIAF ID provided, try to get Wikidata ID
        if viaf_id:
            wikidata_id = await get_wikidata_id_for_viaf(viaf_id)
            if wikidata_id:
                result = await self._enrich_from_wikidata(
                    entity_type, entity_value, norm_key, wikidata_id
                )
                if result:
                    result.viaf_id = viaf_id
                    cache_put(self.conn, result, self.default_ttl_days)
                    return result

        # 5. Fall back to name search
        result = await self._enrich_by_name_search(entity_type, entity_value, norm_key)
        if result:
            cache_put(self.conn, result, self.default_ttl_days)
        return result

    async def _enrich_from_wikidata(
        self,
        entity_type: EntityType,
        entity_value: str,
        norm_key: str,
        wikidata_id: str,
    ) -> Optional[EnrichmentResult]:
        """Enrich from Wikidata by ID.

        Args:
            entity_type: Type of entity
            entity_value: Original entity value
            norm_key: Normalized key
            wikidata_id: Wikidata QID

        Returns:
            EnrichmentResult or None
        """
        if entity_type == EntityType.AGENT:
            result = await enrich_agent_by_id(wikidata_id, norm_key)
        elif entity_type == EntityType.PLACE:
            result = await enrich_place_by_id(wikidata_id, norm_key)
        else:
            # For other types, try agent lookup as default
            result = await enrich_agent_by_id(wikidata_id, norm_key)

        if result:
            result.entity_value = entity_value
            result.normalized_key = norm_key

        return result

    async def _enrich_by_name_search(
        self,
        entity_type: EntityType,
        entity_value: str,
        norm_key: str,
    ) -> Optional[EnrichmentResult]:
        """Enrich by searching for name.

        Args:
            entity_type: Type of entity
            entity_value: Name to search
            norm_key: Normalized key

        Returns:
            Best matching EnrichmentResult or None
        """
        if entity_type == EntityType.AGENT:
            results = await search_agent_by_name(entity_value, limit=3)
        elif entity_type == EntityType.PLACE:
            results = await search_place_by_name(entity_value, limit=3)
        else:
            # Default to agent search
            results = await search_agent_by_name(entity_value, limit=3)

        if results:
            # Return best match (first result usually best)
            best = results[0]
            best.entity_value = entity_value
            best.normalized_key = norm_key
            return best

        return None

    async def enrich_batch(
        self,
        requests: List[EnrichmentRequest],
        parallel: int = 3,
        rate_limit_delay: float = RATE_LIMIT_DELAY,
    ) -> List[Optional[EnrichmentResult]]:
        """Enrich multiple entities.

        Args:
            requests: List of enrichment requests
            parallel: Max parallel requests
            rate_limit_delay: Delay between requests in seconds

        Returns:
            List of EnrichmentResults (None for failed requests)
        """
        results: List[Optional[EnrichmentResult]] = []

        # Process in batches
        for i in range(0, len(requests), parallel):
            batch = requests[i:i + parallel]

            # Create tasks for batch
            tasks = []
            for req in batch:
                task = self.enrich_entity(
                    entity_type=req.entity_type,
                    entity_value=req.entity_value,
                    nli_authority_uri=req.nli_authority_uri,
                )
                tasks.append(task)

            # Execute batch
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for result in batch_results:
                if isinstance(result, Exception):
                    results.append(None)
                else:
                    results.append(result)

            # Rate limiting between batches
            if i + parallel < len(requests):
                await asyncio.sleep(rate_limit_delay)

        return results

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with cache stats
        """
        cursor = self.conn.execute("""
            SELECT
                entity_type,
                source,
                COUNT(*) as count,
                AVG(confidence) as avg_confidence
            FROM enrichment_cache
            GROUP BY entity_type, source
        """)

        stats_by_type = {}
        for row in cursor:
            key = f"{row['entity_type']}_{row['source']}"
            stats_by_type[key] = {
                "count": row["count"],
                "avg_confidence": row["avg_confidence"],
            }

        # Total counts
        cursor = self.conn.execute("SELECT COUNT(*) as total FROM enrichment_cache")
        total = cursor.fetchone()["total"]

        cursor = self.conn.execute("SELECT COUNT(*) as total FROM nli_identifiers")
        nli_total = cursor.fetchone()["total"]

        return {
            "total_cached": total,
            "nli_identifiers_cached": nli_total,
            "by_type_and_source": stats_by_type,
        }

    def clear_expired(self) -> int:
        """Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        now = datetime.now(timezone.utc).isoformat()

        cursor = self.conn.execute(
            "DELETE FROM enrichment_cache WHERE expires_at < ?", (now,)
        )
        count1 = cursor.rowcount

        cursor = self.conn.execute(
            "DELETE FROM nli_identifiers WHERE expires_at < ?", (now,)
        )
        count2 = cursor.rowcount

        self.conn.commit()
        return count1 + count2
