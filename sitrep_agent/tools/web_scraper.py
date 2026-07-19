"""
sitrep_agent/tools/web_scraper.py

Web scraping tool for extracting readable content from URLs.
No API key required — uses httpx with smart content extraction.

Features:
  - Fetches any public URL and extracts main article text
  - Removes scripts, styles, nav, ads, and other boilerplate
  - Graceful fallback on paywalls, blocks, or errors
  - Returns structured content with title and body

Usage:
    result = await WebScraperTool(ctx).execute(url="https://example.com/article")
    # result.data = {"title": "...", "content": "...", "url": "..."}
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from .base import BaseTool, ToolResult

# Request headers that identify us politely
POLITE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
}

# Tags to completely remove (noise)
NOISE_TAGS = [
    "script", "style", "nav", "header", "footer",
    "aside", "[role=banner]", "[role=complementary]",
    ".sidebar", "#sidebar", ".advertisement", ".ads",
    ".comments", "#comments", ".social-share", ".related-posts",
]


class WebScraperTool(BaseTool):
    """Scrape readable content from a web page URL."""

    name = "web_scraper"
    description = (
        "Fetch and extract the main readable content from a web page URL. "
        "Useful for reading articles, blog posts, documentation, or any web page "
        "mentioned in a meeting. Returns the page title and cleaned body text. "
        "No API key required."
    )

    async def execute(self, url: str, max_chars: int = 8000, **kwargs: Any) -> ToolResult:
        """Scrape content from a URL.

        Args:
            url: The web page URL to scrape.
            max_chars: Maximum characters to return (default 8000).

        Returns:
            ToolResult with {"title": str, "content": str, "url": str} in .data
        """
        self.log(f"web_scraper: fetching {url[:80]}...")

        if not url or not url.startswith(("http://", "https://")):
            return ToolResult(
                success=False,
                data={},
                summary="Invalid URL provided.",
                error="URL must start with http:// or https://",
            )

        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=POLITE_HEADERS)
                resp.raise_for_status()
                html = resp.text

            title = self._extract_title(html)
            content = self._extract_content(html, max_chars)

            self.log(f"web_scraper: extracted {len(content)} chars from \"{title[:50]}...\"")

            return ToolResult(
                success=True,
                data={"title": title, "content": content, "url": url},
                summary=f"Extracted {len(content)} characters from \"{title}\"",
            )

        except httpx.HTTPStatusError as e:
            self.log(f"web_scraper: HTTP {e.response.status_code} for {url}")
            return ToolResult(
                success=False,
                data={},
                summary=f"Could not access {url} (HTTP {e.response.status_code}).",
                error=f"HTTP {e.response.status_code}",
            )
        except Exception as e:
            self.log(f"web_scraper: error — {type(e).__name__}: {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary=f"Failed to scrape {url}. Proceeding without this source.",
                error=str(e),
            )

    def _extract_title(self, html: str) -> str:
        """Extract the page title from HTML."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
        if match:
            return self._clean_text(match.group(1))

        match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
        if match:
            return self._clean_text(match.group(1))

        return "Untitled Page"

    def _extract_content(self, html: str, max_chars: int) -> str:
        """Extract main content from HTML using heuristics."""
        # Step 1: Remove noise tags entirely
        for tag in NOISE_TAGS:
            if tag.startswith(".") or tag.startswith("#") or tag.startswith("["):
                pattern = re.compile(
                    rf"<{re.escape(tag.lstrip('.#[').rstrip(']'))}[^>]*>.*?</{re.escape(tag.lstrip('.#[').rstrip(']'))}>",
                    re.DOTALL | re.IGNORECASE,
                )
            else:
                pattern = re.compile(
                    rf"<{tag}[^>]*>.*?</{tag}>",
                    re.DOTALL | re.IGNORECASE,
                )
            html = pattern.sub(" ", html)

        # Step 2: Try to find main content area
        content = ""

        article_match = re.search(
            r"<article[^>]*>(.*?)</article>",
            html, re.DOTALL | re.IGNORECASE,
        )
        if article_match:
            content = article_match.group(1)
        else:
            main_match = re.search(
                r"<main[^>]*>(.*?)</main>",
                html, re.DOTALL | re.IGNORECASE,
            )
            if main_match:
                content = main_match.group(1)
            else:
                body_match = re.search(
                    r"<body[^>]*>(.*?)</body>",
                    html, re.DOTALL | re.IGNORECASE,
                )
                content = body_match.group(1) if body_match else html

        # Step 3: Clean the content
        text = self._clean_text(content)

        # Step 4: Truncate if too long
        if len(text) > max_chars:
            text = text[:max_chars].rsplit(" ", 1)[0] + "... [truncated]"

        return text

    def _clean_text(self, raw: str) -> str:
        """Strip HTML tags and clean up text."""
        if not raw:
            return ""

        raw = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=re.DOTALL | re.IGNORECASE)

        for tag in ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br"]:
            raw = re.sub(rf"</{tag}>", "\n", raw, flags=re.IGNORECASE)
            raw = re.sub(rf"<{tag}[^>]*>", "\n", raw, flags=re.IGNORECASE)

        text = re.sub(r"<[^>]+>", " ", raw)

        entities = {
            "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
            "&#39;": "'", "&nbsp;": " ", "&ndash;": "–", "&mdash;": "—",
            "&rsquo;": "'", "&lsquo;": "'", "&rdquo;": '"', "&ldquo;": '"',
            "&hellip;": "...", "&bull;": "•", "&trade;": "™", "&copy;": "©",
        }
        for ent, char in entities.items():
            text = text.replace(ent, char)

        text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)

        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)
        text = text.strip()

        return text
