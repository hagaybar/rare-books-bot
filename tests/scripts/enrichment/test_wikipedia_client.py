"""Tests for Wikipedia API client. All HTTP calls mocked via _api_get."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from scripts.enrichment.wikipedia_client import (
    WikipediaLinks,
    WikipediaSummary,
    fetch_links_batch,
    fetch_summary,
    resolve_titles_batch,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_wikidata_response():
    """Mock wbgetentities response for title resolution."""
    return {
        "entities": {
            "Q193460": {
                "sitelinks": {"enwiki": {"title": "Joseph Karo"}},
            },
            "Q440285": {
                "sitelinks": {"enwiki": {"title": "Moses Isserles"}},
            },
        }
    }


@pytest.fixture
def mock_links_response():
    """Mock MediaWiki prop=links|categories response."""
    return {
        "query": {
            "pages": {
                "12345": {
                    "title": "Joseph Karo",
                    "links": [
                        {"title": "Moses Isserles"},
                        {"title": "Shulchan Aruch"},
                        {"title": "Safed"},
                    ],
                    "categories": [
                        {"title": "Category:16th-century rabbis"},
                        {"title": "Category:Rabbis in Safed"},
                    ],
                }
            }
        }
    }


@pytest.fixture
def mock_summary_response():
    """Mock REST API page/summary response."""
    return {
        "title": "Joseph Karo",
        "extract": "Joseph ben Ephraim Karo was a major author of Jewish law.",
        "description": "Rabbi and author",
        "pageid": 12345,
        "revision": "rev123",
    }


# ---------------------------------------------------------------------------
# Title Resolution Tests
# ---------------------------------------------------------------------------


class TestResolveTitlesBatch:
    def test_resolves_qids_to_titles(self, mock_wikidata_response):
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            return_value=mock_wikidata_response,
        ):
            result = asyncio.run(resolve_titles_batch(["Q193460", "Q440285"]))
        assert result["Q193460"] == "Joseph Karo"
        assert result["Q440285"] == "Moses Isserles"

    def test_missing_sitelink_returns_none(self):
        response = {"entities": {"Q999": {"sitelinks": {}}}}
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            return_value=response,
        ):
            result = asyncio.run(resolve_titles_batch(["Q999"]))
        assert result.get("Q999") is None

    def test_missing_entity_returns_none(self):
        """Entity not found at all in response."""
        response = {"entities": {}}
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            return_value=response,
        ):
            result = asyncio.run(resolve_titles_batch(["Q999"]))
        assert result.get("Q999") is None

    def test_batching_splits_large_lists(self, mock_wikidata_response):
        """More than 50 QIDs should result in multiple _api_get calls."""
        qids = [f"Q{i}" for i in range(75)]
        # Return entities for all of them
        entities = {}
        for qid in qids:
            entities[qid] = {"sitelinks": {"enwiki": {"title": f"Article_{qid}"}}}
        response = {"entities": entities}

        mock_get = AsyncMock(return_value=response)
        with patch("scripts.enrichment.wikipedia_client._api_get", mock_get):
            asyncio.run(resolve_titles_batch(qids))
        # Should be called at least twice (75 QIDs / 50 per batch = 2 calls)
        assert mock_get.call_count >= 2

    def test_empty_qids_returns_empty(self):
        result = asyncio.run(resolve_titles_batch([]))
        assert result == {}


# ---------------------------------------------------------------------------
# Links + Categories Tests
# ---------------------------------------------------------------------------


class TestFetchLinksBatch:
    def test_extracts_links_and_categories(self, mock_links_response):
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            return_value=mock_links_response,
        ):
            result = asyncio.run(fetch_links_batch(["Joseph Karo"]))
        assert "Joseph Karo" in result
        links = result["Joseph Karo"]
        assert isinstance(links, WikipediaLinks)
        assert "Moses Isserles" in links.article_links
        assert "Shulchan Aruch" in links.article_links
        assert "16th-century rabbis" in links.categories
        assert "Rabbis in Safed" in links.categories

    def test_filters_broad_categories(self, mock_links_response):
        # Add broad/maintenance categories that should be filtered out
        mock_links_response["query"]["pages"]["12345"]["categories"].extend(
            [
                {"title": "Category:Articles with hCards"},
                {"title": "Category:CS1 maint: multiple names"},
                {"title": "Category:All stub articles"},
                {"title": "Category:Wikipedia articles incorporating text"},
                {"title": "Category:Pages using sidebar with deprecated parameters"},
                {"title": "Category:Webarchive template wayback links"},
                {"title": "Category:Use dmy dates from March 2020"},
                {"title": "Category:Short description matches Wikidata"},
                {"title": "Category:Living people"},
                {"title": "Category:AC with 14 elements"},
            ]
        )
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            return_value=mock_links_response,
        ):
            result = asyncio.run(fetch_links_batch(["Joseph Karo"]))
        cats = result["Joseph Karo"].categories
        # Substantive categories should remain
        assert "16th-century rabbis" in cats
        assert "Rabbis in Safed" in cats
        # Broad/maintenance categories should be filtered
        assert "Articles with hCards" not in cats
        assert "CS1 maint: multiple names" not in cats
        assert "All stub articles" not in cats
        assert "Wikipedia articles incorporating text" not in cats
        assert "Living people" not in cats

    def test_page_with_no_links_or_categories(self):
        """Page exists but has empty links/categories."""
        response = {
            "query": {
                "pages": {
                    "99999": {
                        "title": "Obscure Page",
                        "links": [],
                        "categories": [],
                    }
                }
            }
        }
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            return_value=response,
        ):
            result = asyncio.run(fetch_links_batch(["Obscure Page"]))
        assert "Obscure Page" in result
        assert result["Obscure Page"].article_links == []
        assert result["Obscure Page"].categories == []

    def test_empty_titles_returns_empty(self):
        result = asyncio.run(fetch_links_batch([]))
        assert result == {}

    def test_missing_page_key_handled(self):
        """Page is 'missing' in response (e.g., article doesn't exist)."""
        response = {
            "query": {
                "pages": {
                    "-1": {
                        "title": "Nonexistent Article",
                        "missing": "",
                    }
                }
            }
        }
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            return_value=response,
        ):
            result = asyncio.run(fetch_links_batch(["Nonexistent Article"]))
        # Missing page should not appear in results
        assert "Nonexistent Article" not in result


# ---------------------------------------------------------------------------
# Summary Tests
# ---------------------------------------------------------------------------


class TestFetchSummary:
    def test_returns_summary(self, mock_summary_response):
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            return_value=mock_summary_response,
        ):
            result = asyncio.run(fetch_summary("Joseph Karo"))
        assert isinstance(result, WikipediaSummary)
        assert result.title == "Joseph Karo"
        assert "Jewish law" in result.extract
        assert result.description == "Rabbi and author"
        assert result.page_id == 12345
        assert result.revision_id == "rev123"

    def test_returns_none_on_404(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "404", request=MagicMock(), response=mock_response
            ),
        ):
            result = asyncio.run(fetch_summary("NonexistentPage"))
        assert result is None

    def test_returns_none_on_other_http_error(self):
        """Non-404 HTTP errors should also return None (graceful)."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=mock_response
            ),
        ):
            result = asyncio.run(fetch_summary("SomePage"))
        assert result is None

    def test_returns_none_on_timeout(self):
        """Timeout should return None, not raise."""
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("timed out"),
        ):
            result = asyncio.run(fetch_summary("SlowPage"))
        assert result is None

    def test_summary_with_missing_optional_fields(self):
        """Response may lack description or revision."""
        response = {
            "title": "Simple Page",
            "extract": "A simple page.",
            "pageid": 1,
        }
        with patch(
            "scripts.enrichment.wikipedia_client._api_get",
            new_callable=AsyncMock,
            return_value=response,
        ):
            result = asyncio.run(fetch_summary("Simple Page"))
        assert result is not None
        assert result.title == "Simple Page"
        assert result.description is None
        assert result.revision_id is None
