"""Shared Pydantic models used across multiple modules.

Model Organization:
- scripts/chat/models.py: Chat session, messages, conversation state
- scripts/chat/plan_models.py: Execution plan, steps, grounding data, narrator I/O
- scripts/schemas/query_plan.py: Query filters and plans (M4 layer)
- scripts/enrichment/models.py: Enrichment pipeline I/O
- scripts/marc/models.py: MARC XML canonical records (M1)
- scripts/marc/m2_models.py: Normalization layer (M2)
- scripts/query/models.py: Query execution results
- app/api/models.py: API request/response wrappers
- app/api/auth_models.py: Authentication models
- app/api/metadata_models.py: Metadata quality UI models
"""
from pydantic import BaseModel


class ExternalLink(BaseModel):
    """Unified external reference link used across grounding and enrichment.

    Covers Primo catalog links, Wikipedia, Wikidata, VIAF, NLI, ISNI, LoC.
    """
    source: str  # "primo", "wikipedia", "wikidata", "viaf", "nli", "loc", "isni"
    label: str  # Human-readable display label
    url: str  # The actual URL
    entity_type: str | None = None  # "record" or "agent" (grounding context)
    entity_id: str | None = None  # mms_id or agent name (grounding context)
    identifier: str | None = None  # Raw identifier value (enrichment context)
