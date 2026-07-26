"""
sitrep_agent/tools/web_search.py

Web search tool using DuckDuckGo's HTML interface.
No API key required — works out of the box.

Features:
  - Searches DuckDuckGo and extracts top results
  - Returns title, URL, and snippet for each result
  - Graceful fallback on network errors or blocks
  - Respects DuckDuckGo by using their lite interface with proper User-Agent

Usage:
    result = await WebSearchTool(ctx).execute(query="AI agent market size 2026")
    # result.data = [{"title": "...", "url": "...", "snippet": "..."}, ...]
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any

import httpx

from .base import BaseTool, ToolResult, ToolSchema

# DuckDuckGo lite search endpoint — minimal, fast, no JS required
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
DDG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html",
    "Accept-Language": "en-US,en;q=0.9",
}


class WebSearchTool(BaseTool):
    """Search the web via DuckDuckGo and return structured results."""

    name = "web_search"
    description = (
        "Search the web for current information, news, market data, "
        "competitor intelligence, or any topic mentioned in a meeting. "
        "Returns top results with titles, URLs, and snippets. "
        "No API key required."
    )


    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="web_search",
            description=(
                "Search the web for current information, news, market data, "
                "competitor intelligence, or any topic mentioned in a meeting. "
                "Returns top results with titles, URLs, and snippets. "
                "No API key required. Use this when the meeting mentions a company, "
                "technology, market trend, or any topic that needs external verification."
            ),
            parameters={
                "query": {
                    "type": "string",
                    "description": "The search query. Be specific and include relevant keywords.",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (1-10, default 5).",
                    "default": 5,
                },
            },
            required=["query"],
            returns="List of search results with title, URL, and snippet for each.",
        )

    async def execute(self, query: str = "", num_results: int = 5, **kwargs: Any) -> ToolResult:
        query = query or kwargs.get("topic") or ""
        """Execute a web search.

        Args:
            query: The search query string.
            num_results: Number of results to return (default 5, max 10).

        Returns:
            ToolResult with list of result dicts in .data
        """
        self.log(f"web_search: querying \"{query[:60]}...\"")

        if not query or not query.strip():
            return ToolResult(
                success=False,
                data=[],
                summary="Empty search query provided.",
                error="Query string is empty."
            )

        num_results = min(max(num_results, 1), 10)

        try:
            results = await self._search_ddg(query.strip(), num_results)

            if not results:
                return ToolResult(
                    success=True,
                    data=[],
                    summary=f"No results found for query: {query}",
                )

            summary = f"Found {len(results)} results for \"{query}\". Top result: {results[0]['title']}"
            self.log(f"web_search: {len(results)} results returned")

            return ToolResult(
                success=True,
                data=results,
                summary=summary,
            )

        except Exception as e:
            self.log(f"web_search: error — {type(e).__name__}: {str(e)[:100]}")
            return ToolResult(
                success=False,
                data=[],
                summary=f"Web search failed for \"{query}\". Proceeding with meeting summary only.",
                error=str(e),
            )

    async def _search_ddg(self, query: str, num_results: int) -> list[dict[str, str]]:
        """Perform DuckDuckGo lite search and parse results."""
        payload = {"q": query, "kl": "us-en"}

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.post(DDG_LITE_URL, data=payload, headers=DDG_HEADERS)
            resp.raise_for_status()
            html = resp.text

        results: list[dict[str, str]] = []

        # Pattern 1: result links with snippets
        result_blocks = re.findall(
            r'<tr[^>]*>.*?<a[^>]+class="[^"]*result-link[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'<td[^>]+class="[^"]*result-snippet[^"]*"[^>]*>(.*?)</td>.*?',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        for url, title_raw, snippet_raw in result_blocks[:num_results]:
            title = self._clean_html(title_raw)
            snippet = self._clean_html(snippet_raw)
            real_url = self._extract_real_url(url)

            if title and real_url:
                results.append({
                    "title": title,
                    "url": real_url,
                    "snippet": snippet,
                })

        # Fallback pattern if the first regex didn't match
        if not results:
            results = self._fallback_parse(html, num_results)

        return results

    def _extract_real_url(self, url: str) -> str:
        """Extract the real destination URL from DuckDuckGo redirect URLs."""
        if url.startswith("http") and "duckduckgo.com" not in url:
            return url

        match = re.search(r"uddg=([^&]+)", url)
        if match:
            decoded = urllib.parse.unquote(match.group(1))
            return decoded

        if url.startswith("/"):
            return f"https://duckduckgo.com{url}"

        return url

    def _fallback_parse(self, html: str, num_results: int) -> list[dict[str, str]]:
        """Fallback parser using broader regex patterns."""
        results: list[dict[str, str]] = []

        pattern = re.compile(
            r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>\s*(?:</td>\s*<td[^>]*>(.*?)</td>)?',
            re.DOTALL | re.IGNORECASE,
        )

        for match in pattern.finditer(html):
            url = match.group(1)
            title = self._clean_html(match.group(2))
            snippet = self._clean_html(match.group(3) or "")

            real_url = self._extract_real_url(url)

            if title and len(title) > 5 and real_url and "duckduckgo.com" not in real_url:
                results.append({
                    "title": title,
                    "url": real_url,
                    "snippet": snippet,
                })

            if len(results) >= num_results:
                break

        return results

    def _clean_html(self, raw: str) -> str:
        """Strip HTML tags and decode entities from a string."""
        if not raw:
            return ""

        raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)

        text = re.sub(r"<[^>]+>", " ", raw)

        entities = {
            "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
            "&#39;": "'", "&nbsp;": " ", "&ndash;": "–", "&mdash;": "—",
        }
        for ent, char in entities.items():
            text = text.replace(ent, char)

        text = re.sub(r"\s+", " ", text).strip()

        return text
