"""QA test: populate publisher authority schema with real research data against the real DB.

This script tests the PublisherAuthorityStore API by:
1. Initializing the schema in the real bibliographic.db
2. Creating 14 diverse publisher authority records from publisher_research.json
3. Adding variants, linking to imprints, and verifying roundtrips
4. Producing a JSON test report at data/metadata/publisher_authority_test_report.json
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.metadata.publisher_authority import (
    PublisherAuthority,
    PublisherAuthorityStore,
    PublisherVariant,
    detect_script,
)

DB_PATH = PROJECT_ROOT / "data" / "index" / "bibliographic.db"
RESEARCH_PATH = PROJECT_ROOT / "data" / "normalization" / "publisher_research.json"
REPORT_PATH = PROJECT_ROOT / "data" / "metadata" / "publisher_authority_test_report.json"

# ---------------------------------------------------------------------------
# Publisher test definitions (from research data + manually curated variants)
# ---------------------------------------------------------------------------

# Each entry: (canonical_name, type, confidence, dates_active, date_start,
#              date_end, location, notes, sources, is_missing_marker,
#              viaf_id, wikidata_id, cerl_id,
#              variants: list of (form, script, language, is_primary, notes))

PUBLISHERS_TO_TEST = [
    # 1. House of Elzevir -- printing dynasty, 2 Latin variants
    {
        "canonical_name": "House of Elzevir",
        "type": "printing_house",
        "confidence": 0.95,
        "dates_active": "1583-1712",
        "date_start": 1583,
        "date_end": 1712,
        "location": "Leiden/Amsterdam, Netherlands",
        "notes": "Elzevir family printing house. Famous for elegant small-format editions.",
        "sources": ["https://en.wikipedia.org/wiki/House_of_Elzevir"],
        "is_missing_marker": False,
        "viaf_id": "133818802",
        "wikidata_id": "Q1646568",
        "cerl_id": None,
        "variants": [
            ("ex officina elzeviriana", "latin", "la", True, "Latin form on title pages"),
            ("ex officina elseviriorum", "latin", "la", False, "Variant Latin spelling"),
        ],
    },
    # 2. Bragadin Press, Venice -- Hebrew printer with Italian + Hebrew variants
    {
        "canonical_name": "Bragadin Press, Venice",
        "type": "printing_house",
        "confidence": 0.98,
        "dates_active": "1550-1710",
        "date_start": 1550,
        "date_end": 1710,
        "location": "Venice, Italy",
        "notes": "Hebrew printing house founded by Alvise Bragadin. Near-monopoly on Hebrew printing in Venice.",
        "sources": ["https://www.encyclopedia.com/religion/encyclopedias-almanacs-transcripts-and-maps/bragadinideg"],
        "is_missing_marker": False,
        "viaf_id": None,
        "wikidata_id": None,
        "cerl_id": None,
        "variants": [
            ("nella stamparia bragadina", "latin", "it", True, "Italian imprint form"),
            ("g. bragadin", "latin", "it", False, "Abbreviated Italian form"),
            ("דפוס bragadin", "hebrew", "he", False, "Mixed Hebrew-Latin form"),
        ],
    },
    # 3. Daniel Bomberg, Venice -- Hebrew variant + major printer
    {
        "canonical_name": "Daniel Bomberg, Venice",
        "type": "printing_house",
        "confidence": 0.99,
        "dates_active": "1516-1549",
        "date_start": 1516,
        "date_end": 1549,
        "location": "Venice, Italy",
        "notes": "Flemish-born Christian printer. Most prominent Hebrew printer of 16th century. Published first complete Talmud.",
        "sources": ["https://en.wikipedia.org/wiki/Daniel_Bomberg"],
        "is_missing_marker": False,
        "viaf_id": "89712183",
        "wikidata_id": "Q714225",
        "cerl_id": None,
        "variants": [
            ("דפוס דניאל בומבירגי", "hebrew", "he", True, "Hebrew primary form"),
            ("בבית דניאל בומבירגי", "hebrew", "he", False, "Hebrew variant: 'at the house of'"),
            ("דניאל בומבירגי", "hebrew", "he", False, "Short Hebrew form"),
        ],
    },
    # 4. Aldine Press, Venice -- 2 entries that should map to same authority
    {
        "canonical_name": "Aldine Press, Venice",
        "type": "printing_house",
        "confidence": 0.95,
        "dates_active": "1494-1597",
        "date_start": 1494,
        "date_end": 1597,
        "location": "Venice, Italy",
        "notes": "Founded by Aldus Manutius. Revolutionized printing with italic type and portable octavo books.",
        "sources": ["https://en.wikipedia.org/wiki/Aldine_Press"],
        "is_missing_marker": False,
        "viaf_id": "139484406",
        "wikidata_id": "Q315202",
        "cerl_id": None,
        "variants": [
            ("aldus", "latin", "la", True, "Short Latin form"),
            ("in aedibus aldi et andreae", "latin", "la", False, "Joint imprint of Aldus and Andrea Torresani"),
        ],
    },
    # 5. Christophe Plantin, Antwerp -- Latin variant
    {
        "canonical_name": "Christophe Plantin, Antwerp",
        "type": "printing_house",
        "confidence": 0.99,
        "dates_active": "1555-1589",
        "date_start": 1555,
        "date_end": 1589,
        "location": "Antwerp, Belgium",
        "notes": "Christophe Plantin, largest typographical enterprise in 16th-century Europe. Famous for Biblia Polyglotta.",
        "sources": ["https://en.wikipedia.org/wiki/Christophe_Plantin"],
        "is_missing_marker": False,
        "viaf_id": "100212976",
        "wikidata_id": "Q380360",
        "cerl_id": None,
        "variants": [
            ("ex officina c. plantini", "latin", "la", True, "Latin abbreviated form"),
            ("ex officina christophori plantini", "latin", "la", False, "Full Latin form"),
        ],
    },
    # 6. Insel Verlag -- modern publisher
    {
        "canonical_name": "Insel Verlag",
        "type": "modern_publisher",
        "confidence": 0.98,
        "dates_active": "1901-present",
        "date_start": 1901,
        "date_end": None,
        "location": "Leipzig/Berlin, Germany",
        "notes": "German literary publisher. Famous for Insel-Bucherei series. Now part of Suhrkamp.",
        "sources": ["https://www.britannica.com/topic/Insel-Verlag"],
        "is_missing_marker": False,
        "viaf_id": "151223942",
        "wikidata_id": "Q458789",
        "cerl_id": None,
        "variants": [
            ("insel", "latin", "de", True, "Short normalized form"),
        ],
    },
    # 7. Grolier Club, New York -- bibliophile society
    {
        "canonical_name": "Grolier Club, New York",
        "type": "bibliophile_society",
        "confidence": 0.99,
        "dates_active": "1884-present",
        "date_start": 1884,
        "date_end": None,
        "location": "New York, USA",
        "notes": "Oldest bibliophilic club in North America. Named after Jean Grolier de Servieres.",
        "sources": ["https://en.wikipedia.org/wiki/Grolier_Club"],
        "is_missing_marker": False,
        "viaf_id": "155541720",
        "wikidata_id": "Q3775897",
        "cerl_id": None,
        "variants": [
            ("grolier club", "latin", "en", True, "Standard English form"),
        ],
    },
    # 8. Soncino Society, Berlin -- bibliophile society
    {
        "canonical_name": "Soncino Society, Berlin",
        "type": "bibliophile_society",
        "confidence": 0.99,
        "dates_active": "1924-1937",
        "date_start": 1924,
        "date_end": 1937,
        "location": "Berlin, Germany",
        "notes": "Jewish bibliophile society. Published 105 titles covering Jewish culture before dissolution.",
        "sources": ["https://www.jewishvirtuallibrary.org/soncino-gesellschaft-der-freunde-des-juedischen-buches"],
        "is_missing_marker": False,
        "viaf_id": None,
        "wikidata_id": None,
        "cerl_id": None,
        "variants": [
            ("soncino-gesellschaft", "latin", "de", True, "German society name"),
        ],
    },
    # 9. [publisher unknown] (חמו"ל) -- missing marker with Hebrew
    {
        "canonical_name": "[publisher unknown]",
        "type": "unknown_marker",
        "confidence": 0.95,
        "dates_active": None,
        "date_start": None,
        "date_end": None,
        "location": None,
        "notes": "Hebrew abbreviation for חסר מו\"ל (publisher missing). Cataloging convention, not a publisher.",
        "sources": [],
        "is_missing_marker": True,
        "viaf_id": None,
        "wikidata_id": None,
        "cerl_id": None,
        "variants": [
            ('חמו"ל', "hebrew", "he", True, "Hebrew abbreviation"),
            ('[חמו"ל]', "hebrew", "he", False, "Bracketed Hebrew form"),
        ],
    },
    # 10. [privately printed] (privatdruck) -- missing marker
    {
        "canonical_name": "[privately printed]",
        "type": "unknown_marker",
        "confidence": 0.99,
        "dates_active": None,
        "date_start": None,
        "date_end": None,
        "location": None,
        "notes": "German for private print. Not a publisher name. Indicates limited-edition not available in trade.",
        "sources": ["https://de.wikipedia.org/wiki/Privatdruck"],
        "is_missing_marker": True,
        "viaf_id": None,
        "wikidata_id": None,
        "cerl_id": None,
        "variants": [
            ("privatdruck", "latin", "de", True, "German term for private printing"),
        ],
    },
    # 11. Francke Orphanage Press, Halle -- 3 Latin variants mapping to same entity
    {
        "canonical_name": "Francke Orphanage Press, Halle",
        "type": "printing_house",
        "confidence": 0.97,
        "dates_active": "1698-1800s",
        "date_start": 1698,
        "date_end": 1800,
        "location": "Halle, Germany",
        "notes": "Press of the Franckesche Stiftungen (Francke Foundations). Major Pietist publisher.",
        "sources": ["https://www.britannica.com/topic/Franckesche-Stiftungen"],
        "is_missing_marker": False,
        "viaf_id": None,
        "wikidata_id": "Q699504",
        "cerl_id": None,
        "variants": [
            ("impensis orphanotrophei", "latin", "la", True, "Latin: at the expense of the orphanage"),
            ("typis et impensis orphanotrophei", "latin", "la", False, "Fuller Latin form"),
            ("typis & sumptibus orphanotrophei", "latin", "la", False, "Variant Latin form"),
        ],
    },
    # 12. Robert Estienne, Paris -- Hebrew transliteration variant
    {
        "canonical_name": "Robert Estienne, Paris",
        "type": "printing_house",
        "confidence": 0.98,
        "dates_active": "1526-1559",
        "date_start": 1526,
        "date_end": 1559,
        "location": "Paris, France",
        "notes": "Robert I Estienne, Printer to the King for Latin, Hebrew, and Greek. Published complete Hebrew Bible.",
        "sources": ["https://en.wikipedia.org/wiki/Robert_Estienne"],
        "is_missing_marker": False,
        "viaf_id": "100183112",
        "wikidata_id": "Q315602",
        "cerl_id": None,
        "variants": [
            ("רוברטוס סטפניוס", "hebrew", "he", True, "Hebrew transliteration of Latin name"),
            ("רוברטוס סטפניוס ובביתו", "hebrew", "he", False, "Hebrew: 'Robertus Stephanus and his house'"),
        ],
    },
    # 13. Sebastian Gryphius, Lyon -- Latin variant
    {
        "canonical_name": "Sebastian Gryphius, Lyon",
        "type": "printing_house",
        "confidence": 0.99,
        "dates_active": "1523-1556",
        "date_start": 1523,
        "date_end": 1556,
        "location": "Lyon, France",
        "notes": "Sebastian Gryphius (1493-1556), leading printer in Lyon. Published estimated half of European academic textbooks.",
        "sources": ["https://en.wikipedia.org/wiki/Sebastian_Gryphius"],
        "is_missing_marker": False,
        "viaf_id": "12303938",
        "wikidata_id": "Q1406376",
        "cerl_id": None,
        "variants": [
            ("apud s. gryphium", "latin", "la", True, "Latin imprint form"),
            ("s. gryphius excudebat", "latin", "la", False, "Latin: S. Gryphius printed [this]"),
        ],
    },
    # 14. Verdiere, Paris -- simple case, high frequency
    {
        "canonical_name": "Verdiere, Paris",
        "type": "printing_house",
        "confidence": 0.9,
        "dates_active": "1812-1875",
        "date_start": 1812,
        "date_end": 1875,
        "location": "Paris, France",
        "notes": "Charles-Hippolyte Verdiere, Parisian bookseller-publisher at 25 Quai des Augustins.",
        "sources": ["https://data.bnf.fr/15507780/charles-hippolyte_verdiere/"],
        "is_missing_marker": False,
        "viaf_id": None,
        "wikidata_id": None,
        "cerl_id": None,
        "variants": [
            ("verdiere", "latin", "fr", True, "Normalized French form"),
        ],
    },
]


def run_tests():
    """Run all tests against the real database and produce a report."""
    print(f"Database: {DB_PATH}")
    print(f"Database exists: {DB_PATH.exists()}")

    store = PublisherAuthorityStore(DB_PATH)

    # Step 0: Clean up any previous test run (drop and recreate)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Drop existing tables if present (clean slate for test)
    conn.execute("DROP TABLE IF EXISTS publisher_variants")
    conn.execute("DROP TABLE IF EXISTS publisher_authorities")
    conn.commit()

    # Step 1: Initialize schema
    print("\n--- Step 1: Initialize schema ---")
    store.init_schema(conn)

    # Verify tables created
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'publisher%' ORDER BY name"
    ).fetchall()
    table_names = [r["name"] for r in tables]
    print(f"Tables created: {table_names}")
    assert "publisher_authorities" in table_names, "publisher_authorities table not created"
    assert "publisher_variants" in table_names, "publisher_variants table not created"

    # Step 2-5: Create records, test roundtrips, link imprints
    results = []
    total_variants = 0
    total_imprints_linked = 0
    all_roundtrips_passed = True
    schema_issues = []
    suggested_refinements = []

    for i, pub_def in enumerate(PUBLISHERS_TO_TEST, 1):
        print(f"\n--- Publisher {i}/{len(PUBLISHERS_TO_TEST)}: {pub_def['canonical_name']} ---")
        issues = []

        # 2a. Create PublisherAuthority with variants
        variants = []
        for v_form, v_script, v_lang, v_primary, v_notes in pub_def["variants"]:
            # Test detect_script
            detected = detect_script(v_form)
            expected_script = v_script
            if detected != expected_script:
                issue = f"detect_script('{v_form}') returned '{detected}', expected '{expected_script}'"
                issues.append(issue)
                print(f"  ISSUE: {issue}")

            variants.append(PublisherVariant(
                variant_form=v_form,
                script=v_script,
                language=v_lang,
                is_primary=v_primary,
                notes=v_notes,
            ))

        authority = PublisherAuthority(
            canonical_name=pub_def["canonical_name"],
            type=pub_def["type"],
            confidence=pub_def["confidence"],
            dates_active=pub_def["dates_active"],
            date_start=pub_def["date_start"],
            date_end=pub_def["date_end"],
            location=pub_def["location"],
            notes=pub_def["notes"],
            sources=pub_def["sources"],
            is_missing_marker=pub_def["is_missing_marker"],
            viaf_id=pub_def["viaf_id"],
            wikidata_id=pub_def["wikidata_id"],
            cerl_id=pub_def["cerl_id"],
            variants=variants,
        )

        # 2b. Insert
        try:
            auth_id = store.create(authority, conn=conn)
            print(f"  Created authority id={auth_id}")
        except sqlite3.IntegrityError as e:
            issue = f"IntegrityError on create: {e}"
            issues.append(issue)
            print(f"  ERROR: {issue}")
            results.append({
                "canonical_name": pub_def["canonical_name"],
                "authority_id": None,
                "variants_added": 0,
                "imprints_linked": 0,
                "roundtrip_ok": False,
                "variant_search_ok": False,
                "issues": issues,
            })
            all_roundtrips_passed = False
            continue

        # 2c. Link to imprints
        imprints_linked = store.link_to_imprints(auth_id, conn=conn)
        print(f"  Imprints linked: {imprints_linked}")

        # 2d. Get by ID and verify roundtrip
        retrieved = store.get_by_id(auth_id, conn=conn)
        roundtrip_ok = True

        if retrieved is None:
            issue = "get_by_id returned None"
            issues.append(issue)
            roundtrip_ok = False
        else:
            # Verify key fields
            checks = [
                ("canonical_name", retrieved.canonical_name, pub_def["canonical_name"]),
                ("type", retrieved.type, pub_def["type"]),
                ("confidence", retrieved.confidence, pub_def["confidence"]),
                ("dates_active", retrieved.dates_active, pub_def["dates_active"]),
                ("date_start", retrieved.date_start, pub_def["date_start"]),
                ("date_end", retrieved.date_end, pub_def["date_end"]),
                ("location", retrieved.location, pub_def["location"]),
                ("is_missing_marker", retrieved.is_missing_marker, pub_def["is_missing_marker"]),
                ("viaf_id", retrieved.viaf_id, pub_def["viaf_id"]),
                ("wikidata_id", retrieved.wikidata_id, pub_def["wikidata_id"]),
                ("cerl_id", retrieved.cerl_id, pub_def["cerl_id"]),
                ("variant_count", len(retrieved.variants), len(pub_def["variants"])),
            ]
            for field_name, actual, expected in checks:
                if actual != expected:
                    issue = f"Roundtrip mismatch on '{field_name}': got {actual!r}, expected {expected!r}"
                    issues.append(issue)
                    roundtrip_ok = False
                    print(f"  MISMATCH: {issue}")

            # Check sources deserialization
            if retrieved.sources != pub_def["sources"]:
                issue = f"Sources roundtrip mismatch: got {retrieved.sources!r}, expected {pub_def['sources']!r}"
                issues.append(issue)
                roundtrip_ok = False

            # Verify variants were stored correctly
            for orig_v in pub_def["variants"]:
                v_form, v_script, v_lang, v_primary, v_notes = orig_v
                found = False
                for rv in retrieved.variants:
                    if rv.variant_form == v_form:
                        found = True
                        if rv.script != v_script:
                            issue = f"Variant '{v_form}' script mismatch: got {rv.script!r}, expected {v_script!r}"
                            issues.append(issue)
                            roundtrip_ok = False
                        if rv.is_primary != v_primary:
                            issue = f"Variant '{v_form}' is_primary mismatch: got {rv.is_primary!r}, expected {v_primary!r}"
                            issues.append(issue)
                            roundtrip_ok = False
                        break
                if not found:
                    issue = f"Variant '{v_form}' not found in retrieved record"
                    issues.append(issue)
                    roundtrip_ok = False

        if roundtrip_ok:
            print("  Roundtrip: OK")
        else:
            all_roundtrips_passed = False

        # 2e. Search by variant for each variant
        variant_search_ok = True
        for v_form, v_script, v_lang, v_primary, v_notes in pub_def["variants"]:
            found_auth = store.search_by_variant(v_form, conn=conn)
            if found_auth is None:
                issue = f"search_by_variant('{v_form}') returned None"
                issues.append(issue)
                variant_search_ok = False
                print(f"  VARIANT SEARCH FAIL: {issue}")
            elif found_auth.id != auth_id:
                issue = f"search_by_variant('{v_form}') returned wrong authority id={found_auth.id}, expected {auth_id}"
                issues.append(issue)
                variant_search_ok = False
                print(f"  VARIANT SEARCH FAIL: {issue}")
            else:
                print(f"  Variant search '{v_form}': OK")

        # Also test search by canonical name
        by_name = store.get_by_canonical_name(pub_def["canonical_name"], conn=conn)
        if by_name is None:
            issue = f"get_by_canonical_name('{pub_def['canonical_name']}') returned None"
            issues.append(issue)
            print(f"  CANONICAL NAME SEARCH FAIL: {issue}")
        elif by_name.id != auth_id:
            issue = f"get_by_canonical_name returned wrong id={by_name.id}, expected {auth_id}"
            issues.append(issue)

        # Also get linked imprints details for the report
        linked_imprints_detail = store.get_linked_imprints(auth_id, conn=conn)

        n_variants = len(pub_def["variants"])
        total_variants += n_variants
        total_imprints_linked += imprints_linked

        results.append({
            "canonical_name": pub_def["canonical_name"],
            "authority_id": auth_id,
            "variants_added": n_variants,
            "imprints_linked": imprints_linked,
            "roundtrip_ok": roundtrip_ok,
            "variant_search_ok": variant_search_ok,
            "issues": issues,
            "linked_imprint_sample": linked_imprints_detail[:3] if linked_imprints_detail else [],
        })

    # Step 6: Additional schema tests

    # Test list_all
    print("\n--- Additional tests ---")
    all_authorities = store.list_all(conn=conn)
    print(f"list_all() returned {len(all_authorities)} records (expected {len(PUBLISHERS_TO_TEST)})")
    if len(all_authorities) != len(PUBLISHERS_TO_TEST):
        schema_issues.append(f"list_all returned {len(all_authorities)}, expected {len(PUBLISHERS_TO_TEST)}")

    # Test list_all with type_filter
    printing_houses = store.list_all(type_filter="printing_house", conn=conn)
    expected_ph = sum(1 for p in PUBLISHERS_TO_TEST if p["type"] == "printing_house")
    print(f"list_all(type='printing_house') returned {len(printing_houses)} (expected {expected_ph})")
    if len(printing_houses) != expected_ph:
        schema_issues.append(f"list_all(type_filter='printing_house') returned {len(printing_houses)}, expected {expected_ph}")

    bibliophile = store.list_all(type_filter="bibliophile_society", conn=conn)
    expected_bs = sum(1 for p in PUBLISHERS_TO_TEST if p["type"] == "bibliophile_society")
    print(f"list_all(type='bibliophile_society') returned {len(bibliophile)} (expected {expected_bs})")

    unknown_markers = store.list_all(type_filter="unknown_marker", conn=conn)
    expected_um = sum(1 for p in PUBLISHERS_TO_TEST if p["type"] == "unknown_marker")
    print(f"list_all(type='unknown_marker') returned {len(unknown_markers)} (expected {expected_um})")

    # Test case-insensitive variant search
    elzevir = store.search_by_variant("EX OFFICINA ELZEVIRIANA", conn=conn)
    if elzevir and elzevir.canonical_name == "House of Elzevir":
        print("Case-insensitive variant search: OK")
    else:
        schema_issues.append("Case-insensitive variant search failed for 'EX OFFICINA ELZEVIRIANA'")

    # Test duplicate variant detection (should fail with IntegrityError)
    try:
        dup_variant = PublisherVariant(variant_form="verdiere", script="latin", language="fr", is_primary=False)
        store.add_variant(results[-1]["authority_id"], dup_variant, conn=conn)
        schema_issues.append("Duplicate variant 'verdiere' was accepted (should have raised IntegrityError)")
        print("Duplicate variant test: FAIL (no error raised)")
    except sqlite3.IntegrityError:
        print("Duplicate variant rejection: OK (IntegrityError raised as expected)")

    # Test update
    verdiere = store.get_by_canonical_name("Verdiere, Paris", conn=conn)
    if verdiere:
        verdiere.confidence = 0.95
        verdiere.notes = "Updated: Charles-Hippolyte Verdiere, Parisian bookseller-publisher."
        store.update(verdiere, conn=conn)
        verdiere_updated = store.get_by_id(verdiere.id, conn=conn)
        if verdiere_updated and verdiere_updated.confidence == 0.95:
            print("Update test: OK")
        else:
            schema_issues.append("Update did not persist confidence change")

    # Check for potential schema refinements
    # 1. No way to track which branch of Elzevir (Leiden vs Amsterdam)
    suggested_refinements.append(
        "Consider adding a 'branch' or 'sub_entity' field for printing dynasties "
        "with multiple branches (e.g., Elzevir Leiden vs Amsterdam)"
    )

    # 2. No way to link Aldine Press entries that appeared as separate normalized forms
    suggested_refinements.append(
        "The schema correctly handles multiple normalized forms mapping to one authority "
        "(e.g., 'aldus' and 'in aedibus aldi et andreae' both map to Aldine Press). "
        "Consider adding a priority/rank to variants for display purposes."
    )

    # 3. No language field on authority itself
    suggested_refinements.append(
        "Consider adding a 'primary_language' field to publisher_authorities "
        "for publishers whose output was predominantly in one language."
    )

    # 4. The imprint linking is read-only (no FK column in imprints)
    suggested_refinements.append(
        "link_to_imprints() is read-only. For production, consider adding "
        "'authority_id' column to imprints table for persistent linking."
    )

    # 5. Check if Hebrew characters in variant_form_lower are handled correctly
    hebrew_variants_check = conn.execute(
        "SELECT variant_form, variant_form_lower FROM publisher_variants WHERE script='hebrew'"
    ).fetchall()
    for row in hebrew_variants_check:
        if row["variant_form"].lower() != row["variant_form_lower"]:
            schema_issues.append(
                f"Hebrew lowercasing issue: variant_form='{row['variant_form']}' "
                f"lowered to '{row['variant_form_lower']}' but Python .lower() "
                f"gives '{row['variant_form'].lower()}'"
            )

    conn.close()

    # Build report
    report = {
        "test_date": datetime.now(timezone.utc).isoformat(),
        "database_path": str(DB_PATH),
        "publishers_tested": len(PUBLISHERS_TO_TEST),
        "results": results,
        "schema_issues": schema_issues,
        "suggested_refinements": suggested_refinements,
        "summary": {
            "total_authorities_created": len([r for r in results if r["authority_id"] is not None]),
            "total_variants_added": total_variants,
            "total_imprints_linked": total_imprints_linked,
            "all_roundtrips_passed": all_roundtrips_passed,
            "all_variant_searches_passed": all(r["variant_search_ok"] for r in results),
            "type_distribution": {
                "printing_house": sum(1 for p in PUBLISHERS_TO_TEST if p["type"] == "printing_house"),
                "modern_publisher": sum(1 for p in PUBLISHERS_TO_TEST if p["type"] == "modern_publisher"),
                "bibliophile_society": sum(1 for p in PUBLISHERS_TO_TEST if p["type"] == "bibliophile_society"),
                "unknown_marker": sum(1 for p in PUBLISHERS_TO_TEST if p["type"] == "unknown_marker"),
            },
        },
    }

    # Write report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport written to: {REPORT_PATH}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Publishers tested: {len(PUBLISHERS_TO_TEST)}")
    print(f"Authorities created: {report['summary']['total_authorities_created']}")
    print(f"Total variants: {total_variants}")
    print(f"Total imprints linked: {total_imprints_linked}")
    print(f"All roundtrips passed: {all_roundtrips_passed}")
    print(f"All variant searches passed: {report['summary']['all_variant_searches_passed']}")
    print(f"Schema issues: {len(schema_issues)}")
    print(f"Suggested refinements: {len(suggested_refinements)}")

    if schema_issues:
        print("\nSchema issues:")
        for si in schema_issues:
            print(f"  - {si}")

    # Print issues per publisher
    any_issues = False
    for r in results:
        if r["issues"]:
            any_issues = True
            print(f"\n  Issues for {r['canonical_name']}:")
            for iss in r["issues"]:
                print(f"    - {iss}")

    if not any_issues:
        print("\nNo issues found in any publisher record.")

    return report


if __name__ == "__main__":
    report = run_tests()

    # Output JSON summary for caller
    output = {
        "publishers_tested": report["summary"]["total_authorities_created"],
        "total_variants": report["summary"]["total_variants_added"],
        "total_imprints_linked": report["summary"]["total_imprints_linked"],
        "issues_found": len(report["schema_issues"]) + sum(len(r["issues"]) for r in report["results"]),
        "report_path": str(REPORT_PATH),
    }
    print("\n--- JSON OUTPUT ---")
    print(json.dumps(output, indent=2))
