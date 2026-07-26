"""
sitrep_agent/tools/notion.py

Notion integration for creating structured meeting notes pages.

Posts meeting summaries, action items, and follow-ups as rich Notion pages
in a specified database. Supports:
  - Creating pages with structured properties (title, date, attendees, status)
  - Rich content blocks (headings, paragraphs, to-do lists, callouts)
  - Linking action items as checkbox tasks

Setup:
  1. Create a Notion integration at https://www.notion.so/my-integrations
  2. Copy the "Internal Integration Token"
  3. Share your database with the integration
  4. Copy the database ID from the URL

Env vars:
  NOTION_TOKEN — Integration token (secret_...)
  NOTION_DATABASE_ID — Database ID to create pages in

Usage:
    result = await NotionTool(ctx).execute(
        title="Q3 Planning Meeting",
        summary="Meeting summary...",
        action_items=[{"action": "Do X", "owner": "Alice", "deadline": "Friday"}],
        attendees=[{"name": "Alice"}],
    )
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

import httpx

from .base import BaseTool, ToolResult, ToolSchema

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionTool(BaseTool):
    """Create structured meeting notes pages in Notion."""

    name = "notion"
    description = (
        "Create a structured Notion page with meeting summary, action items, and attendee list. "
        "Ideal for building a persistent knowledge base of meeting outcomes. "
        "Requires NOTION_TOKEN and NOTION_DATABASE_ID env vars."
    )

    def __init__(self, ctx: Any = None):
        super().__init__(ctx=ctx)
        self.token = NOTION_TOKEN
        self.database_id = NOTION_DATABASE_ID
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }


    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="notion",
            description=(
                "Create a structured Notion page with meeting summary, action items, and attendee list. "
                "Ideal for building a persistent knowledge base of meeting outcomes. "
                "Requires NOTION_TOKEN and NOTION_DATABASE_ID env vars. "
                "Use this when you want to save meeting notes to a knowledge base."
            ),
            parameters={
                "title": {
                    "type": "string",
                    "description": "Page title.",
                },
                "summary": {
                    "type": "string",
                    "description": "Meeting summary text.",
                    "default": "",
                },
                "action_items": {
                    "type": "array",
                    "description": "List of action item dicts.",
                },
                "attendees": {
                    "type": "array",
                    "description": "List of attendee dicts.",
                },
                "tags": {
                    "type": "array",
                    "description": "Optional list of tags (e.g., ['sprint', 'planning']).",
                },
            },
            required=["title"],
            returns="Dict with 'page_id' and 'url' keys.",
        )

    async def execute(
        self,
        title: str = "",
        summary: str = "",
        action_items: list[dict[str, str]] | None = None,
        attendees: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        title = title or kwargs.get("task_title") or "Meeting Notes"
        """Create a Notion page in the configured database.

        Args:
            title: Page title.
            summary: Meeting summary text.
            action_items: List of action item dicts.
            attendees: List of attendee dicts.
            tags: Optional list of tags (e.g., ["sprint", "planning"]).

        Returns:
            ToolResult with Notion page URL in artifacts.
        """
        if not self.token or not self.database_id:
            self.log("notion: not configured — missing NOTION_TOKEN or NOTION_DATABASE_ID")
            return ToolResult(
                success=False,
                data={},
                summary="Notion is not configured. Set NOTION_TOKEN and NOTION_DATABASE_ID env vars.",
                error="Missing Notion credentials.",
            )

        self.log(f"notion: creating page \"{title[:50]}...\"")

        # Build rich content blocks
        children = self._build_content_blocks(summary, action_items or [])

        # Build page properties
        properties: dict[str, Any] = {
            "Name": {"title": [{"text": {"content": title}}]},
        }

        # Add date
        properties["Date"] = {"date": {"start": str(date.today())}}

        # Add attendees as multi-select if available
        if attendees:
            attendee_names = [a.get("name", "") for a in attendees if a.get("name")]
            if attendee_names:
                properties["Attendees"] = {
                    "multi_select": [{"name": n} for n in attendee_names]
                }

        # Add tags
        if tags:
            properties["Tags"] = {"multi_select": [{"name": t} for t in tags]}

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
            "children": children,
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{NOTION_API_BASE}/pages",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            page_id = data.get("id", "")
            page_url = data.get("url", f"https://notion.so/{page_id.replace('-', '')}")

            self.log(f"notion: page created — {page_url}")

            return ToolResult(
                success=True,
                data={"page_id": page_id, "url": page_url},
                summary=f"Notion page created: {title}",
                artifacts=[
                    {
                        "type": "link",
                        "title": f"Notion: {title}",
                        "content": page_url,
                    },
                    {
                        "type": "markdown",
                        "title": "Notion Export",
                        "content": (
                            f"✅ **Notion page created**\n\n"
                            f"**Title:** {title}\n"
                            f"**URL:** {page_url}\n\n"
                            f"**Summary:**\n{summary[:800]}"
                        ),
                    },
                ],
            )

        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.json().get("message", "")
            except Exception:
                pass
            self.log(f"notion: HTTP {e.response.status_code} — {detail[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary=f"Notion API error (HTTP {e.response.status_code}).",
                error=detail or str(e),
            )
        except Exception as e:
            self.log(f"notion: error — {type(e).__name__}: {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary="Failed to create Notion page.",
                error=str(e),
            )

    def _build_content_blocks(
        self, summary: str, action_items: list[dict[str, str]]
    ) -> list[dict]:
        """Build Notion block children for rich content."""
        blocks: list[dict] = []

        # Summary section
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "📝 Meeting Summary"}}]
            },
        })

        # Split summary into paragraphs
        for paragraph in summary.split("\n\n"):
            if paragraph.strip():
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": paragraph.strip()}}]
                    },
                })

        # Action items section
        if action_items:
            blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {},
            })
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "✅ Action Items"}}]
                },
            })

            for item in action_items:
                action = item.get("action", "")
                owner = item.get("owner", "[OWNER?]")
                deadline = item.get("deadline", "[DEADLINE?]")
                priority = item.get("priority", "Medium")

                text = f"{action} — @{owner} | Due: {deadline} | Priority: {priority}"
                blocks.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": text}}],
                        "checked": False,
                    },
                })

        return blocks
