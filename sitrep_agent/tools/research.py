"""
sitrep_agent/tools/research.py

Orchestrates multi-source research by combining web search, Wikipedia, and
optional web scraping into a single coherent brief. This is the "intelligence
layer" of the agent.

Features:
  - Runs web search and Wikipedia lookups in parallel
  - Optionally scrapes top result URLs for deeper context
  - Synthesizes everything into a structured research brief
  - Cites sources clearly
  - Gracefully degrades if sources fail

Usage:
    result = await ResearchTool(ctx).execute(
        query="competitive landscape for CRM software 2026",
        summary="Meeting summary...",
        llm=ctx.llm,
        scrape_urls=True
    )
"""
from __future__ import annotations

import asyncio
from typing import Any

from .base import BaseTool, ToolResult
from .web_search import WebSearchTool
from .wikipedia import WikipediaTool
from .web_scraper import WebScraperTool


class ResearchTool(BaseTool):
    """Multi-source research synthesizer."""

    name = "research"
    description = (
        "Conduct multi-source research on any topic and synthesize a structured brief. "
        "Combines web search, Wikipedia, and web scraping to provide comprehensive, "
        "cited background information. Use this when a meeting task involves research, "
        "competitive analysis, market sizing, technology evaluation, or fact-checking."
    )

    async def execute(
        self,
        query: str,
        summary: str = "",
        llm: Any = None,
        scrape_urls: bool = False,
        max_scrape: int = 2,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute multi-source research.

        Args:
            query: The research query/topic.
            summary: Meeting summary for context.
            llm: The LLM instance (required).
            scrape_urls: Whether to scrape top search result pages.
            max_scrape: Max URLs to scrape (default 2, to stay fast).

        Returns:
            ToolResult with synthesized brief in artifacts.
        """
        self.log(f"research: starting multi-source research on '{query[:60]}...'")

        if not llm:
            return ToolResult(
                success=False,
                data={},
                summary="Research tool requires an LLM instance.",
                error="Missing llm parameter.",
            )

        # Step 1: Run web search and Wikipedia in parallel
        web_tool = WebSearchTool(ctx=self.ctx)
        wiki_tool = WikipediaTool(ctx=self.ctx)

        search_task = web_tool.execute(query=query, num_results=5)
        wiki_task = wiki_tool.execute(topic=query)

        search_result, wiki_result = await asyncio.gather(
            search_task, wiki_task, return_exceptions=True
        )

        # Handle exceptions
        if isinstance(search_result, Exception):
            self.log(f"research: web search failed — {str(search_result)[:100]}")
            search_result = ToolResult(success=False, data=[], summary="Search failed.")
        if isinstance(wiki_result, Exception):
            self.log(f"research: wikipedia failed — {str(wiki_result)[:100]}")
            wiki_result = ToolResult(success=False, data={}, summary="Wikipedia failed.")

        # Step 2: Optionally scrape top URLs
        scraped_contents = []
        if scrape_urls and search_result.success and isinstance(search_result.data, list):
            urls_to_scrape = [
                r["url"] for r in search_result.data[:max_scrape]
                if r.get("url") and r["url"].startswith("http")
            ]

            if urls_to_scrape:
                self.log(f"research: scraping {len(urls_to_scrape)} URLs")
                scraper = WebScraperTool(ctx=self.ctx)
                scrape_tasks = [scraper.execute(url=u) for u in urls_to_scrape]
                scrape_results = await asyncio.gather(*scrape_tasks, return_exceptions=True)

                for res in scrape_results:
                    if isinstance(res, ToolResult) and res.success and res.data.get("content"):
                        scraped_contents.append(res.data)

        # Step 3: Build context for synthesis
        context_parts = []

        if wiki_result.success and wiki_result.data.get("extract"):
            ctx_data = wiki_result.data
            context_parts.append(
                f"## Wikipedia: {ctx_data['title']}\n{ctx_data['extract']}\n"
                f"Source: {ctx_data.get('url', '')}"
            )

        if search_result.success and search_result.data:
            context_parts.append("## Web Search Results")
            for i, result in enumerate(search_result.data[:5], 1):
                context_parts.append(
                    f"{i}. **{result.get('title', 'Untitled')}**\n"
                    f"   URL: {result.get('url', '')}\n"
                    f"   {result.get('snippet', '')}"
                )

        for scrape in scraped_contents:
            context_parts.append(
                f"## Scraped: {scrape.get('title', 'Untitled')}\n"
                f"URL: {scrape.get('url', '')}\n"
                f"{scrape.get('content', '')[:1500]}"
            )

        if not context_parts:
            return ToolResult(
                success=False,
                data={},
                summary=f"No research sources found for '{query}'.",
                error="All research sources failed or returned empty.",
            )

        full_context = "\n\n".join(context_parts)

        # Step 4: Synthesize with LLM
        system = (
            "You are a senior research analyst. Synthesize the provided source material "
            "into a tight, structured research brief with these sections:\n\n"
            "1. **Overview** (2-3 sentences)\n"
            "2. **Key Findings** (3-5 bullet points with citations like [Source 1])\n"
            "3. **Market/Competitive Context** (if relevant)\n"
            "4. **Implications** (what this means for the business)\n"
            "5. **Open Questions** (gaps in the research)\n\n"
            "Rules:\n"
            "- Ground every claim in the provided sources\n"
            "- Use [Source N] citations\n"
            "- Clearly mark anything unverified with [UNVERIFIED]\n"
            "- Keep it under 500 words\n"
            "- Write for a busy executive who needs the TL;DR"
        )

        user = (
            f"Research query: {query}\n\n"
            f"Meeting context:\n{summary}\n\n"
            f"Source material:\n{full_context}"
        )

        try:
            brief = await llm.complete(system=system, prompt=user, temperature=0.4)

            self.log(f"research: brief synthesized ({len(brief)} chars)")

            return ToolResult(
                success=True,
                data={
                    "brief": brief,
                    "sources_used": len(context_parts),
                    "query": query,
                },
                summary=f"Research brief synthesized from {len(context_parts)} sources.",
                artifacts=[
                    {
                        "type": "markdown",
                        "title": f"{query} — Research Brief",
                        "content": brief,
                    },
                ],
            )

        except Exception as e:
            self.log(f"research: synthesis error — {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={"raw_context": full_context},
                summary="Research synthesis failed, but raw sources were gathered.",
                error=str(e),
            )
