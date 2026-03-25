"""Wikipedia & MediaWiki API client for agent enrichment.

Provides batch title resolution (Wikidata -> Wikipedia), batch link/category
fetching, and individual summary fetching. Uses httpx async with rate limiting.

Follows the same pattern as scripts/enrichment/wikidata_client.py.

Usage:
------
# Resolve Wikidata QIDs to Wikipedia article titles
titles = await resolve_titles_batch(["Q193460", "Q440285"])
# -> {"Q193460": "Joseph Karo", "Q440285": "Moses Isserles"}

# Fetch wikilinks + categories for articles
links = await fetch_links_batch(["Joseph Karo", "Moses Isserles"])
# -> {"Joseph Karo": WikipediaLinks(...), ...}

# Fetch summary for a single article
summary = await fetch_summary("Joseph Karo")
# -> WikipediaSummary(title="Joseph Karo", extract="...", ...)
"""

import asyncio
import logging
import re

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

USER_AGENT = (
    "RareBooksBot/1.0 (https://github.com/rare-books-bot; educational research)"
)
REQUEST_DELAY_SECONDS = 0.5  # Conservative rate limiting

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_REST = "https://en.wikipedia.org/api/rest_v1"

BATCH_SIZE = 50  # MediaWiki API max titles per request

# Category patterns to filter out (maintenance, not substantive)
_BROAD_CATEGORY_RE = re.compile(
    r"^("
    r"Articles|All |CS1|Pages|Webarchive|Use |Short description|"
    r"Living people|AC with|Wikipedia|Wikidata|Commons|Harv and Sfn"
    r")",
    re.IGNORECASE,
)


# =============================================================================
# Models
# =============================================================================


class WikipediaSummary(BaseModel):
    """Summary extracted from the Wikipedia REST API /page/summary endpoint."""

    title: str
    extract: str
    description: str | None = None
    page_id: int
    revision_id: str | None = None


class WikipediaLinks(BaseModel):
    """Links and categories extracted from a Wikipedia article via MediaWiki API."""

    article_links: list[str]  # All internal wikilink titles
    categories: list[str]  # Filtered category names (no "Category:" prefix)
    see_also: list[str] = []  # "See also" titles if detectable


# =============================================================================
# HTTP Helper
# =============================================================================


async def _api_get(url: str, params: dict, timeout: float = 30.0) -> dict:
    """Make a GET request with User-Agent and rate limiting.

    This function is the single HTTP touchpoint, making it easy to mock
    in tests without patching httpx internals.

    Args:
        url: Request URL
        params: Query parameters
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON response as dict

    Raises:
        httpx.HTTPStatusError: On non-2xx status codes
        httpx.TimeoutException: On request timeout
    """
    await asyncio.sleep(REQUEST_DELAY_SECONDS)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()


# =============================================================================
# Title Resolution
# =============================================================================


async def resolve_titles_batch(qids: list[str]) -> dict[str, str | None]:
    """Resolve Wikidata QIDs to English Wikipedia article titles.

    Uses the Wikidata wbgetentities API with sitefilter=enwiki.
    Batches up to 50 QIDs per request per MediaWiki API limits.

    Args:
        qids: List of Wikidata QIDs (e.g., ["Q193460", "Q440285"])

    Returns:
        Dict mapping QID -> Wikipedia title (or None if no enwiki sitelink)
    """
    if not qids:
        return {}

    result: dict[str, str | None] = {}

    for batch_start in range(0, len(qids), BATCH_SIZE):
        batch = qids[batch_start : batch_start + BATCH_SIZE]
        ids_param = "|".join(batch)

        try:
            data = await _api_get(
                WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": ids_param,
                    "props": "sitelinks",
                    "sitefilter": "enwiki",
                    "format": "json",
                },
            )
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.RequestError) as e:
            logger.warning("Failed to resolve title batch starting at %d: %s", batch_start, e)
            for qid in batch:
                result[qid] = None
            continue

        entities = data.get("entities", {})
        for qid in batch:
            entity = entities.get(qid, {})
            sitelinks = entity.get("sitelinks", {})
            enwiki = sitelinks.get("enwiki", {})
            title = enwiki.get("title")
            if title:
                result[qid] = title
            else:
                result[qid] = None

    return result


# =============================================================================
# Link + Category Fetching
# =============================================================================


def _is_broad_category(cat_name: str) -> bool:
    """Check if a category name matches broad/maintenance patterns.

    Args:
        cat_name: Category name without the "Category:" prefix

    Returns:
        True if the category should be filtered out
    """
    return bool(_BROAD_CATEGORY_RE.search(cat_name))


def _strip_category_prefix(raw_title: str) -> str:
    """Strip the 'Category:' prefix from a category title.

    Args:
        raw_title: Raw category title (e.g., "Category:16th-century rabbis")

    Returns:
        Category name without prefix (e.g., "16th-century rabbis")
    """
    if raw_title.startswith("Category:"):
        return raw_title[len("Category:"):]
    return raw_title


async def fetch_links_batch(titles: list[str]) -> dict[str, WikipediaLinks]:
    """Fetch internal wikilinks and categories for Wikipedia articles.

    Uses the MediaWiki Action API with prop=links|categories.
    Batches up to 50 titles per request. Filters out broad/maintenance
    categories using regex patterns.

    Args:
        titles: List of Wikipedia article titles

    Returns:
        Dict mapping title -> WikipediaLinks (only for pages that exist)
    """
    if not titles:
        return {}

    result: dict[str, WikipediaLinks] = {}

    for batch_start in range(0, len(titles), BATCH_SIZE):
        batch = titles[batch_start : batch_start + BATCH_SIZE]
        titles_param = "|".join(batch)

        try:
            data = await _api_get(
                WIKIPEDIA_API,
                params={
                    "action": "query",
                    "titles": titles_param,
                    "prop": "links|categories",
                    "pllimit": "500",
                    "cllimit": "50",
                    "format": "json",
                },
            )
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.RequestError) as e:
            logger.warning("Failed to fetch links batch starting at %d: %s", batch_start, e)
            continue

        pages = data.get("query", {}).get("pages", {})
        for _page_id, page_data in pages.items():
            # Skip missing pages
            if "missing" in page_data:
                continue

            title = page_data.get("title", "")

            # Extract article links
            raw_links = page_data.get("links", [])
            article_links = [link["title"] for link in raw_links if "title" in link]

            # Extract and filter categories
            raw_categories = page_data.get("categories", [])
            categories = []
            for cat in raw_categories:
                raw_title = cat.get("title", "")
                cat_name = _strip_category_prefix(raw_title)
                if cat_name and not _is_broad_category(cat_name):
                    categories.append(cat_name)

            result[title] = WikipediaLinks(
                article_links=article_links,
                categories=categories,
                see_also=[],  # See-also detection requires parsing article text
            )

    return result


# =============================================================================
# Summary Fetching
# =============================================================================


async def fetch_summary(title: str) -> WikipediaSummary | None:
    """Fetch summary extract for a single Wikipedia article.

    Uses the Wikipedia REST API /page/summary/{title} endpoint.
    Returns None on 404, timeout, or other errors.

    Args:
        title: Wikipedia article title (e.g., "Joseph Karo")

    Returns:
        WikipediaSummary or None if article not found / error occurred
    """
    # URL-encode the title for the REST API path
    encoded_title = title.replace(" ", "_")
    url = f"{WIKIPEDIA_REST}/page/summary/{encoded_title}"

    try:
        data = await _api_get(url, params={})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.debug("Wikipedia article not found: %s", title)
        else:
            logger.warning("HTTP error fetching summary for %s: %s", title, e)
        return None
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("Error fetching summary for %s: %s", title, e)
        return None

    return WikipediaSummary(
        title=data.get("title", title),
        extract=data.get("extract", ""),
        description=data.get("description"),
        page_id=data.get("pageid", 0),
        revision_id=data.get("revision"),
    )
