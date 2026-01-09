#!/usr/bin/env python3
"""
generate_place_alias_map.py

Goal:
  place_norm (unique)  ->  English canonical place key (lowercase ASCII)

Inputs:
  - places_freq.csv with columns: place_norm,count

Outputs:
  - place_alias_proposed.csv  (review-friendly, includes counts + decisions + notes)
  - place_alias_map.json      (only KEEP/MAP rows that pass guardrails)

Guardrails:
  - Auto-KEEP if place_norm already looks like a valid canonical key (e.g., "london")
  - Deterministic bracket stripping: "[paris]" -> "paris"
  - LLM must return strict structured JSON (Pydantic parsing)
  - Post-validate and fail closed (UNKNOWN -> keep input unchanged)
  - Optional fallback model for hard cases
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError, field_validator

# OpenAI SDK (Responses API)
from openai import OpenAI


# ----------------------------
# Canonical key policy
# ----------------------------

# Canonical keys must be lowercase ASCII, words separated by single spaces.
# Example: "tel aviv", "new york", "frankfurt"
CANON_RE = re.compile(r"^[a-z0-9]+(?: [a-z0-9]+)*$")

# If you want to allow a few special abbreviations, whitelist them here.
SPECIAL_CANON = {"s.l.": "s.l."}  # sine loco; keep as-is (optional)

# Inputs that are inherently ambiguous and should never be auto-mapped by LLM alone.
# (You can expand this list over time.)
ALWAYS_AMBIGUOUS = {
    "frankfurt",
    "alexandria",
    "newcastle",
}

# Inputs that are not places (or are placeholders) you may want to keep unchanged.
PLACEHOLDER_KEYS = {"s.l.", "[s.l.]", "sine loco"}


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def collapse_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def strip_outer_brackets(s: str) -> str:
    s2 = s.strip()
    if s2.startswith("[") and s2.endswith("]") and len(s2) > 2:
        return s2[1:-1].strip()
    return s2


def looks_like_canonical(place_norm: str) -> bool:
    # already clean English key
    return bool(CANON_RE.match(place_norm))


def postprocess_canonical(raw: str) -> str:
    """
    Make the LLM output safer, without letting it "wander":
    - lowercase
    - replace hyphen/underscore with space
    - remove obvious punctuation
    - collapse spaces
    Then validate against CANON_RE (or SPECIAL_CANON).
    """
    s = nfkc(raw).casefold()
    if s in SPECIAL_CANON:
        return s

    # Normalize separators
    s = s.replace("-", " ").replace("_", " ")
    # Remove punctuation that commonly sneaks in
    s = re.sub(r"[,:;()\[\]\"'“”‘’]", " ", s)
    s = collapse_spaces(s)
    return s


def validate_canonical(place_norm_in: str, canonical_out: str, decision: str) -> Tuple[bool, str]:
    """
    Hard rules:
      - canonical must match CANON_RE (or be whitelisted in SPECIAL_CANON)
      - if decision == KEEP, canonical must equal input exactly
      - NEVER auto-map ALWAYS_AMBIGUOUS
    """
    if canonical_out in SPECIAL_CANON:
        # Only allow exact whitelisted special strings
        return True, ""

    if not CANON_RE.match(canonical_out):
        return False, "canonical_bad_format"

    if decision == "KEEP" and canonical_out != place_norm_in:
        return False, "keep_must_equal_input"

    if place_norm_in in ALWAYS_AMBIGUOUS and decision == "MAP":
        return False, "input_marked_ambiguous"

    return True, ""


# ----------------------------
# Structured Output Model
# ----------------------------

class PlaceNormResult(BaseModel):
    decision: str = Field(..., description="KEEP|MAP|AMBIGUOUS|UNKNOWN")
    canonical: str = Field(..., description="Lowercase ASCII canonical place key")
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: str = Field("", description="<= 12 words")

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        allowed = {"KEEP", "MAP", "AMBIGUOUS", "UNKNOWN"}
        if v not in allowed:
            raise ValueError(f"decision must be one of {allowed}")
        return v

    @field_validator("notes")
    @classmethod
    def short_notes(cls, v: str) -> str:
        # soft limit; do not fail hard on notes length
        return v.strip()[:200]


# ----------------------------
# LLM prompting
# ----------------------------

SYSTEM_INSTRUCTIONS = (
    "You normalize imprint place keys into an English canonical key for faceting. "
    "Follow the schema exactly. Never invent qualifiers. If ambiguous, say AMBIGUOUS."
)

def build_user_prompt(place_norm: str, count: int, examples: Optional[List[str]] = None) -> str:
    # examples optional; you can add later if you export examples.json
    examples_part = ""
    if examples:
        examples_part = f"\nRaw examples: {json.dumps(examples, ensure_ascii=False)}\n"

    return f"""
Task: Map one imprint place key to ONE English canonical key.

Rules:
1) Output must match the provided JSON schema (no prose).
2) canonical must be lowercase ASCII; only letters/digits/spaces (no punctuation).
3) If input already is a valid English key (e.g., "london", "paris"), decision="KEEP" and canonical MUST equal the input.
4) If input is a clear variant/transliteration/Latin form that maps to a known modern place, decision="MAP".
5) If multiple modern places are plausible (e.g., "frankfurt", "alexandria"), decision="AMBIGUOUS" and canonical=input unchanged.
6) If you cannot determine, decision="UNKNOWN" and canonical=input unchanged.
7) Do NOT add country/region qualifiers (avoid "paris france", "london uk").

Input place_norm: "{place_norm}"
Count: {count}{examples_part}
Return JSON only.
""".strip()


# ----------------------------
# Cache utilities
# ----------------------------

def load_cache(cache_path: Path) -> Dict[str, dict]:
    cache: Dict[str, dict] = {}
    if not cache_path.exists():
        return cache
    with cache_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            cache[obj["place_norm"]] = obj
    return cache


def append_cache(cache_path: Path, row: dict) -> None:
    with cache_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ----------------------------
# Main normalization loop
# ----------------------------

@dataclass
class Row:
    place_norm: str
    count: int


def read_places_freq(csv_path: Path, top_n: int) -> List[Row]:
    rows: List[Row] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "place_norm" not in reader.fieldnames or "count" not in reader.fieldnames:
            raise ValueError("CSV must contain headers: place_norm,count")
        for r in reader:
            pn = (r["place_norm"] or "").strip()
            if not pn:
                continue
            rows.append(Row(place_norm=pn, count=int(r["count"])))
    # sort by count desc then name asc
    rows.sort(key=lambda x: (-x.count, x.place_norm))
    return rows[:top_n]


def auto_rules(place_norm: str) -> Optional[PlaceNormResult]:
    """
    Deterministic shortcuts BEFORE calling LLM.
    """
    s = nfkc(place_norm).casefold()

    # Placeholder / special cases
    if s in PLACEHOLDER_KEYS:
        # keep unchanged; let humans decide later
        return PlaceNormResult(decision="UNKNOWN", canonical=s, confidence=0.0, notes="placeholder")

    # Deterministic bracket stripping: "[paris]" -> "paris"
    stripped = strip_outer_brackets(s)
    if stripped != s and looks_like_canonical(stripped):
        return PlaceNormResult(decision="MAP", canonical=stripped, confidence=0.95, notes="strip brackets")

    # Already clean canonical English key -> KEEP without LLM
    if looks_like_canonical(s):
        return PlaceNormResult(decision="KEEP", canonical=s, confidence=0.90, notes="already canonical")

    # Always ambiguous list -> force AMBIGUOUS
    if s in ALWAYS_AMBIGUOUS:
        return PlaceNormResult(decision="AMBIGUOUS", canonical=s, confidence=0.0, notes="known ambiguous")

    return None


def call_model(client: OpenAI, model: str, place_norm: str, count: int) -> PlaceNormResult:
    prompt = build_user_prompt(place_norm=place_norm, count=count)

    # Using Responses API structured parsing (Pydantic) for strong guardrails
    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        text_format=PlaceNormResult,
    )
    return resp.output_parsed


def normalize_one(
    client: OpenAI,
    place_norm: str,
    count: int,
    model_primary: str,
    model_fallback: Optional[str] = None,
) -> dict:
    """
    Returns a dict row that will be written to proposed CSV and cache.
    """
    # 1) deterministic pre-rules
    pre = auto_rules(place_norm)
    if pre is not None:
        canonical = postprocess_canonical(pre.canonical)
        ok, reason = validate_canonical(nfkc(place_norm).casefold(), canonical, pre.decision)
        if not ok:
            return {
                "place_norm": place_norm,
                "canonical": nfkc(place_norm).casefold(),
                "decision": "UNKNOWN",
                "confidence": 0.0,
                "notes": f"auto_rule_invalid:{reason}",
                "method": "auto_invalid",
                "count": count,
            }
        return {
            "place_norm": place_norm,
            "canonical": canonical,
            "decision": pre.decision,
            "confidence": float(pre.confidence),
            "notes": pre.notes,
            "method": "auto_rule",
            "count": count,
        }

    # 2) LLM primary
    try:
        out = call_model(client, model_primary, nfkc(place_norm).casefold(), count)
    except Exception as e:
        return {
            "place_norm": place_norm,
            "canonical": nfkc(place_norm).casefold(),
            "decision": "UNKNOWN",
            "confidence": 0.0,
            "notes": f"primary_error:{type(e).__name__}",
            "method": "llm_primary_error",
            "count": count,
        }

    canonical = postprocess_canonical(out.canonical)
    ok, reason = validate_canonical(nfkc(place_norm).casefold(), canonical, out.decision)

    # 3) if invalid or weak -> optional fallback
    need_fallback = (
        (not ok)
        or out.decision in {"AMBIGUOUS", "UNKNOWN"}
        or float(out.confidence) < 0.75
    )

    if need_fallback and model_fallback:
        try:
            out2 = call_model(client, model_fallback, nfkc(place_norm).casefold(), count)
            canonical2 = postprocess_canonical(out2.canonical)
            ok2, reason2 = validate_canonical(nfkc(place_norm).casefold(), canonical2, out2.decision)
            if ok2 and (out2.decision in {"KEEP", "MAP"}) and float(out2.confidence) >= float(out.confidence):
                return {
                    "place_norm": place_norm,
                    "canonical": canonical2,
                    "decision": out2.decision,
                    "confidence": float(out2.confidence),
                    "notes": out2.notes,
                    "method": "llm_fallback",
                    "count": count,
                }
        except Exception:
            pass  # keep primary result

    if not ok:
        return {
            "place_norm": place_norm,
            "canonical": nfkc(place_norm).casefold(),
            "decision": "UNKNOWN",
            "confidence": 0.0,
            "notes": f"invalid_llm:{reason}",
            "method": "llm_invalid_fallback",
            "count": count,
        }

    return {
        "place_norm": place_norm,
        "canonical": canonical,
        "decision": out.decision,
        "confidence": float(out.confidence),
        "notes": out.notes,
        "method": "llm_primary",
        "count": count,
    }


# ----------------------------
# Outputs
# ----------------------------

def write_proposed_csv(rows: List[dict], out_path: Path) -> None:
    fieldnames = ["place_norm", "canonical", "decision", "confidence", "method", "count", "notes"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_alias_map_json(rows: List[dict], out_path: Path, min_conf: float) -> None:
    """
    Only write entries that are safe to apply automatically.
    - KEEP: no need to store (identity), but we can include for completeness if you want.
    - MAP: store {place_norm -> canonical}
    """
    alias: Dict[str, str] = {}
    for r in rows:
        if r["decision"] == "MAP" and float(r["confidence"]) >= min_conf:
            alias[nfkc(r["place_norm"]).casefold()] = r["canonical"]

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(alias, f, ensure_ascii=False, indent=2, sort_keys=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--places_csv", required=True, help="places_freq.csv path")
    ap.add_argument("--top_n", type=int, default=200, help="how many places to process (by count)")
    ap.add_argument("--out_proposed_csv", default="place_alias_proposed.csv")
    ap.add_argument("--out_alias_json", default="place_alias_map.json")
    ap.add_argument("--cache_jsonl", default="place_alias_cache.jsonl")
    ap.add_argument("--min_conf", type=float, default=0.85, help="min confidence for MAP to enter alias json")
    ap.add_argument("--model_primary", default="gpt-4.1")
    ap.add_argument("--model_fallback", default="gpt-4.1")
    args = ap.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set", file=sys.stderr)
        sys.exit(2)

    client = OpenAI()

    places_csv = Path(args.places_csv)
    cache_path = Path(args.cache_jsonl)
    out_proposed = Path(args.out_proposed_csv)
    out_alias = Path(args.out_alias_json)

    items = read_places_freq(places_csv, args.top_n)
    cache = load_cache(cache_path)

    out_rows: List[dict] = []
    for row in items:
        if row.place_norm in cache:
            out_rows.append(cache[row.place_norm])
            continue

        result = normalize_one(
            client=client,
            place_norm=row.place_norm,
            count=row.count,
            model_primary=args.model_primary,
            model_fallback=args.model_fallback,
        )
        out_rows.append(result)
        append_cache(cache_path, result)

    # deterministic output ordering
    out_rows.sort(key=lambda r: (-int(r["count"]), str(r["place_norm"])))

    write_proposed_csv(out_rows, out_proposed)
    write_alias_map_json(out_rows, out_alias, min_conf=args.min_conf)

    print(f"Wrote proposed review CSV: {out_proposed}")
    print(f"Wrote alias map JSON (MAP + conf >= {args.min_conf}): {out_alias}")
    print(f"Cache: {cache_path} (delete it to re-run from scratch)")

if __name__ == "__main__":
    main()
