"""Tests for chat aggregation module.

Tests the is_overview_query() function that distinguishes between
general collection overview requests and specific search queries.
"""

import pytest

from scripts.chat.aggregation import is_overview_query


class TestIsOverviewQuery:
    """Tests for is_overview_query function."""

    # ==================== True Positives (Should return True) ====================

    def test_exact_greeting_hi(self):
        """Simple greeting 'hi' should be treated as overview request."""
        assert is_overview_query("hi") is True

    def test_exact_greeting_hello(self):
        """Simple greeting 'hello' should be treated as overview request."""
        assert is_overview_query("hello") is True

    def test_exact_help(self):
        """'help' should be treated as overview request."""
        assert is_overview_query("help") is True

    def test_exact_question_mark(self):
        """Single '?' should be treated as overview request."""
        assert is_overview_query("?") is True

    def test_exact_what_do_you_have(self):
        """'what do you have' should be overview request."""
        assert is_overview_query("what do you have") is True

    def test_tell_me_about_collection(self):
        """'tell me about the collection' is overview request."""
        assert is_overview_query("tell me about the collection") is True

    def test_what_can_you_tell_me_about_collection(self):
        """Generic collection question should be overview."""
        assert is_overview_query("what can you tell me about the collection") is True

    def test_overview_keyword(self):
        """Query with 'overview' keyword should be overview request."""
        assert is_overview_query("give me an overview") is True

    def test_short_tell_me_about(self):
        """Short 'tell me about this' should be overview (< 40 chars)."""
        assert is_overview_query("tell me about this") is True

    def test_describe_the_collection(self):
        """'describe the collection' should be overview."""
        assert is_overview_query("describe the collection") is True

    def test_what_types_of_books(self):
        """'what types of books do you have' should be overview."""
        assert is_overview_query("what types of books in the collection") is True

    def test_case_insensitive(self):
        """Should be case insensitive."""
        assert is_overview_query("HELLO") is True
        assert is_overview_query("What Do You Have") is True

    def test_whitespace_handling(self):
        """Should handle leading/trailing whitespace."""
        assert is_overview_query("  hi  ") is True
        assert is_overview_query("\nhello\n") is True

    # ==================== True Negatives (Should return False) ====================

    def test_hebrew_books_not_overview(self):
        """Query about Hebrew books is specific, not overview."""
        assert is_overview_query("tell me about Hebrew books") is False

    def test_latin_books_not_overview(self):
        """Query about Latin books is specific, not overview."""
        assert is_overview_query("what Latin books do you have") is False

    def test_venice_books_not_overview(self):
        """Query about Venice is specific, not overview."""
        assert is_overview_query("books from Venice") is False

    def test_16th_century_not_overview(self):
        """Query about 16th century is specific, not overview."""
        assert is_overview_query("tell me about 16th century books") is False

    def test_astronomy_not_overview(self):
        """Query about astronomy is specific, not overview."""
        assert is_overview_query("what books about astronomy") is False

    def test_printer_query_not_overview(self):
        """Query about printers is specific, not overview."""
        assert is_overview_query("what was printed by Aldus") is False

    def test_how_many_not_overview(self):
        """'how many' queries are specific searches."""
        assert is_overview_query("how many books do you have") is False

    def test_where_were_not_overview(self):
        """'where were' queries are specific searches."""
        assert is_overview_query("where were these books published") is False

    def test_specific_language_french(self):
        """French language query is specific."""
        assert is_overview_query("French books in the collection") is False

    def test_specific_place_paris(self):
        """Paris place query is specific."""
        assert is_overview_query("books published in Paris") is False

    def test_specific_subject_theology(self):
        """Theology subject query is specific."""
        assert is_overview_query("theology books") is False

    def test_mixed_overview_with_criteria(self):
        """Overview phrase with specific criteria is NOT overview."""
        assert is_overview_query("tell me about the Hebrew collection") is False

    def test_century_keyword(self):
        """'century' keyword makes it specific."""
        assert is_overview_query("books from the 15th century") is False

    def test_year_number(self):
        """Specific year number makes it specific."""
        assert is_overview_query("books from 1500") is False

    # ==================== Edge Cases ====================

    def test_empty_string(self):
        """Empty string should not be overview."""
        assert is_overview_query("") is False

    def test_whitespace_only(self):
        """Whitespace only should not be overview."""
        assert is_overview_query("   ") is False

    def test_long_generic_query_without_collection_ref(self):
        """Long generic query without collection reference is NOT overview."""
        # This is > 40 chars and has no collection reference
        long_query = "what can you tell me about the items available in this repository"
        # Contains "available" but not a collection indicator, and > 40 chars
        # Actually "available here" is a collection indicator, let me check...
        # "available here" is in collection_indicators but "available" alone is not
        assert is_overview_query(long_query) is False

    def test_start_keyword(self):
        """'start' should be treated as overview."""
        assert is_overview_query("start") is True

    def test_introduction_keyword(self):
        """'introduction' should be overview if short enough."""
        assert is_overview_query("introduction") is True

    def test_general_information(self):
        """'general information' should be overview."""
        assert is_overview_query("general information") is True
