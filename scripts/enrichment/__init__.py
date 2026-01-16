"""Enrichment Pipeline for Metadata Enhancement.

This package provides external data enrichment for bibliographic records:
- NLI Authority Lookup: Extract Wikidata/VIAF IDs from NLI authority pages
- Wikidata Integration: Fetch entity information via SPARQL
- VIAF Integration: Authority record lookups
- Caching: Local cache to avoid repeated requests

Architecture:
-----------

1. MARC records contain authority URIs in $0 subfields:
   - Format: https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities/{NLI_ID}.jsonld
   - Example: 987007261327805171

2. NLI Authority pages contain external identifiers:
   - Page: https://www.nli.org.il/en/authorities/{NLI_ID}
   - External IDs in <div class="additional-identity-container">:
     - Wikidata ID (e.g., Q123456)
     - VIAF ID (e.g., 12345678)
     - ISNI
     - LC/NAF ID

3. With Wikidata/VIAF IDs, we can fetch:
   - Birth/death dates
   - Biographical info
   - Related entities
   - Images
   - External links

Cloudflare Note:
---------------
NLI uses Cloudflare protection. For automated access:
- Use Playwright (browser automation) via MCP
- Or cache manually obtained IDs
- The JSONLD endpoint works but lacks external identifiers

Modules:
-------
- nnl_client: Fetch NLI authority pages for external IDs
- wikidata_client: SPARQL queries to Wikidata
- viaf_client: VIAF API integration
- enrichment_service: Main service with caching
- schema.sql: Cache database schema
"""

from scripts.enrichment.models import (
    EnrichmentSource,
    EnrichmentResult,
    EnrichmentRequest,
    EntityType,
    PersonInfo,
    PlaceInfo,
)
from scripts.enrichment.enrichment_service import EnrichmentService

__all__ = [
    "EnrichmentSource",
    "EnrichmentResult",
    "EnrichmentRequest",
    "EntityType",
    "PersonInfo",
    "PlaceInfo",
    "EnrichmentService",
]
