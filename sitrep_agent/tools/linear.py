"""
sitrep_agent/tools/linear.py

Linear Issue Creator tool using the Linear GraphQL API (https://api.linear.app/graphql).

Transforms meeting action items into Linear issues with:
  - Issue title & description
  - Team assignment
  - Priority (0=No priority, 1=Urgent, 2=High, 3=Medium, 4=Low)
  - Due date

Setup & Env Vars:
  LINEAR_API_KEY — Personal access token (lin_api_...)
  LINEAR_TEAM_ID — Linear Team ID or Team Key (e.g. ENG or team UUID)

Usage:
    result = await LinearTool(ctx).execute(
        action_items=[
            {"action": "Build auth flow", "owner": "Alice", "deadline": "2026-08-01", "priority": "High"}
        ],
        summary="Sprint planning meeting...",
    )
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from .base import BaseTool, ToolResult, ToolSchema

LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")
LINEAR_TEAM_ID = os.getenv("LINEAR_TEAM_ID", "")

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"


class LinearTool(BaseTool):
    """Create Linear issues from meeting action items via GraphQL."""

    name = "linear"
    description = (
        "Create issues in Linear from meeting action items. "
        "Modern engineering and product teams use Linear for task tracking. "
        "Requires LINEAR_API_KEY and LINEAR_TEAM_ID env vars."
    )

    def __init__(self, ctx: Any = None):
        super().__init__(ctx=ctx)
        self.api_key = LINEAR_API_KEY
        self.team_id = LINEAR_TEAM_ID
        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="linear",
            description=(
                "Create issues in Linear from meeting action items. "
                "Maps action items to Linear issues, sets priorities and due dates, "
                "and returns issue links. Requires LINEAR_API_KEY and LINEAR_TEAM_ID env vars."
            ),
            parameters={
                "action_items": {
                    "type": "array",
                    "description": "List of action item dicts with 'action' (or 'title'), 'owner', 'deadline', 'priority'.",
                },
                "summary": {
                    "type": "string",
                    "description": "Meeting summary to include in issue description.",
                    "default": "",
                },
                "team_id": {
                    "type": "string",
                    "description": "Override target Linear team ID or key.",
                },
            },
            required=["action_items"],
            returns="Dict with created 'issues' list, 'count', and 'errors' keys.",
        )

    async def execute(
        self,
        action_items: list[dict[str, Any]] | None = None,
        summary: str = "",
        team_id: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Create Linear issues for action items.

        Args:
            action_items: List of action item dicts.
            summary: Meeting summary.
            team_id: Override target team ID.

        Returns:
            ToolResult with created Linear issue identifiers and link artifacts.
        """
        if not self.api_key:
            msg = "Linear tool not configured. Set LINEAR_API_KEY in .env."
            self.log(f"linear: {msg}")
            return ToolResult(
                success=False,
                data={},
                summary=msg,
                error="Missing LINEAR_API_KEY env var.",
            )

        target_team = team_id or self.team_id
        if not target_team:
            msg = "No Linear team ID specified. Set LINEAR_TEAM_ID in .env or pass team_id=."
            self.log(f"linear: {msg}")
            return ToolResult(
                success=False,
                data={},
                summary=msg,
                error="Missing LINEAR_TEAM_ID env var.",
            )

        action_items = action_items or kwargs.get("items", [])
        if not action_items:
            return ToolResult(
                success=True,
                data={"issues": [], "count": 0},
                summary="No action items provided to create Linear issues for.",
            )

        self.log(f"linear: resolving team and creating {len(action_items)} issue(s)")

        # Resolve team ID if a team key (e.g., "ENG") was provided
        real_team_id = await self._resolve_team_id(target_team)
        if not real_team_id:
            return ToolResult(
                success=False,
                data={},
                summary=f"Could not resolve Linear team ID for '{target_team}'.",
                error=f"Invalid team ID/key: {target_team}",
            )

        created_issues: list[dict[str, str]] = []
        errors: list[str] = []

        mutation = """
        mutation IssueCreate($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                }
            }
        }
        """

        for item in action_items:
            action = item.get("action") or item.get("title") or "Untitled Action Item"
            owner = item.get("owner", "")
            deadline = item.get("deadline", "")
            priority_str = item.get("priority", "Medium")

            # Map priority (Linear: 0=No priority, 1=Urgent, 2=High, 3=Medium, 4=Low)
            priority_map = {
                "Urgent": 1,
                "High": 2,
                "Medium": 3,
                "Low": 4,
            }
            linear_priority = priority_map.get(priority_str, 3)

            # Build markdown description
            desc_parts = [f"**Action item from meeting:**\n{action}"]
            if summary:
                desc_parts.append(f"\n**Meeting Summary:**\n{summary[:1000]}")
            if owner and owner != "[OWNER?]":
                desc_parts.append(f"\n**Owner:** {owner}")
            if deadline and deadline != "[DEADLINE?]":
                desc_parts.append(f"\n**Deadline:** {deadline}")

            description = "\n\n".join(desc_parts)

            input_payload: dict[str, Any] = {
                "teamId": real_team_id,
                "title": action[:255],
                "description": description,
                "priority": linear_priority,
            }

            if deadline and deadline != "[DEADLINE?]" and len(deadline) == 10:
                input_payload["dueDate"] = deadline

            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(
                        LINEAR_GRAPHQL_URL,
                        headers=self.headers,
                        json={"query": mutation, "variables": {"input": input_payload}},
                    )
                    resp.raise_for_status()
                    res_json = resp.json()

                if res_json.get("errors"):
                    err_msg = res_json["errors"][0].get("message", "GraphQL error")
                    errors.append(f"'{action[:30]}...': {err_msg}")
                    self.log(f"linear: GraphQL error — {err_msg}")
                    continue

                data = res_json.get("data", {}).get("issueCreate", {})
                if not data.get("success") or not data.get("issue"):
                    errors.append(f"'{action[:30]}...': issue creation returned false")
                    continue

                issue = data["issue"]
                identifier = issue.get("identifier", "")
                url = issue.get("url", "")
                title = issue.get("title", action)

                created_issues.append({
                    "identifier": identifier,
                    "url": url,
                    "title": title,
                    "owner": owner,
                })
                self.log(f"linear: created {identifier} — {title[:40]}")

            except Exception as e:
                errors.append(f"'{action[:30]}...': {str(e)[:80]}")
                self.log(f"linear: error creating issue — {str(e)[:80]}")

        success_count = len(created_issues)
        total_count = len(action_items)

        if success_count == 0:
            return ToolResult(
                success=False,
                data={"issues": [], "errors": errors},
                summary=f"Failed to create any Linear issues. Errors: {len(errors)}",
                error="; ".join(errors[:2]),
            )

        # Build markdown summary table
        lines = ["| Issue | Action | Owner |", "|---|---|---|"]
        for issue in created_issues:
            lines.append(f"| [{issue['identifier']}]({issue['url']}) | {issue['title']} | {issue['owner'] or '—'} |")

        md = "\n".join(lines)
        summary_text = f"Created {success_count}/{total_count} Linear issue(s)."
        if errors:
            summary_text += f"\n\n⚠️ {len(errors)} item(s) failed: " + "; ".join(errors[:2])

        return ToolResult(
            success=True,
            data={"issues": created_issues, "count": success_count, "errors": errors},
            summary=summary_text,
            artifacts=[
                {
                    "type": "markdown",
                    "title": "Linear Issues Created",
                    "content": md,
                }
            ]
            + [
                {
                    "type": "link",
                    "title": f"Linear: {issue['identifier']}",
                    "content": issue["url"],
                }
                for issue in created_issues
            ],
        )

    async def _resolve_team_id(self, team_key_or_id: str) -> str:
        """Resolve a team key (e.g. 'ENG') or ID to a Linear team UUID."""
        # If it looks like a UUID (36 chars with dashes), return as is
        if len(team_key_or_id) == 36 and "-" in team_key_or_id:
            return team_key_or_id

        query = """
        query Teams {
            teams {
                nodes {
                    id
                    key
                    name
                }
            }
        }
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    LINEAR_GRAPHQL_URL,
                    headers=self.headers,
                    json={"query": query},
                )
                resp.raise_for_status()
                data = resp.json()

            nodes = data.get("data", {}).get("teams", {}).get("nodes", [])
            for node in nodes:
                if node.get("key", "").upper() == team_key_or_id.upper() or node.get("id") == team_key_or_id:
                    return node.get("id", "")
                if node.get("name", "").lower() == team_key_or_id.lower():
                    return node.get("id", "")

            # If no match found, fallback to first team node ID
            if nodes:
                return nodes[0].get("id", "")

        except Exception as e:
            self.log(f"linear: failed to query teams — {str(e)[:80]}")

        return team_key_or_id
