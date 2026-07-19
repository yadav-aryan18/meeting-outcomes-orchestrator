"""
sitrep_agent/tools/wikipedia.py

Wikipedia summary tool using the official REST API.
No API key required — free, reliable, and fast.

Features:
  - Fetches concise summaries from Wikipedia
  - Auto-normalizes search terms (spaces → underscores)
  - Graceful fallback on missing pages or network errors
  - Returns structured data with title, extract, and page URL

Usage:
    result = await WikipediaTool(ctx).execute(topic="artificial intelligence")
    # result.data = {"title": "...", "extract": "...", "url": "..."}
"""
from __future__ import annotations

import urllib.parse
from typing import Any

import httpx

from .base import BaseTool, ToolResult

WIKI_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKI_PAGE_URL = "https://en.wikipedia.org/wiki/"

# Wikipedia requires a descriptive User-Agent per their API policy
WIKI_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "SitRep-MeetingOutcomesOrchestrator/1.0 "
        "(https://joinsitrep.com; agent@sitrep.example)"
    ),
}


class WikipediaTool(BaseTool):
    """Fetch a concise Wikipedia summary for a given topic."""

    name = "wikipedia"
    description = (
        "Look up a topic on Wikipedia and return a concise, factual summary. "
        "Ideal for grounding meeting discussions in verified background knowledge. "
        "Useful for researching technologies, companies, concepts, or people mentioned in meetings. "
        "No API key required."
    )

    async def execute(self, topic: str, **kwargs: Any) -> ToolResult:
        """Fetch Wikipedia summary for a topic.

        Args:
            topic: The topic to look up (e.g., "machine learning", "Salesforce").

        Returns:
            ToolResult with {"title": str, "extract": str, "url": str} in .data
        """
        self.log(f"wikipedia: looking up \"{topic[:60]}...\"")

        if not topic or not topic.strip():
            return ToolResult(
                success=False,
                data={},
                summary="Empty topic provided.",
                error="Topic string is empty.",
            )

        # Normalize: replace spaces with underscores, strip
        normalized = topic.strip().replace(" ", "_")
        encoded = urllib.parse.quote(normalized)
        url = WIKI_SUMMARY_API + encoded

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=WIKI_HEADERS)

                # 404 means page not found — not a crash, just no result
                if resp.status_code == 404:
                    self.log(f"wikipedia: no page found for \"{topic}\"")
                    return ToolResult(
                        success=True,
                        data={},
                        summary=f"No Wikipedia page found for \"{topic}\".",
                    )

                resp.raise_for_status()
                data = resp.json()

            title = data.get("title", topic)
            extract = data.get("extract", "")
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")

            if not page_url:
                page_url = WIKI_PAGE_URL + urllib.parse.quote(title.replace(" ", "_"))

            self.log(f"wikipedia: found \"{title}\" ({len(extract)} chars)")

            return ToolResult(
                success=True,
                data={"title": title, "extract": extract, "url": page_url},
                summary=f"Wikipedia summary for \"{title}\": {len(extract)} characters.",
            )

        except httpx.HTTPError as e:
            self.log(f"wikipedia: HTTP error — {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary=f"Wikipedia lookup failed for \"{topic}\".",
                error=str(e),
            )
        except Exception as e:
            self.log(f"wikipedia: error — {type(e).__name__}: {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary=f"Wikipedia lookup failed for \"{topic}\".",
                error=str(e),
            )
