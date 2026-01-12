"""Agent and role normalization functions.

Deterministic, rule-based normalization for agent names and roles.
No LLM calls. All normalization is reversible and confidence-scored.
"""

import re
import unicodedata
from typing import Optional, Tuple


def normalize_agent_base(agent_raw: str) -> str:
    """Deterministic base normalization for agent names.

    Args:
        agent_raw: Raw agent name string from M1 (e.g., "Manutius, Aldus, 1450?-1515")

    Returns:
        Normalized agent key (lowercase, minimal punctuation, whitespace collapsed)

    Rules:
        - Casefold (lowercase)
        - Trim leading/trailing whitespace
        - Collapse internal whitespace to single spaces
        - Strip trailing punctuation (commas, periods, colons, semicolons)
        - Remove bracket wrappers [...]
        - Keep diacritics (consistent with place normalization)
        - Keep internal commas (for name structure like "Surname, First")
        - DO NOT expand abbreviations or invent data
        - DO NOT remove dates or qualifiers (kept for disambiguation)

    Examples:
        "Manutius, Aldus, 1450?-1515" → "manutius, aldus, 1450?-1515"
        "[Oxford University Press]" → "oxford university press"
        "Elsevier, " → "elsevier"
        "Smith, John" → "smith, john"
        "Pagliarini, Marco," → "pagliarini, marco"
    """
    if not agent_raw:
        return ""

    # Remove brackets
    normalized = agent_raw.strip()
    if normalized.startswith('[') and normalized.endswith(']'):
        normalized = normalized[1:-1].strip()

    # Unicode normalize (NFKC) - same as place/publisher
    normalized = unicodedata.normalize('NFKC', normalized)

    # Casefold
    normalized = normalized.lower()

    # Strip trailing punctuation
    normalized = normalized.rstrip('.,;:')

    # Strip whitespace again
    normalized = normalized.strip()

    # Collapse internal whitespace
    normalized = ' '.join(normalized.split())

    return normalized


def normalize_role_base(role_raw: Optional[str]) -> Tuple[str, float, str]:
    """Map role string to controlled vocabulary.

    Uses explicit mapping table for common variants.
    Returns ("other", low_confidence) for unknown roles.

    Args:
        role_raw: Raw role string from M1 (relator code, term, or inferred)

    Returns:
        Tuple of (role_norm, confidence, method) where:
        - role_norm: Controlled vocabulary term
        - confidence: 0.0-1.0
        - method: Normalization method used

    Controlled vocabulary (90+ roles for rare books and manuscripts):
        Authors: author, creator, compiler, contributor
        Editors: editor, annotator, commentator, corrector, proofreader, redactor, reviewer
        Writers: writer_of_preface, author_of_introduction, author_of_afterword
        Translation: translator
        Visual Arts: artist, illustrator, illuminator, engraver, etcher, lithographer,
                     wood_engraver, draftsman, colorist, printmaker, photographer
        Production: printer, publisher, binder, book_designer, book_producer, typographer,
                    papermaker, marbler, manufacturer, distributor
        Manuscripts: scribe, calligrapher, rubricator, inscriber
        Cartography: cartographer, surveyor, delineator
        Provenance: former_owner, owner, collector, donor, bookseller, curator
        Patronage: dedicatee, patron, funder, sponsor, honoree
        Conservation: conservator, restorationist
        Other: facsimilist, signer, witness, censor, expert, researcher, other
    """
    if not role_raw:
        return ("other", 0.5, "missing_role")

    role_clean = role_raw.strip().lower()

    # Relator code mappings (ISO 639 codes - high confidence)
    RELATOR_CODE_MAP = {
        # Authors and creators
        'aut': 'author',
        'cre': 'creator',
        'asn': 'associated_name',
        'com': 'compiler',
        'ctb': 'contributor',
        'oth': 'other',

        # Editors and textual work
        'edt': 'editor',
        'ann': 'annotator',
        'cmm': 'commentator',
        'crr': 'corrector',
        'pfr': 'proofreader',
        'red': 'redactor',
        'rev': 'reviewer',
        'wpr': 'writer_of_preface',
        'aui': 'author_of_introduction',
        'aft': 'author_of_afterword',
        'wam': 'writer_of_accompanying_material',

        # Translation
        'trl': 'translator',

        # Visual arts and illustration
        'art': 'artist',
        'ill': 'illustrator',
        'ilu': 'illuminator',
        'eng': 'engraver',
        'etr': 'etcher',
        'ltg': 'lithographer',
        'wde': 'wood_engraver',
        'drm': 'draftsman',
        'clr': 'colorist',
        'acp': 'art_copyist',
        'pnc': 'penciller',
        'ink': 'inker',
        'prm': 'printmaker',
        'pop': 'printer_of_plates',
        'plt': 'platemaker',

        # Book production and design
        'prt': 'printer',
        'pbl': 'publisher',
        'bnd': 'binder',
        'bdd': 'binding_designer',
        'bkd': 'book_designer',
        'bkp': 'book_producer',
        'bjd': 'bookjacket_designer',
        'bpd': 'bookplate_designer',
        'bka': 'book_artist',
        'cov': 'cover_designer',
        'tyd': 'type_designer',
        'tyg': 'typographer',
        'ppm': 'papermaker',
        'mrb': 'marbler',
        'mfr': 'manufacturer',
        'dst': 'distributor',

        # Manuscript and scribal
        'scr': 'scribe',
        'cll': 'calligrapher',
        'rbr': 'rubricator',
        'ins': 'inscriber',

        # Cartography
        'ctg': 'cartographer',
        'srv': 'surveyor',
        'dln': 'delineator',

        # Provenance and ownership
        'fmo': 'former_owner',
        'own': 'owner',
        'col': 'collector',
        'dnr': 'donor',
        'bsl': 'bookseller',
        'rps': 'repository',
        'cur': 'curator',
        'cor': 'collection_registrar',

        # Dedication and patronage
        'dte': 'dedicatee',
        'pat': 'patron',
        'fnd': 'funder',
        'spn': 'sponsor',
        'hnr': 'honoree',

        # Photography
        'pht': 'photographer',

        # Conservation
        'con': 'conservator',
        'rsr': 'restorationist',

        # Other specialized roles
        'fac': 'facsimilist',
        'sgn': 'signer',
        'wit': 'witness',
        'cns': 'censor',
        'lse': 'licensee',
        'lso': 'licensor',
        'res': 'researcher',
        'exp': 'expert',
    }

    if role_clean in RELATOR_CODE_MAP:
        return (RELATOR_CODE_MAP[role_clean], 0.99, "relator_code")

    # Relator term mappings (English terms - medium-high confidence)
    RELATOR_TERM_MAP = {
        # Authors and creators
        'author': 'author',
        'creator': 'creator',
        'associated name': 'associated_name',
        'compiler': 'compiler',
        'contributor': 'contributor',

        # Editors and textual work
        'editor': 'editor',
        'annotator': 'annotator',
        'commentator': 'commentator',
        'corrector': 'corrector',
        'proofreader': 'proofreader',
        'redactor': 'redactor',
        'reviewer': 'reviewer',
        'writer of preface': 'writer_of_preface',
        'author of introduction': 'author_of_introduction',
        'author of afterword': 'author_of_afterword',
        'writer of accompanying material': 'writer_of_accompanying_material',

        # Translation
        'translator': 'translator',

        # Visual arts and illustration
        'artist': 'artist',
        'illustrator': 'illustrator',
        'illuminator': 'illuminator',
        'engraver': 'engraver',
        'etcher': 'etcher',
        'lithographer': 'lithographer',
        'wood engraver': 'wood_engraver',
        'draftsman': 'draftsman',
        'colorist': 'colorist',
        'art copyist': 'art_copyist',
        'penciller': 'penciller',
        'inker': 'inker',
        'printmaker': 'printmaker',
        'printer of plates': 'printer_of_plates',
        'platemaker': 'platemaker',

        # Book production and design
        'printer': 'printer',
        'publisher': 'publisher',
        'binder': 'binder',
        'binding designer': 'binding_designer',
        'book designer': 'book_designer',
        'book producer': 'book_producer',
        'bookjacket designer': 'bookjacket_designer',
        'bookplate designer': 'bookplate_designer',
        'book artist': 'book_artist',
        'cover designer': 'cover_designer',
        'type designer': 'type_designer',
        'typographer': 'typographer',
        'papermaker': 'papermaker',
        'marbler': 'marbler',
        'manufacturer': 'manufacturer',
        'distributor': 'distributor',

        # Manuscript and scribal
        'scribe': 'scribe',
        'calligrapher': 'calligrapher',
        'rubricator': 'rubricator',
        'inscriber': 'inscriber',

        # Cartography
        'cartographer': 'cartographer',
        'surveyor': 'surveyor',
        'delineator': 'delineator',

        # Provenance and ownership
        'former owner': 'former_owner',
        'owner': 'owner',
        'collector': 'collector',
        'donor': 'donor',
        'bookseller': 'bookseller',
        'repository': 'repository',
        'curator': 'curator',
        'collection registrar': 'collection_registrar',

        # Dedication and patronage
        'dedicatee': 'dedicatee',
        'patron': 'patron',
        'funder': 'funder',
        'sponsor': 'sponsor',
        'honoree': 'honoree',

        # Photography
        'photographer': 'photographer',

        # Conservation
        'conservator': 'conservator',
        'restorationist': 'restorationist',

        # Other specialized roles
        'facsimilist': 'facsimilist',
        'signer': 'signer',
        'witness': 'witness',
        'censor': 'censor',
        'licensee': 'licensee',
        'licensor': 'licensor',
        'researcher': 'researcher',
        'expert': 'expert',

        # Common abbreviations and variants
        'impr.': 'printer',
        'impr': 'printer',
        'print.': 'printer',
        'pub.': 'publisher',
        'pub': 'publisher',
        'publ.': 'publisher',
        'ed.': 'editor',
        'ed': 'editor',
        'edit.': 'editor',
        'trans.': 'translator',
        'trans': 'translator',
        'tran.': 'translator',
        'tr.': 'translator',
        'tr': 'translator',
        'engr.': 'engraver',
        'engr': 'engraver',
        'illus.': 'illustrator',
        'illus': 'illustrator',
        'ill.': 'illustrator',
        'phot.': 'photographer',
        'annot.': 'annotator',
    }

    if role_clean in RELATOR_TERM_MAP:
        return (RELATOR_TERM_MAP[role_clean], 0.95, "relator_term")

    # Inferred roles from tag type (lower confidence)
    # These come from the parser when no explicit relator is present
    if role_clean == 'author':
        return ('author', 0.85, "inferred_from_tag")
    elif role_clean == 'creator':
        return ('creator', 0.85, "inferred_from_tag")

    # Unknown role
    return ("other", 0.6, "unmapped")


def normalize_agent_with_alias_map(
    agent_raw: str,
    agent_alias_map: Optional[dict] = None
) -> Tuple[str, float, str, Optional[str]]:
    """Normalize agent name with optional alias map lookup.

    Args:
        agent_raw: Raw agent name string
        agent_alias_map: Optional dict mapping normalized keys to canonical forms
            Expected structure: {
                "normalized_key": {
                    "decision": "KEEP" | "MAP" | "AMBIGUOUS",
                    "canonical": "canonical_form",
                    "confidence": 0.0-1.0,
                    "notes": "..."
                }
            }

    Returns:
        Tuple of (agent_norm, confidence, method, notes) where:
        - agent_norm: Canonical agent name (or normalized if no alias map)
        - confidence: 0.0-1.0
        - method: "base_clean", "alias_map", or "ambiguous"
        - notes: Optional notes or warnings
    """
    # Base normalization
    agent_norm_base = normalize_agent_base(agent_raw)

    if not agent_norm_base:
        return ("", 0.0, "empty_after_cleaning", "Agent name empty after cleaning")

    # Check alias map if provided
    if agent_alias_map and agent_norm_base in agent_alias_map:
        alias_entry = agent_alias_map[agent_norm_base]
        decision = alias_entry.get("decision", "KEEP")

        if decision == "MAP":
            return (
                alias_entry["canonical"],
                alias_entry.get("confidence", 0.95),
                "alias_map",
                alias_entry.get("notes")
            )
        elif decision == "AMBIGUOUS":
            return (
                "ambiguous",
                alias_entry.get("confidence", 0.5),
                "ambiguous",
                alias_entry.get("notes", "Agent identity ambiguous")
            )
        # KEEP falls through to base normalization

    # Default: base normalization only
    return (agent_norm_base, 0.80, "base_clean", None)
