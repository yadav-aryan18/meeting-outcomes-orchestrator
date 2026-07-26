"""
sitrep_agent/tools/memory.py

Memory tool for the Meeting Outcomes Orchestrator.

Wraps the SQLite database (sitrep_agent/database.py) to provide:
  - Meeting persistence
  - Action item tracking
  - Historical context retrieval for LLM prompts
  - Attendee profile building

This tool is special: it runs automatically in the background for EVERY task,
not just when explicitly triggered. The orchestrator calls it to store the
meeting and retrieve context before processing.

Usage (automatic, from handler.py):
    memory_tool = MemoryTool(ctx=ctx)
    await memory_tool.store_meeting(input)
    context = await memory_tool.get_context(input)

Usage (explicit, for queries):
    result = await MemoryTool(ctx).execute(
        operation="get_open_items",
        owner="Alice"
    )
"""
from __future__ import annotations

from typing import Any

from sitrep_agent.database import AgentDatabase

from .base import BaseTool, ToolResult, ToolSchema


class MemoryTool(BaseTool):
    """Persistent memory for meetings, action items, and attendee context."""

    name = "memory"
    description = (
        "Store and retrieve meeting history, action items, and attendee context. "
        "This tool runs automatically for every meeting to build a persistent memory. "
        "It enables the agent to answer questions like 'What did Alice commit to last week?' "
        "and 'Which action items from our last 3 meetings are still open?'"
    )

    def __init__(self, ctx: Any = None):
        super().__init__(ctx=ctx)
        self.db = AgentDatabase()


    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="memory",
            description=(
                "Store and retrieve meeting history, action items, and attendee context. "
                "This tool runs automatically but can also be called explicitly to query "
                "past meetings or open action items. Use this when you need historical context "
                "about a person, project, or previous meeting decisions."
            ),
            parameters={
                "operation": {
                    "type": "string",
                    "description": "One of: store, get_context, get_open_items, get_recent_meetings.",
                },
                "input_data": {
                    "type": "object",
                    "description": "The data for the operation (AgentInput for store, dict for queries).",
                },
                "owner": {
                    "type": "string",
                    "description": "Filter action items by owner (for get_open_items).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (for get_recent_meetings).",
                    "default": 5,
                },
            },
            required=["operation"],
            returns="Dict with operation-specific results.",
        )

    async def execute(
        self,
        operation: str = "store",
        input_data: Any = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute a memory operation.

        Args:
            operation: One of: store, get_context, get_open_items, get_recent_meetings.
            input_data: The data for the operation (AgentInput for store, dict for queries).
            **kwargs: Additional params (owner, limit, etc.).

        Returns:
            ToolResult with the operation result.
        """
        if operation == "store":
            return await self._store_meeting(input_data, **kwargs)
        elif operation == "get_context":
            return await self._get_context(input_data)
        elif operation == "get_open_items":
            return await self._get_open_items(kwargs.get("owner"))
        elif operation == "get_recent_meetings":
            return await self._get_recent_meetings(kwargs.get("limit", 5))
        else:
            return ToolResult(
                success=False,
                data={},
                summary=f"Unknown memory operation: {operation}",
                error=f"Unknown operation: {operation}",
            )

    async def store_meeting(
        self,
        input_data: Any,
        action_items: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Convenience wrapper for the orchestrator to store a meeting."""
        return await self._store_meeting(input_data, action_items=action_items, **kwargs)

    async def get_context(self, input_data: Any) -> str:
        """Convenience wrapper for the orchestrator to get context. Returns raw string."""
        result = await self._get_context(input_data)
        return result.data.get("context", "") if result.success else ""

    # ── Internal Operations ─────────────────────────────────────────────

    async def _store_meeting(
        self,
        input_data: Any,
        action_items: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Store a meeting and its action items in the database."""
        if not input_data:
            return ToolResult(success=False, error="No input data provided.")

        task = input_data.task or {}
        meeting_id = task.get("id", "unknown")
        title = task.get("title", "Untitled")
        description = task.get("description", "")
        summary = input_data.summary or ""
        attendees = input_data.attendees or []

        items_to_store = action_items or kwargs.get("action_items", [])

        self.log(f"memory: storing meeting '{meeting_id}' — '{title[:50]}...'")

        success = await self.db.store_meeting(
            meeting_id=meeting_id,
            task_title=title,
            task_description=description,
            summary=summary,
            attendees=attendees,
            action_items=items_to_store,
        )

        if success:
            self.log(f"memory: meeting '{meeting_id}' stored successfully")
            return ToolResult(
                success=True,
                data={"meeting_id": meeting_id, "stored": True},
                summary=f"Meeting '{title}' stored in agent memory.",
            )
        else:
            self.log(f"memory: failed to store meeting '{meeting_id}'")
            return ToolResult(
                success=False,
                data={},
                summary="Failed to store meeting in memory.",
                error="Database write failed.",
            )

    async def _get_context(self, input_data: Any) -> ToolResult:
        """Retrieve historical context for the current meeting."""
        if not input_data:
            return ToolResult(success=True, data={"context": ""}, summary="No input data.")

        attendees = input_data.attendees or []
        task_title = (input_data.task or {}).get("title", "")

        self.log("memory: retrieving historical context")

        context = await self.db.get_context_for_task(task_title, attendees)

        if context:
            self.log(f"memory: retrieved {len(context)} chars of context")
            return ToolResult(
                success=True,
                data={"context": context},
                summary=f"Retrieved historical context ({len(context)} chars).",
            )
        else:
            self.log("memory: no historical context found")
            return ToolResult(
                success=True,
                data={"context": ""},
                summary="No historical context available (first meeting or DB empty).",
            )

    async def _get_open_items(self, owner: str | None = None) -> ToolResult:
        """Get open action items, optionally filtered by owner."""
        self.log(f"memory: retrieving open action items for {owner or 'all'}")

        if owner:
            items = await self.db.get_open_action_items_for_owner(owner)
        else:
            items = await self.db.get_open_action_items()

        if not items:
            return ToolResult(
                success=True,
                data={"items": [], "count": 0},
                summary=f"No open action items found for {owner or 'anyone'}.",
            )

        # Format as markdown table
        lines = ["| # | Action | Owner | Deadline | Priority |", "|---|---|---|---|---|"]
        for i, item in enumerate(items, 1):
            lines.append(
                f"| {i} | {item.action} | {item.owner} | {item.deadline} | {item.priority} |"
            )

        md = "\n".join(lines)

        return ToolResult(
            success=True,
            data={"items": [vars(i) for i in items], "count": len(items)},
            summary=f"Found {len(items)} open action items for {owner or 'all'}.",
            artifacts=[
                {
                    "type": "markdown",
                    "title": f"Open Action Items — {owner or 'All'}",
                    "content": md,
                },
            ],
        )

    async def _get_recent_meetings(self, limit: int = 5) -> ToolResult:
        """Get recent meetings."""
        self.log(f"memory: retrieving {limit} recent meetings")

        meetings = await self.db.get_recent_meetings(limit)

        if not meetings:
            return ToolResult(
                success=True,
                data={"meetings": [], "count": 0},
                summary="No meetings found in memory.",
            )

        lines = ["| # | Meeting | Date | Attendees |", "|---|---|---|---|"]
        for i, m in enumerate(meetings, 1):
            attendee_names = ", ".join(a.get("name", "") for a in m.attendees[:3])
            lines.append(f"| {i} | {m.task_title} | {m.created_at[:10]} | {attendee_names} |")

        md = "\n".join(lines)

        return ToolResult(
            success=True,
            data={"meetings": [vars(m) for m in meetings], "count": len(meetings)},
            summary=f"Retrieved {len(meetings)} recent meetings from memory.",
            artifacts=[
                {
                    "type": "markdown",
                    "title": "Recent Meetings",
                    "content": md,
                },
            ],
        )
