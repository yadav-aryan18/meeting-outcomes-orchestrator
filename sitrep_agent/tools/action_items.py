"""
sitrep_agent/tools/action_items.py

Extracts structured action items from meeting summaries with owners, deadlines,
and priorities. This is one of the highest-impact post-meeting automations.

Features:
  - Identifies who owns each action item from attendee names
  - Suggests deadlines based on context (e.g., "next week", "by Friday")
  - Assigns priority (High/Medium/Low) based on urgency language
  - Outputs a structured table and a project-plan-style markdown list
  - Never invents owners — flags unclear assignments with [OWNER?]

Usage:
    result = await ActionItemsTool(ctx).execute(
        task_title="Q3 Sprint Planning",
        summary="Meeting summary...",
        attendees=[{"name": "Alice"}, {"name": "Bob"}],
        llm=ctx.llm
    )
"""
from __future__ import annotations

from typing import Any

from .base import BaseTool, ToolResult


class ActionItemsTool(BaseTool):
    """Extract structured action items from meeting summaries."""

    name = "action_items"
    description = (
        "Extract structured action items from a meeting summary, including owners, "
        "deadlines, and priorities. This is the highest-impact post-meeting automation — "
        "most teams fail to execute on decisions because action items aren't captured. "
        "Use this for sprint planning, project kickoffs, quarterly reviews, or any "
        "meeting where decisions and next steps were discussed."
    )

    async def execute(
        self,
        task_title: str,
        summary: str = "",
        attendees: list[dict[str, Any]] | None = None,
        llm: Any = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Extract structured action items.

        Args:
            task_title: The meeting task title.
            summary: Meeting summary text.
            attendees: List of attendee dicts with "name" key.
            llm: The LLM instance from ctx.llm (required).

        Returns:
            ToolResult with structured action items in .data
        """
        self.log("action_items: extracting structured tasks from summary")

        if not llm:
            return ToolResult(
                success=False,
                data={},
                summary="Action items tool requires an LLM instance.",
                error="Missing llm parameter.",
            )

        # Build attendee context
        names = [a.get("name") for a in (attendees or []) if a.get("name")]
        attendee_context = f"Attendees: {', '.join(names)}" if names else "Attendees: unknown"

        system = (
            "You are a project manager extracting action items from a meeting. "
            "Analyze the meeting summary and produce a structured list of action items.\n\n"
            "For EACH action item, provide:\n"
            "1. **Action**: Clear, specific task (1 sentence)\n"
            "2. **Owner**: The person responsible. Use [OWNER?] if unclear.\n"
            "3. **Deadline**: Specific date or relative time. Use [DEADLINE?] if unclear.\n"
            "4. **Priority**: High / Medium / Low based on urgency in the summary\n"
            "5. **Status**: Not started\n\n"
            "Format as a markdown table with columns: # | Action | Owner | Deadline | Priority\n\n"
            "Then, below the table, provide:\n"
            "- A brief 'Risk Assessment' paragraph highlighting any unclear owners or tight deadlines\n"
            "- A 'Dependencies' list if any tasks depend on others\n\n"
            "Rules:\n"
            "- Do NOT invent owners not mentioned in the summary\n"
            "- Do NOT invent deadlines not implied by the summary\n"
            "- If a task has no clear owner, flag it with [OWNER?]\n"
            "- If a task has no clear deadline, flag it with [DEADLINE?]\n"
            "- Be exhaustive — capture every decision that requires follow-up"
        )

        user = (
            f"Meeting: {task_title}\n"
            f"{attendee_context}\n\n"
            f"Meeting summary:\n{summary}"
        )

        try:
            extraction = await llm.complete(system=system, prompt=user, temperature=0.3)

            self.log(f"action_items: extracted ({len(extraction)} chars)")

            # Parse the table to structured data (best-effort)
            items = self._parse_action_items(extraction)

            return ToolResult(
                success=True,
                data={
                    "raw_markdown": extraction,
                    "items": items,
                    "count": len(items),
                },
                summary=f"Extracted {len(items)} action items from meeting.",
                artifacts=[
                    {
                        "type": "markdown",
                        "title": f"{task_title} — Action Items",
                        "content": extraction,
                    },
                ],
            )

        except Exception as e:
            self.log(f"action_items: error — {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary="Action item extraction failed.",
                error=str(e),
            )

    def _parse_action_items(self, markdown: str) -> list[dict[str, str]]:
        """Best-effort parser to extract structured data from markdown table."""
        items = []
        lines = markdown.splitlines()
        for line in lines:
            line = line.strip()
            # Look for table rows starting with | and a number
            if line.startswith("|") and len(line.split("|")) >= 5:
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) >= 4 and parts[0] and parts[0][0].isdigit():
                    items.append({
                        "id": parts[0],
                        "action": parts[1],
                        "owner": parts[2],
                        "deadline": parts[3],
                        "priority": parts[4] if len(parts) > 4 else "Medium",
                    })
        return items
