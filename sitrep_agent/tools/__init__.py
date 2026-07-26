"""
sitrep_agent/tools/__init__.py

Central registry for all agent tools. Import this to access any tool by name.

Adding a new tool:
  1. Create your_tool.py in this directory
  2. Inherit from BaseTool, implement get_schema() and execute()
  3. Import and register below
  4. The orchestrator in orchestrator.py will automatically discover it

Current tools:
  web_search    — DuckDuckGo search (no API key)
  web_scraper   — URL content extraction
  wikipedia     — Wikipedia REST API
  calendar      — Google Calendar template links (no auth)
  calendar_api  — Google Calendar API (real events, service account)
  email         — Personalized email drafter
  slides        — Slide outline + HTML preview
  action_items  — Structured task extractor
  research      — Multi-source synthesizer
  memory        — SQLite meeting memory & context retrieval
  slack         — Slack channel messenger
  notion        — Notion page creator
  jira          — Jira ticket creator
"""

from __future__ import annotations

from .action_items import ActionItemsTool
from .base import BaseTool, ToolResult, ToolSchema
from .calendar import CalendarTool
from .calendar_api import CalendarAPITool
from .email import EmailTool
from .email_sender import EmailSenderTool
from .hubspot import HubSpotTool
from .jira import JiraTool
from .linear import LinearTool
from .mcp_client import MCPClientTool
from .memory import MemoryTool
from .notion import NotionTool
from .research import ResearchTool
from .slack import SlackTool
from .slides import SlidesTool
from .vector_memory import VectorMemoryTool
from .web_scraper import WebScraperTool
from .web_search import WebSearchTool
from .wikipedia import WikipediaTool

# Registry: name -> class
TOOL_REGISTRY: dict[str, type[BaseTool]] = {
    "web_search": WebSearchTool,
    "web_scraper": WebScraperTool,
    "wikipedia": WikipediaTool,
    "calendar": CalendarTool,
    "calendar_api": CalendarAPITool,
    "email": EmailTool,
    "email_sender": EmailSenderTool,
    "slides": SlidesTool,
    "action_items": ActionItemsTool,
    "research": ResearchTool,
    "memory": MemoryTool,
    "slack": SlackTool,
    "notion": NotionTool,
    "jira": JiraTool,
    "linear": LinearTool,
    "hubspot": HubSpotTool,
    "mcp_client": MCPClientTool,
    "vector_memory": VectorMemoryTool,
}

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolSchema",
    "TOOL_REGISTRY",
    "WebSearchTool",
    "WebScraperTool",
    "WikipediaTool",
    "CalendarTool",
    "CalendarAPITool",
    "EmailTool",
    "EmailSenderTool",
    "SlidesTool",
    "ActionItemsTool",
    "ResearchTool",
    "MemoryTool",
    "SlackTool",
    "NotionTool",
    "JiraTool",
    "LinearTool",
    "HubSpotTool",
    "MCPClientTool",
    "VectorMemoryTool",
]
