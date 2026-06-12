"""Regression guard for the fix_19 Hebrew translation dictionaries.

The original authoring pass mangled 37 dictionary values (each a 2-byte
Hebrew letter -> 2×U+FFFD), which leaked into 117 subjects.value_he rows.
Lock the dictionaries clean.
"""
from scripts.qa.fixes.fix_19_add_hebrew_subjects import (
    BASE_TRANSLATIONS,
    SUBDIVISION_TRANSLATIONS,
    translate_subject,
)


def test_no_replacement_chars_in_dictionaries():
    for d in (BASE_TRANSLATIONS, SUBDIVISION_TRANSLATIONS):
        for k, v in d.items():
            assert "�" not in v, f"mojibake in translation for {k!r}: {v!r}"


def test_previously_corrupted_terms_translate_cleanly():
    assert translate_subject("Limited editions") == "מהדורות מצומצמות"
    assert translate_subject("Authorship") == "כתיבה חיבור"
    assert "ומסעות" in (translate_subject("Atlantic States -- Description and travel.") or "")
