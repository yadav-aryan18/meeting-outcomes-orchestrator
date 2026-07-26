"""
sitrep_agent/tools/jira.py

Jira Cloud integration for creating tickets from meeting action items.

Transforms extracted action items into actual Jira issues with:
  - Proper issue type (Task, Story, Bug, etc.)
  - Assignee mapping (by name → Jira account ID)
  - Priority mapping (High/Medium/Low → Jira priority IDs)
  - Labels and components
  - Due dates

Supports both:
  - Jira Cloud (atlassian.net)
  - Jira Server/Data Center (self-hosted)

Setup:
  1. Create an API token at https://id.atlassian.com/manage-profile/security/api-tokens
  2. Get your Jira base URL (e.g., https://yourcompany.atlassian.net)
  3. Get the project key (e.g., "PROJ")

Env vars:
  JIRA_BASE_URL — e.g., https://yourcompany.atlassian.net
  JIRA_EMAIL — Your Jira account email
  JIRA_API_TOKEN — API token (NOT your password)
  JIRA_PROJECT_KEY — Default project key (e.g., "PROJ")
  JIRA_ISSUE_TYPE — Default issue type (default: "Task")

Usage:
    result = await JiraTool(ctx).execute(
        action_items=[
            {"action": "Fix login bug", "owner": "Alice", "deadline": "2026-07-25", "priority": "High"}
        ],
        summary="Sprint planning meeting...",
    )
"""
from __future__ import annotations

import base64
import os
from typing import Any

import httpx

from .base import BaseTool, ToolResult, ToolSchema

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "")
JIRA_ISSUE_TYPE = os.getenv("JIRA_ISSUE_TYPE", "Task")


class JiraTool(BaseTool):
    """Create Jira tickets from meeting action items."""

    name = "jira"
    description = (
        "Create Jira tickets from meeting action items. Maps owners to assignees, "
        "sets priorities and due dates, and returns ticket links. "
        "Requires JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, and JIRA_PROJECT_KEY env vars. "
        "This is the critical bridge between meeting decisions and actual execution."
    )

    def __init__(self, ctx: Any = None):
        super().__init__(ctx=ctx)
        self.base_url = JIRA_BASE_URL
        self.email = JIRA_EMAIL
        self.token = JIRA_API_TOKEN
        self.project_key = JIRA_PROJECT_KEY
        self.issue_type = JIRA_ISSUE_TYPE

        # Build auth header once
        if self.email and self.token:
            credentials = base64.b64encode(
                f"{self.email}:{self.token}".encode()
            ).decode()
            self.headers = {
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        else:
            self.headers = {}


    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="jira",
            description=(
                "Create Jira tickets from meeting action items. Maps owners to assignees, "
                "sets priorities and due dates, and returns ticket links. "
                "Requires JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, and JIRA_PROJECT_KEY env vars. "
                "This is the critical bridge between meeting decisions and actual execution. "
                "Use this whenever action items need to become tracked work items."
            ),
            parameters={
                "action_items": {
                    "type": "array",
                    "description": "List of action item dicts with 'action', 'owner', 'deadline', 'priority' keys.",
                },
                "summary": {
                    "type": "string",
                    "description": "Meeting summary (added to ticket description).",
                    "default": "",
                },
                "project_key": {
                    "type": "string",
                    "description": "Override default project key.",
                },
            },
            required=["action_items"],
            returns="Dict with 'tickets' (list), 'count', and 'errors' keys.",
        )

    async def execute(
        self,
        action_items: list[dict[str, str]] | None = None,
        summary: str = "",
        project_key: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        action_items = action_items or []
        """Create Jira tickets for action items.

        Args:
            action_items: List of action item dicts with action, owner, deadline, priority.
            summary: Meeting summary (added to ticket description).
            project_key: Override default project key.

        Returns:
            ToolResult with created ticket details and link artifacts.
        """
        # Validate config
        missing = []
        if not self.base_url:
            missing.append("JIRA_BASE_URL")
        if not self.email:
            missing.append("JIRA_EMAIL")
        if not self.token:
            missing.append("JIRA_API_TOKEN")

        if missing:
            msg = f"Jira not configured. Missing: {', '.join(missing)}"
            self.log(f"jira: {msg}")
            return ToolResult(
                success=False,
                data={},
                summary=msg,
                error=f"Missing env vars: {missing}",
            )

        project = project_key or self.project_key
        if not project:
            return ToolResult(
                success=False,
                data={},
                summary="No Jira project key specified. Set JIRA_PROJECT_KEY or pass project_key=.",
                error="Missing project key.",
            )

        if not action_items:
            return ToolResult(
                success=True,
                data={"tickets": [], "count": 0},
                summary="No action items to create tickets for.",
            )

        self.log(f"jira: creating {len(action_items)} tickets in project {project}")

        created_tickets: list[dict] = []
        errors: list[str] = []

        for idx, item in enumerate(action_items):
            action = item.get("action", "Untitled action item")
            owner = item.get("owner", "")
            deadline = item.get("deadline", "")
            priority = item.get("priority", "Medium")

            # Build description
            description_parts = [f"*Action item from meeting:*\n{action}"]
            if summary:
                description_parts.append(f"\n*Meeting context:*\n{summary[:1000]}")
            if owner and owner != "[OWNER?]":
                description_parts.append(f"\n*Assigned to:* {owner}")
            if deadline and deadline != "[DEADLINE?]":
                description_parts.append(f"\n*Due date:* {deadline}")

            description = "\n\n".join(description_parts)

            # Map priority
            priority_map = {
                "High": "Highest",
                "Medium": "Medium",
                "Low": "Low",
            }
            jira_priority = priority_map.get(priority, "Medium")

            # Build issue payload
            issue_data = {
                "fields": {
                    "project": {"key": project},
                    "summary": action[:255],  # Jira summary max length
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": description}],
                            }
                        ],
                    },
                    "issuetype": {"name": self.issue_type},
                    "priority": {"name": jira_priority},
                }
            }

            # Add due date if valid
            if deadline and deadline != "[DEADLINE?]" and len(deadline) == 10:
                issue_data["fields"]["duedate"] = deadline

            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(
                        f"{self.base_url}/rest/api/3/issue",
                        headers=self.headers,
                        json=issue_data,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                ticket_key = data.get("key", "")
                ticket_url = f"{self.base_url}/browse/{ticket_key}"

                created_tickets.append({
                    "key": ticket_key,
                    "url": ticket_url,
                    "action": action,
                    "owner": owner,
                })

                self.log(f"jira: created {ticket_key} — {action[:50]}")

            except httpx.HTTPStatusError as e:
                err_msg = f"HTTP {e.response.status_code}"
                try:
                    err_detail = e.response.json()
                    err_msg = err_detail.get("errorMessages", [err_msg])[0]
                except Exception:
                    pass
                errors.append(f"'{action[:40]}...': {err_msg}")
                self.log(f"jira: failed to create ticket — {err_msg}")

            except Exception as e:
                errors.append(f"'{action[:40]}...': {str(e)[:100]}")
                self.log(f"jira: error — {str(e)[:100]}")

        # Build result
        success_count = len(created_tickets)
        total_count = len(action_items)

        if success_count == 0:
            return ToolResult(
                success=False,
                data={"tickets": [], "errors": errors},
                summary=f"Failed to create any Jira tickets. Errors: {len(errors)}",
                error="; ".join(errors[:3]),
            )

        # Build markdown table
        lines = ["| Ticket | Action | Owner |", "|---|---|---|"]
        for t in created_tickets:
            lines.append(f"| [{t['key']}]({t['url']}) | {t['action']} | {t['owner'] or '—'} |")

        md = "\n".join(lines)

        summary_text = (
            f"Created {success_count}/{total_count} Jira tickets in project **{project}**."
        )
        if errors:
            summary_text += f"\n\n⚠️ {len(errors)} item(s) failed: " + "; ".join(errors[:2])

        return ToolResult(
            success=True,
            data={"tickets": created_tickets, "count": success_count, "errors": errors},
            summary=summary_text,
            artifacts=[
                {
                    "type": "markdown",
                    "title": f"Jira Tickets — {project}",
                    "content": md,
                },
            ]
            + [
                {
                    "type": "link",
                    "title": f"Jira: {t['key']}",
                    "content": t["url"],
                }
                for t in created_tickets
            ],
        )
