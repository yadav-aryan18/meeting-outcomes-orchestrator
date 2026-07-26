"""
sitrep_agent/tools/hubspot.py

HubSpot CRM integration tool using HubSpot REST API v3 (https://api.hubapi.com/).

Logs meeting summary as a CRM meeting activity, creates CRM follow-up tasks
for action items, and associates them with contact records.

Features:
  - Searches contacts by email address
  - Creates CRM meeting engagement records
  - Creates CRM task records for action items
  - Returns confirmation markdown and CRM record links

Setup & Env Vars:
  HUBSPOT_API_KEY / HUBSPOT_ACCESS_TOKEN — Private App Access Token (pat-na1-...)

Usage:
    result = await HubSpotTool(ctx).execute(
        title="Q3 Strategy Meeting",
        summary="Discussed enterprise contract renewal...",
        attendees=[{"name": "Alice", "email": "alice@example.com"}],
        action_items=[{"action": "Send proposal", "owner": "Alice", "deadline": "2026-08-01"}]
    )
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from .base import BaseTool, ToolResult, ToolSchema

HUBSPOT_TOKEN = os.getenv("HUBSPOT_API_KEY") or os.getenv("HUBSPOT_ACCESS_TOKEN", "")

HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubSpotTool(BaseTool):
    """Log meeting notes and tasks to HubSpot CRM API v3."""

    name = "hubspot"
    description = (
        "Log meeting notes and action items to HubSpot CRM. "
        "Creates CRM meeting engagement records, generates CRM tasks for action items, "
        "and links them to contact records. Essential for sales and client meetings. "
        "Requires HUBSPOT_API_KEY or HUBSPOT_ACCESS_TOKEN env var."
    )

    def __init__(self, ctx: Any = None):
        super().__init__(ctx=ctx)
        self.token = HUBSPOT_TOKEN
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="hubspot",
            description=(
                "Log meeting notes and action items to HubSpot CRM. "
                "Creates CRM meeting engagement records, generates CRM tasks for action items, "
                "and links them to contact records. Requires HUBSPOT_API_KEY or HUBSPOT_ACCESS_TOKEN env var."
            ),
            parameters={
                "title": {
                    "type": "string",
                    "description": "Meeting title.",
                },
                "summary": {
                    "type": "string",
                    "description": "Meeting summary text.",
                    "default": "",
                },
                "attendees": {
                    "type": "array",
                    "description": "List of attendee dicts with 'email' and 'name'.",
                },
                "action_items": {
                    "type": "array",
                    "description": "List of action item dicts to create as CRM tasks.",
                },
            },
            required=["title"],
            returns="Dict with created 'meeting_id', 'task_ids', and 'contact_ids' keys.",
        )

    async def execute(
        self,
        title: str = "",
        summary: str = "",
        attendees: list[dict[str, Any]] | None = None,
        action_items: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Log meeting notes and tasks to HubSpot CRM.

        Args:
            title: Meeting title.
            summary: Meeting summary text.
            attendees: List of attendee dicts.
            action_items: List of action item dicts.

        Returns:
            ToolResult with CRM IDs and confirmation artifacts.
        """
        title = title or kwargs.get("task_title") or "Meeting Log"

        if not self.token:
            msg = "HubSpot CRM not configured. Set HUBSPOT_API_KEY or HUBSPOT_ACCESS_TOKEN in .env."
            self.log(f"hubspot: {msg}")
            return ToolResult(
                success=False,
                data={},
                summary=msg,
                error="Missing HUBSPOT_API_KEY / HUBSPOT_ACCESS_TOKEN env var.",
            )

        self.log(f"hubspot: logging meeting notes for \"{title[:40]}...\"")

        attendees = attendees or []
        action_items = action_items or kwargs.get("items", [])

        # Step 1: Resolve contacts by email
        contact_ids = []
        for attendee in attendees:
            email = attendee.get("email", "")
            if email and "@" in email:
                c_id = await self._find_contact_by_email(email)
                if c_id:
                    contact_ids.append(c_id)

        # Step 2: Create Meeting Engagement
        meeting_id = await self._create_meeting_engagement(title, summary, contact_ids)

        # Step 3: Create CRM Tasks for Action Items
        task_ids = []
        for item in action_items:
            t_id = await self._create_task(item, summary)
            if t_id:
                task_ids.append(t_id)

        self.log(f"hubspot: logged meeting ID {meeting_id}, created {len(task_ids)} CRM task(s)")

        md = (
            f"✅ **HubSpot CRM Activity Logged**\n\n"
            f"**Meeting Title:** {title}\n"
            f"**HubSpot Meeting ID:** `{meeting_id or 'Created'}`\n"
            f"**Associated Contacts:** {len(contact_ids)}\n"
            f"**CRM Tasks Created:** {len(task_ids)}\n\n"
            f"**Summary:**\n{summary[:500]}"
        )

        return ToolResult(
            success=True,
            data={
                "meeting_id": meeting_id,
                "task_ids": task_ids,
                "contact_ids": contact_ids,
            },
            summary=f"HubSpot CRM activity logged ({len(task_ids)} tasks created, {len(contact_ids)} contacts linked).",
            artifacts=[
                {
                    "type": "markdown",
                    "title": f"HubSpot CRM Log: {title}",
                    "content": md,
                }
            ],
        )

    async def _find_contact_by_email(self, email: str) -> str | None:
        """Search for a HubSpot contact by email."""
        url = f"{HUBSPOT_API_BASE}/crm/v3/objects/contacts/search"
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "email",
                            "operator": "EQ",
                            "value": email,
                        }
                    ]
                }
            ],
            "limit": 1,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=self.headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                if results:
                    return results[0].get("id")
        except Exception as e:
            self.log(f"hubspot: contact search error for {email} — {str(e)[:80]}")
        return None

    async def _create_meeting_engagement(
        self, title: str, summary: str, contact_ids: list[str]
    ) -> str | None:
        """Create a HubSpot meeting object."""
        url = f"{HUBSPOT_API_BASE}/crm/v3/objects/meetings"
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        payload: dict[str, Any] = {
            "properties": {
                "hs_meeting_title": title,
                "hs_meeting_body": summary,
                "hs_timestamp": str(now_ms),
            }
        }

        if contact_ids:
            payload["associations"] = [
                {
                    "to": {"id": cid},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": 200,  # Meeting to Contact
                        }
                    ],
                }
                for cid in contact_ids
            ]

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, headers=self.headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("id")
        except Exception as e:
            self.log(f"hubspot: meeting creation error — {str(e)[:80]}")
        return None

    async def _create_task(self, item: dict[str, Any], summary: str) -> str | None:
        """Create a HubSpot task object for an action item."""
        url = f"{HUBSPOT_API_BASE}/crm/v3/objects/tasks"

        action = item.get("action") or item.get("title") or "Action Item"
        owner = item.get("owner", "")
        deadline = item.get("deadline", "")
        priority = item.get("priority", "MEDIUM").upper()
        if priority not in ("HIGH", "MEDIUM", "LOW"):
            priority = "MEDIUM"

        body_parts = [f"Task: {action}"]
        if owner and owner != "[OWNER?]":
            body_parts.append(f"Owner: {owner}")
        if summary:
            body_parts.append(f"Meeting Context: {summary[:500]}")

        payload: dict[str, Any] = {
            "properties": {
                "hs_task_subject": action[:255],
                "hs_task_body": "\n".join(body_parts),
                "hs_task_priority": priority,
                "hs_task_status": "NOT_STARTED",
            }
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, headers=self.headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("id")
        except Exception as e:
            self.log(f"hubspot: task creation error for '{action[:30]}' — {str(e)[:80]}")
        return None
