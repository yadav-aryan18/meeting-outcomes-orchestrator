"""
sitrep_agent/tools/__init__.py

Central registry for all agent tools. Import this to access any tool by name.

Adding a new tool:
  1. Create your_tool.py in this directory
  2. Inherit from BaseTool, implement execute()
  3. Import and register below
  4. The orchestrator in handler.py will automatically discover it
"""

from __future__ import annotations

from .action_items import ActionItemsTool
from .base import BaseTool, ToolResult
from .calendar import CalendarTool
from .email import EmailTool
from .research import ResearchTool
from .slides import SlidesTool
from .web_scraper import WebScraperTool
from .web_search import WebSearchTool
from .wikipedia import WikipediaTool

# Registry: name -> class
TOOL_REGISTRY: dict[str, type[BaseTool]] = {
    "web_search": WebSearchTool,
    "web_scraper": WebScraperTool,
    "wikipedia": WikipediaTool,
    "calendar": CalendarTool,
    "email": EmailTool,
    "slides": SlidesTool,
    "action_items": ActionItemsTool,
    "research": ResearchTool,
}

__all__ = [
    "BaseTool",
    "ToolResult",
    "TOOL_REGISTRY",
    "WebSearchTool",
    "WebScraperTool",
    "WikipediaTool",
    "CalendarTool",
    "EmailTool",
    "SlidesTool",
    "ActionItemsTool",
    "ResearchTool",
]
