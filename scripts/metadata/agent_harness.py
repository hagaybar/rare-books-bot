"""Shared agent harness for specialist metadata agents.

Provides the foundation for all specialist metadata agents with two layers:
- GroundingLayer: Deterministic queries against M3 database and alias maps (no LLM)
- ReasoningLayer: LLM-assisted mapping proposals with strict prompts and caching

All LLM output is cached, validated, and requires human review before production use.
"""

import json
import os
import sqlite3
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class GapRecord:
    """A low-confidence record identified from the M3 database."""

    mms_id: str
    field: str  # "date", "place", "publisher", "agent"
    raw_value: str
    current_norm: Optional[str]
    confidence: float
    method: str
    country_code: Optional[str] = None


@dataclass
class ProposedMapping:
    """An LLM-proposed canonical mapping for a raw value."""

    raw_value: str
    canonical_value: str
    confidence: float
    reasoning: str
    evidence_sources: List[str] = dc_field(default_factory=list)
    field: str = ""


# ---------------------------------------------------------------------------
# GROUNDING LAYER (deterministic, no LLM)
# ---------------------------------------------------------------------------

# SQL templates for querying gaps by field.
_GAP_QUERIES: Dict[str, str] = {
    "place": """
        SELECT r.mms_id, i.place_raw, i.place_norm, i.place_confidence,
               i.place_method, i.country_code
        FROM imprints i
        JOIN records r ON r.id = i.record_id
        WHERE i.place_confidence <= ?
          AND i.place_raw IS NOT NULL
          AND i.place_raw != ''
    """,
    "date": """
        SELECT r.mms_id, i.date_raw, i.date_label, i.date_confidence,
               i.date_method, i.country_code
        FROM imprints i
        JOIN records r ON r.id = i.record_id
        WHERE i.date_confidence <= ?
          AND i.date_raw IS NOT NULL
          AND i.date_raw != ''
    """,
    "publisher": """
        SELECT r.mms_id, i.publisher_raw, i.publisher_norm, i.publisher_confidence,
               i.publisher_method, i.country_code
        FROM imprints i
        JOIN records r ON r.id = i.record_id
        WHERE i.publisher_confidence <= ?
          AND i.publisher_raw IS NOT NULL
          AND i.publisher_raw != ''
    """,
    "agent": """
        SELECT r.mms_id, a.agent_raw, a.agent_norm, a.agent_confidence,
               a.agent_method, NULL
        FROM agents a
        JOIN records r ON r.id = a.record_id
        WHERE a.agent_confidence <= ?
          AND a.agent_raw IS NOT NULL
          AND a.agent_raw != ''
    """,
}

# Mapping from field name to alias map file name.
_ALIAS_MAP_FILES: Dict[str, str] = {
    "place": "place_aliases/place_alias_map.json",
    "publisher": "publisher_aliases/publisher_alias_map.json",
    "agent": "agent_aliases/agent_alias_map.json",
}

# SQL for counting affected records by raw value per field.
_COUNT_QUERIES: Dict[str, str] = {
    "place": "SELECT COUNT(*) FROM imprints WHERE place_raw = ?",
    "date": "SELECT COUNT(*) FROM imprints WHERE date_raw = ?",
    "publisher": "SELECT COUNT(*) FROM imprints WHERE publisher_raw = ?",
    "agent": "SELECT COUNT(*) FROM agents WHERE agent_raw = ?",
}


class GroundingLayer:
    """Deterministic grounding against M3 database and alias maps.

    No LLM calls. Provides data context for reasoning.
    """

    def __init__(self, db_path: Path, alias_map_dir: Path):
        """Initialize with paths to M3 database and alias map directory.

        Args:
            db_path: Path to M3 SQLite database (bibliographic.db).
            alias_map_dir: Path to normalization alias directory
                           (e.g., data/normalization/).
        """
        self.db_path = db_path
        self.alias_map_dir = alias_map_dir

    def _connect(self) -> sqlite3.Connection:
        """Open a read-only connection to the database."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def query_gaps(
        self, field: str, max_confidence: float = 0.8
    ) -> List[GapRecord]:
        """Query M3 DB for low-confidence records in the given field.

        Args:
            field: One of "date", "place", "publisher", "agent".
            max_confidence: Upper confidence threshold (inclusive).

        Returns:
            List of GapRecord with low-confidence values.

        Raises:
            ValueError: If field is not recognized.
        """
        sql = _GAP_QUERIES.get(field)
        if sql is None:
            raise ValueError(
                f"Unknown field '{field}'. Must be one of: "
                f"{', '.join(sorted(_GAP_QUERIES))}"
            )

        conn = self._connect()
        try:
            rows = conn.execute(sql, (max_confidence,)).fetchall()
            results: List[GapRecord] = []
            for row in rows:
                results.append(
                    GapRecord(
                        mms_id=row[0],
                        field=field,
                        raw_value=row[1] or "",
                        current_norm=row[2],
                        confidence=row[3] if row[3] is not None else 0.0,
                        method=row[4] or "",
                        country_code=row[5],
                    )
                )
            return results
        finally:
            conn.close()

    def query_alias_map(self, field: str) -> Dict[str, str]:
        """Load current alias map for the given field.

        Args:
            field: One of "place", "publisher", "agent".

        Returns:
            Dict mapping raw alias → canonical value.
            Empty dict if file does not exist.
        """
        rel_path = _ALIAS_MAP_FILES.get(field)
        if rel_path is None:
            return {}

        alias_path = self.alias_map_dir / rel_path
        if not alias_path.exists():
            return {}

        with open(alias_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def query_country_codes(self, mms_ids: List[str]) -> Dict[str, str]:
        """Get MARC country codes for given MMS IDs from imprints table.

        Args:
            mms_ids: List of MMS ID strings.

        Returns:
            Dict mapping mms_id → country_code (only non-NULL entries).
        """
        if not mms_ids:
            return {}

        conn = self._connect()
        try:
            placeholders = ",".join("?" for _ in mms_ids)
            sql = f"""
                SELECT r.mms_id, i.country_code
                FROM imprints i
                JOIN records r ON r.id = i.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND i.country_code IS NOT NULL
            """
            rows = conn.execute(sql, mms_ids).fetchall()
            result: Dict[str, str] = {}
            for row in rows:
                result[row[0]] = row[1]
            return result
        finally:
            conn.close()

    def query_authority_uris(self, mms_ids: List[str]) -> Dict[str, str]:
        """Get authority URIs from agents table for given MMS IDs.

        Args:
            mms_ids: List of MMS ID strings.

        Returns:
            Dict mapping mms_id → authority_uri (only non-NULL entries).
        """
        if not mms_ids:
            return {}

        conn = self._connect()
        try:
            placeholders = ",".join("?" for _ in mms_ids)
            sql = f"""
                SELECT r.mms_id, a.authority_uri
                FROM agents a
                JOIN records r ON r.id = a.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND a.authority_uri IS NOT NULL
            """
            rows = conn.execute(sql, mms_ids).fetchall()
            result: Dict[str, str] = {}
            for row in rows:
                result[row[0]] = row[1]
            return result
        finally:
            conn.close()

    def count_affected_records(self, raw_value: str, field: str) -> int:
        """Count how many records have this raw value in the given field.

        Args:
            raw_value: The raw metadata value to count.
            field: One of "date", "place", "publisher", "agent".

        Returns:
            Count of matching records.

        Raises:
            ValueError: If field is not recognized.
        """
        sql = _COUNT_QUERIES.get(field)
        if sql is None:
            raise ValueError(
                f"Unknown field '{field}'. Must be one of: "
                f"{', '.join(sorted(_COUNT_QUERIES))}"
            )

        conn = self._connect()
        try:
            row = conn.execute(sql, (raw_value,)).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# REASONING LAYER (LLM-assisted)
# ---------------------------------------------------------------------------

# System prompt template for propose_mapping.
_PROPOSE_MAPPING_PROMPT = """\
You are a bibliographic metadata specialist working with rare book catalogs (15th-19th century).
Given a raw MARC metadata value, propose the canonical English form.

FIELD: {field}
RAW VALUE: "{raw_value}"
EVIDENCE: {evidence_json}
EXISTING VOCABULARY: {vocabulary}

Respond with ONLY a JSON object:
{{
  "canonical_value": "the canonical English form (lowercase)",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation of your reasoning"
}}

Rules:
- If this is a well-known place/publisher/name, confidence should be >= 0.85
- If uncertain, set confidence < 0.7 and explain why
- For places: use modern English name (lowercase)
- For publishers: use the most common English form
- For dates: provide start_year and end_year if applicable
- Never invent data - if you don't know, say so"""

_EXPLAIN_CLUSTER_PROMPT = """You are a bibliographic metadata specialist.
Explain why the following raw {field} values from rare book catalogs might be related:

Cluster type: {cluster_type}
Values: {values}

Provide a brief, factual explanation (2-3 sentences max)."""

_SUGGEST_INVESTIGATION_PROMPT = """You are a bibliographic metadata specialist.
Suggest next steps for resolving these related {field} values from rare book catalogs:

Cluster type: {cluster_type}
Values: {values}

Provide 2-3 concrete, actionable suggestions for a librarian to investigate."""


class ReasoningLayer:
    """LLM-assisted reasoning for metadata normalization.

    All calls are cached. Results are proposals, not authoritative mappings.
    """

    def __init__(
        self,
        grounding: GroundingLayer,
        cache_path: Path,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
    ):
        """Initialize reasoning layer.

        Args:
            grounding: GroundingLayer instance for context.
            cache_path: Path to JSONL cache file.
            model: OpenAI model name (default gpt-4o).
            api_key: OpenAI API key. Falls back to OPENAI_API_KEY env var.
        """
        self.grounding = grounding
        self.cache_path = cache_path
        self.model = model
        self._api_key = api_key
        self.client = None  # Lazy init
        self._cache: Dict[str, ProposedMapping] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Load cached proposals from JSONL file."""
        if not self.cache_path.exists():
            return
        with open(self.cache_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    key = self._cache_key(entry["field"], entry["raw_value"])
                    result = entry["result"]
                    self._cache[key] = ProposedMapping(
                        raw_value=entry["raw_value"],
                        canonical_value=result["canonical_value"],
                        confidence=result["confidence"],
                        reasoning=result["reasoning"],
                        evidence_sources=result.get("evidence_sources", []),
                        field=entry["field"],
                    )
                except (json.JSONDecodeError, KeyError):
                    continue

    def _write_cache_entry(
        self, field: str, raw_value: str, mapping: ProposedMapping
    ) -> None:
        """Append a single entry to the JSONL cache file."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "field": field,
            "raw_value": raw_value,
            "result": {
                "canonical_value": mapping.canonical_value,
                "confidence": mapping.confidence,
                "reasoning": mapping.reasoning,
                "evidence_sources": mapping.evidence_sources,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.cache_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _cache_key(field: str, raw_value: str) -> str:
        """Deterministic cache key from field + raw_value."""
        return f"{field}::{raw_value}"

    def _get_client(self):
        """Lazy-initialize OpenAI client."""
        if self.client is None:
            from openai import OpenAI

            api_key = self._api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "No OpenAI API key. Set OPENAI_API_KEY or pass api_key."
                )
            self.client = OpenAI(api_key=api_key)
        return self.client

    def _build_vocabulary_context(self, field: str, max_entries: int = 50) -> str:
        """Build vocabulary context string from existing alias map."""
        alias_map = self.grounding.query_alias_map(field)
        if not alias_map:
            return "(no existing mappings)"
        entries = list(alias_map.items())[:max_entries]
        lines = [f'  "{k}" -> "{v}"' for k, v in entries]
        suffix = ""
        if len(alias_map) > max_entries:
            suffix = f"\n  ... and {len(alias_map) - max_entries} more entries"
        return "\n".join(lines) + suffix

    def _build_system_prompt(
        self, field: str, raw_value: str, evidence: Optional[Dict] = None
    ) -> str:
        """Build the system prompt for propose_mapping."""
        vocabulary = self._build_vocabulary_context(field)
        evidence_json = json.dumps(evidence or {}, ensure_ascii=False)
        return _PROPOSE_MAPPING_PROMPT.format(
            field=field,
            raw_value=raw_value,
            evidence_json=evidence_json,
            vocabulary=vocabulary,
        )

    def propose_mapping(
        self,
        raw_value: str,
        field: str,
        evidence: Optional[Dict] = None,
    ) -> ProposedMapping:
        """Ask LLM for canonical mapping with evidence. Cache results.

        Args:
            raw_value: Raw metadata value to normalize.
            field: Metadata field ("place", "publisher", "agent", "date").
            evidence: Optional dict of supporting evidence (country codes, etc.).

        Returns:
            ProposedMapping with canonical value, confidence, and reasoning.
        """
        # 1. Check cache first
        key = self._cache_key(field, raw_value)
        if key in self._cache:
            return self._cache[key]

        # 2. Build prompt
        system_prompt = self._build_system_prompt(field, raw_value, evidence)

        # 3. Call OpenAI API
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f'Normalize this {field} value: "{raw_value}"',
                },
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        # 4. Parse response
        content = response.choices[0].message.content
        parsed = json.loads(content)

        evidence_sources = []
        if evidence:
            evidence_sources = list(evidence.keys())

        mapping = ProposedMapping(
            raw_value=raw_value,
            canonical_value=parsed.get("canonical_value", ""),
            confidence=float(parsed.get("confidence", 0.0)),
            reasoning=parsed.get("reasoning", ""),
            evidence_sources=evidence_sources,
            field=field,
        )

        # 5. Cache result
        self._cache[key] = mapping
        self._write_cache_entry(field, raw_value, mapping)

        return mapping

    def explain_cluster(
        self, cluster_type: str, values: List[str], field: str
    ) -> str:
        """LLM explains why these values are related.

        Args:
            cluster_type: Type of cluster (e.g., "latin_place_names").
            values: List of raw values in the cluster.
            field: Metadata field.

        Returns:
            Explanation string.
        """
        client = self._get_client()
        prompt = _EXPLAIN_CLUSTER_PROMPT.format(
            field=field,
            cluster_type=cluster_type,
            values=json.dumps(values[:20], ensure_ascii=False),
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    def suggest_investigation(
        self, cluster_type: str, values: List[str], field: str
    ) -> str:
        """LLM suggests next steps for investigating this cluster.

        Args:
            cluster_type: Type of cluster.
            values: List of raw values.
            field: Metadata field.

        Returns:
            Suggestions string.
        """
        client = self._get_client()
        prompt = _SUGGEST_INVESTIGATION_PROMPT.format(
            field=field,
            cluster_type=cluster_type,
            values=json.dumps(values[:20], ensure_ascii=False),
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# COMBINED INTERFACE
# ---------------------------------------------------------------------------


class AgentHarness:
    """Combined interface for specialist metadata agents.

    Exposes both the deterministic grounding layer and the LLM-assisted
    reasoning layer through a single entry point.
    """

    def __init__(
        self,
        db_path: Path,
        alias_map_dir: Path,
        cache_path: Optional[Path] = None,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
    ):
        """Initialize agent harness with both layers.

        Args:
            db_path: Path to M3 SQLite database.
            alias_map_dir: Path to normalization alias directory.
            cache_path: Path to JSONL LLM cache (default:
                        data/metadata/agent_llm_cache.jsonl).
            api_key: OpenAI API key (falls back to env var).
            model: OpenAI model name.
        """
        self.grounding = GroundingLayer(db_path, alias_map_dir)
        cache = cache_path or Path("data/metadata/agent_llm_cache.jsonl")
        self.reasoning = ReasoningLayer(
            self.grounding, cache, api_key=api_key, model=model
        )

    # -- Grounding delegates --------------------------------------------------

    def query_gaps(
        self, field: str, max_confidence: float = 0.8
    ) -> List[GapRecord]:
        """Query M3 DB for low-confidence records in the given field."""
        return self.grounding.query_gaps(field, max_confidence)

    def query_alias_map(self, field: str) -> Dict[str, str]:
        """Load current alias map for the given field."""
        return self.grounding.query_alias_map(field)

    def query_country_codes(self, mms_ids: List[str]) -> Dict[str, str]:
        """Get MARC country codes for given MMS IDs."""
        return self.grounding.query_country_codes(mms_ids)

    def query_authority_uris(self, mms_ids: List[str]) -> Dict[str, str]:
        """Get authority URIs from agents table for given MMS IDs."""
        return self.grounding.query_authority_uris(mms_ids)

    def count_affected_records(self, raw_value: str, field: str) -> int:
        """Count how many records have this raw value."""
        return self.grounding.count_affected_records(raw_value, field)

    # -- Reasoning delegates ---------------------------------------------------

    def propose_mapping(
        self,
        raw_value: str,
        field: str,
        evidence: Optional[Dict] = None,
    ) -> ProposedMapping:
        """Ask LLM for canonical mapping with evidence."""
        return self.reasoning.propose_mapping(raw_value, field, evidence)

    def explain_cluster(
        self, cluster_type: str, values: List[str], field: str
    ) -> str:
        """LLM explains why these values are related."""
        return self.reasoning.explain_cluster(cluster_type, values, field)

    def suggest_investigation(
        self, cluster_type: str, values: List[str], field: str
    ) -> str:
        """LLM suggests next steps for investigating this cluster."""
        return self.reasoning.suggest_investigation(cluster_type, values, field)
