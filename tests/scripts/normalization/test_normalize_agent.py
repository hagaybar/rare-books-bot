"""Tests for agent and role normalization (Stage 3)."""

import pytest
from scripts.normalization.normalize_agent import (
    normalize_agent_base,
    normalize_role_base,
    normalize_agent_with_alias_map
)


class TestNormalizeAgentBase:
    """Test base agent name normalization."""

    def test_simple_name(self):
        """Test normalization of simple name."""
        result = normalize_agent_base("Smith, John")
        assert result == "smith, john"

    def test_name_with_dates(self):
        """Test that dates are preserved in normalized form."""
        result = normalize_agent_base("Manutius, Aldus, 1450?-1515")
        assert result == "manutius, aldus, 1450?-1515"

    def test_bracketed_name(self):
        """Test removal of brackets."""
        result = normalize_agent_base("[Oxford University Press]")
        assert result == "oxford university press"

    def test_trailing_punctuation(self):
        """Test removal of trailing punctuation."""
        result = normalize_agent_base("Elsevier,")
        assert result == "elsevier"

    def test_trailing_period(self):
        """Test removal of trailing period."""
        result = normalize_agent_base("Smith, J.")
        assert result == "smith, j"

    def test_multiple_trailing_punct(self):
        """Test removal of multiple trailing punctuation."""
        result = normalize_agent_base("Cambridge University Press.,")
        assert result == "cambridge university press"

    def test_whitespace_collapse(self):
        """Test collapsing of internal whitespace."""
        result = normalize_agent_base("Smith,  John   Jr.")
        assert result == "smith, john jr"

    def test_leading_trailing_whitespace(self):
        """Test trimming of leading/trailing whitespace."""
        result = normalize_agent_base("  Brown, Alice  ")
        assert result == "brown, alice"

    def test_unicode_normalization(self):
        """Test unicode normalization (NFKC)."""
        # Input with composed unicode
        result = normalize_agent_base("Müller, Hans")
        assert "muller" in result.lower() or "müller" in result

    def test_empty_string(self):
        """Test handling of empty string."""
        result = normalize_agent_base("")
        assert result == ""

    def test_only_brackets(self):
        """Test handling of string with only brackets."""
        result = normalize_agent_base("[]")
        assert result == ""

    def test_only_whitespace(self):
        """Test handling of string with only whitespace."""
        result = normalize_agent_base("   ")
        assert result == ""

    def test_preserves_internal_commas(self):
        """Test that internal commas are preserved."""
        result = normalize_agent_base("Smith, John, Jr.")
        assert result == "smith, john, jr"

    def test_case_insensitive(self):
        """Test that normalization is case-insensitive."""
        result1 = normalize_agent_base("SMITH, JOHN")
        result2 = normalize_agent_base("Smith, John")
        result3 = normalize_agent_base("smith, john")
        assert result1 == result2 == result3 == "smith, john"

    def test_deterministic(self):
        """Test that normalization is deterministic."""
        input_str = "Manutius, Aldus, 1450?-1515"
        result1 = normalize_agent_base(input_str)
        result2 = normalize_agent_base(input_str)
        assert result1 == result2


class TestNormalizeRoleBase:
    """Test role normalization with mapping table."""

    def test_relator_code_author(self):
        """Test mapping of 'aut' relator code."""
        role_norm, confidence, method = normalize_role_base("aut")
        assert role_norm == "author"
        assert confidence == 0.99
        assert method == "relator_code"

    def test_relator_code_printer(self):
        """Test mapping of 'prt' relator code."""
        role_norm, confidence, method = normalize_role_base("prt")
        assert role_norm == "printer"
        assert confidence == 0.99
        assert method == "relator_code"

    def test_relator_code_publisher(self):
        """Test mapping of 'pbl' relator code."""
        role_norm, confidence, method = normalize_role_base("pbl")
        assert role_norm == "publisher"
        assert confidence == 0.99
        assert method == "relator_code"

    def test_relator_code_translator(self):
        """Test mapping of 'trl' relator code."""
        role_norm, confidence, method = normalize_role_base("trl")
        assert role_norm == "translator"
        assert confidence == 0.99
        assert method == "relator_code"

    def test_relator_code_editor(self):
        """Test mapping of 'edt' relator code."""
        role_norm, confidence, method = normalize_role_base("edt")
        assert role_norm == "editor"
        assert confidence == 0.99
        assert method == "relator_code"

    def test_relator_code_artist(self):
        """Test mapping of 'art' relator code."""
        role_norm, confidence, method = normalize_role_base("art")
        assert role_norm == "artist"
        assert confidence == 0.99
        assert method == "relator_code"

    def test_relator_term_printer_full(self):
        """Test mapping of full 'printer' term."""
        role_norm, confidence, method = normalize_role_base("printer")
        assert role_norm == "printer"
        assert confidence == 0.95
        assert method == "relator_term"

    def test_relator_term_publisher_full(self):
        """Test mapping of full 'publisher' term."""
        role_norm, confidence, method = normalize_role_base("publisher")
        assert role_norm == "publisher"
        assert confidence == 0.95
        assert method == "relator_term"

    def test_relator_term_abbreviation_impr(self):
        """Test mapping of 'impr.' abbreviation."""
        role_norm, confidence, method = normalize_role_base("impr.")
        assert role_norm == "printer"
        assert confidence == 0.95
        assert method == "relator_term"

    def test_relator_term_abbreviation_pub(self):
        """Test mapping of 'pub.' abbreviation."""
        role_norm, confidence, method = normalize_role_base("pub.")
        assert role_norm == "publisher"
        assert confidence == 0.95
        assert method == "relator_term"

    def test_relator_term_abbreviation_ed(self):
        """Test mapping of 'ed.' abbreviation."""
        role_norm, confidence, method = normalize_role_base("ed.")
        assert role_norm == "editor"
        assert confidence == 0.95
        assert method == "relator_term"

    def test_relator_term_abbreviation_trans(self):
        """Test mapping of 'trans.' abbreviation."""
        role_norm, confidence, method = normalize_role_base("trans.")
        assert role_norm == "translator"
        assert confidence == 0.95
        assert method == "relator_term"

    def test_relator_term_artist(self):
        """Test mapping of 'artist' term."""
        role_norm, confidence, method = normalize_role_base("artist")
        assert role_norm == "artist"
        assert confidence == 0.95
        assert method == "relator_term"

    def test_inferred_author(self):
        """Test mapping of inferred 'author' role."""
        role_norm, confidence, method = normalize_role_base("author")
        assert role_norm == "author"
        assert confidence == 0.95  # relator_term, not inferred
        assert method == "relator_term"

    def test_inferred_creator(self):
        """Test mapping of inferred 'creator' role."""
        role_norm, confidence, method = normalize_role_base("creator")
        assert role_norm == "creator"
        assert confidence == 0.95  # relator_term
        assert method == "relator_term"

    def test_missing_role(self):
        """Test handling of None/missing role."""
        role_norm, confidence, method = normalize_role_base(None)
        assert role_norm == "other"
        assert confidence == 0.5
        assert method == "missing_role"

    def test_empty_role(self):
        """Test handling of empty string role."""
        role_norm, confidence, method = normalize_role_base("")
        assert role_norm == "other"
        assert confidence == 0.5
        assert method == "missing_role"

    def test_unknown_role(self):
        """Test handling of unmapped role."""
        role_norm, confidence, method = normalize_role_base("unknown_role_xyz")
        assert role_norm == "other"
        assert confidence == 0.6
        assert method == "unmapped"

    def test_case_insensitive_code(self):
        """Test that relator codes are case-insensitive."""
        role_norm1, _, _ = normalize_role_base("prt")
        role_norm2, _, _ = normalize_role_base("PRT")
        role_norm3, _, _ = normalize_role_base("Prt")
        assert role_norm1 == role_norm2 == role_norm3 == "printer"

    def test_case_insensitive_term(self):
        """Test that relator terms are case-insensitive."""
        role_norm1, _, _ = normalize_role_base("Printer")
        role_norm2, _, _ = normalize_role_base("PRINTER")
        role_norm3, _, _ = normalize_role_base("printer")
        assert role_norm1 == role_norm2 == role_norm3 == "printer"

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        role_norm, confidence, method = normalize_role_base("  printer  ")
        assert role_norm == "printer"
        assert confidence == 0.95
        assert method == "relator_term"

    def test_all_relator_codes(self):
        """Test all defined relator codes."""
        codes = {
            'aut': 'author',
            'prt': 'printer',
            'pbl': 'publisher',
            'trl': 'translator',
            'edt': 'editor',
            'ill': 'illustrator',
            'com': 'compiler',      # MARC code 'com' = compiler, not commentator
            'cmm': 'commentator',   # MARC code 'cmm' = commentator
            'scr': 'scribe',
            'fmo': 'former_owner',
            'dte': 'dedicatee',
            'bsl': 'bookseller',
            'ctg': 'cartographer',
            'eng': 'engraver',
            'bnd': 'binder',
            'ann': 'annotator',
            'cre': 'creator',
            'asn': 'associated_name',
            'art': 'artist',
            'oth': 'other',
        }
        for code, expected_role in codes.items():
            role_norm, confidence, method = normalize_role_base(code)
            assert role_norm == expected_role, f"Code {code} mapped incorrectly"
            assert confidence == 0.99
            assert method == "relator_code"


class TestNormalizeAgentWithAliasMap:
    """Test agent normalization with alias map."""

    def test_without_alias_map(self):
        """Test normalization without alias map (base normalization only)."""
        agent_norm, confidence, method, notes = normalize_agent_with_alias_map(
            "Manutius, Aldus, 1450?-1515"
        )
        assert agent_norm == "manutius, aldus, 1450?-1515"
        assert confidence == 0.80
        assert method == "base_clean"
        assert notes is None

    def test_with_alias_map_keep(self):
        """Test with alias map entry marked KEEP."""
        alias_map = {
            "aldus manutius": {
                "decision": "KEEP",
                "canonical": "aldus manutius",
                "confidence": 1.0,
                "notes": "Already canonical"
            }
        }
        agent_norm, confidence, method, notes = normalize_agent_with_alias_map(
            "Aldus Manutius",
            alias_map
        )
        # KEEP decision should fall through to base normalization
        assert agent_norm == "aldus manutius"
        assert confidence == 0.80
        assert method == "base_clean"

    def test_with_alias_map_mapping(self):
        """Test with alias map entry marked MAP."""
        alias_map = {
            "manutius, aldus, 1450?-1515": {
                "decision": "MAP",
                "canonical": "aldus manutius",
                "confidence": 0.95,
                "notes": "Standard form, dates removed"
            }
        }
        agent_norm, confidence, method, notes = normalize_agent_with_alias_map(
            "Manutius, Aldus, 1450?-1515",
            alias_map
        )
        assert agent_norm == "aldus manutius"
        assert confidence == 0.95
        assert method == "alias_map"
        assert notes == "Standard form, dates removed"

    def test_with_alias_map_ambiguous(self):
        """Test with alias map entry marked AMBIGUOUS."""
        alias_map = {
            "smith, john": {
                "decision": "AMBIGUOUS",
                "canonical": "ambiguous",
                "confidence": 0.5,
                "notes": "Multiple John Smiths, cannot disambiguate"
            }
        }
        agent_norm, confidence, method, notes = normalize_agent_with_alias_map(
            "Smith, John",
            alias_map
        )
        assert agent_norm == "ambiguous"
        assert confidence == 0.5
        assert method == "ambiguous"
        assert "cannot disambiguate" in notes.lower()

    def test_not_in_alias_map(self):
        """Test agent not in alias map falls back to base normalization."""
        alias_map = {
            "aldus manutius": {
                "decision": "KEEP",
                "canonical": "aldus manutius",
                "confidence": 1.0
            }
        }
        agent_norm, confidence, method, notes = normalize_agent_with_alias_map(
            "Different, Author",
            alias_map
        )
        assert agent_norm == "different, author"
        assert confidence == 0.80
        assert method == "base_clean"
        assert notes is None

    def test_empty_after_cleaning(self):
        """Test handling of agent name that becomes empty after cleaning."""
        agent_norm, confidence, method, notes = normalize_agent_with_alias_map("")
        assert agent_norm == ""
        assert confidence == 0.0
        assert method == "empty_after_cleaning"
        assert "empty" in notes.lower()

    def test_alias_map_case_insensitive_lookup(self):
        """Test that alias map lookup is case-insensitive (via base normalization)."""
        alias_map = {
            "aldus manutius": {
                "decision": "MAP",
                "canonical": "aldus manutius",
                "confidence": 0.95
            }
        }
        # Different cases should all normalize to same key for lookup
        for variant in ["Aldus Manutius", "ALDUS MANUTIUS", "aldus manutius"]:
            agent_norm, confidence, method, _ = normalize_agent_with_alias_map(
                variant,
                alias_map
            )
            assert agent_norm == "aldus manutius"
            assert method == "alias_map"


class TestDeterminism:
    """Test that all normalization is deterministic."""

    def test_agent_base_deterministic(self):
        """Test that agent base normalization is deterministic."""
        input_str = "Manutius, Aldus, 1450?-1515"
        results = [normalize_agent_base(input_str) for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_role_base_deterministic(self):
        """Test that role base normalization is deterministic."""
        input_str = "prt"
        results = [normalize_role_base(input_str) for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_agent_with_alias_map_deterministic(self):
        """Test that agent normalization with alias map is deterministic."""
        alias_map = {
            "manutius, aldus, 1450?-1515": {
                "decision": "MAP",
                "canonical": "aldus manutius",
                "confidence": 0.95
            }
        }
        input_str = "Manutius, Aldus, 1450?-1515"
        results = [
            normalize_agent_with_alias_map(input_str, alias_map)
            for _ in range(10)
        ]
        assert all(r == results[0] for r in results)
