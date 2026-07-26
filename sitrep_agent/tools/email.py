"""
sitrep_agent/tools/email.py

Email drafting tool that produces personalized follow-up emails using meeting context.
This is a "smart template" tool — it uses the LLM to draft, but structures the prompt
for maximum quality and consistency.

Features:
  - Personalizes greeting using attendee names from the meeting
  - Adapts tone based on task description (formal, friendly, urgent)
  - Includes clear next steps and deadlines
  - Marks unknowns with [TODO] placeholders
  - Returns both markdown email and a plain-text version

Usage:
    result = await EmailTool(ctx).execute(
        task_title="Follow up with client",
        task_description="Send pricing details",
        summary="Meeting summary...",
        attendees=[{"name": "Alice"}, {"name": "Bob"}],
        research_context="Optional research to include"
    )
"""
from __future__ import annotations

from typing import Any

from .base import BaseTool, ToolResult, ToolSchema


class EmailTool(BaseTool):
    """Draft personalized follow-up emails from meeting context."""

    name = "email"
    description = (
        "Draft a professional, personalized follow-up email based on meeting context. "
        "Uses attendee names for personalization, includes clear next steps, and never "
        "invents facts not present in the meeting summary. Use this for any task that "
        "involves sending an email, following up with stakeholders, or communicating "
        "decisions to the team."
    )


    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="email",
            description=(
                "Draft a professional, personalized follow-up email based on meeting context. "
                "Uses attendee names for personalization, includes clear next steps, and never "
                "invents facts not present in the meeting summary. Use this for any task that "
                "involves sending an email, following up with stakeholders, or communicating "
                "decisions to the team."
            ),
            parameters={
                "task_title": {
                    "type": "string",
                    "description": "The action item title.",
                },
                "task_description": {
                    "type": "string",
                    "description": "Additional task details.",
                    "default": "",
                },
                "summary": {
                    "type": "string",
                    "description": "Meeting summary text.",
                },
                "attendees": {
                    "type": "array",
                    "description": "List of attendee dicts with 'name' key.",
                },
                "research_context": {
                    "type": "string",
                    "description": "Optional research to weave into the email.",
                    "default": "",
                },
                "tone": {
                    "type": "string",
                    "description": "Email tone: professional, friendly, formal, or urgent (default professional).",
                    "default": "professional",
                },
            },
            required=["task_title", "summary", "attendees"],
            returns="Dict with 'subject', 'body', 'recipients', and 'greeting' keys.",
        )

    async def execute(
        self,
        task_title: str = "",
        task_description: str = "",
        summary: str = "",
        attendees: list[dict[str, Any]] | None = None,
        research_context: str = "",
        tone: str = "professional",
        llm: Any = None,
        **kwargs: Any,
    ) -> ToolResult:
        task_title = task_title or kwargs.get("title") or "Follow-up"
        """Draft a follow-up email.

        Args:
            task_title: The action item title.
            task_description: Additional task details.
            summary: Meeting summary text.
            attendees: List of attendee dicts with "name" key.
            research_context: Optional research to weave into the email.
            tone: Email tone — "professional", "friendly", "formal", "urgent".
            llm: The LLM instance from ctx.llm (required).

        Returns:
            ToolResult with {"subject": str, "body": str, "recipients": str} in .data
        """
        self.log("email: drafting personalized follow-up email")

        if not llm:
            return ToolResult(
                success=False,
                data={},
                summary="Email tool requires an LLM instance.",
                error="Missing llm parameter.",
            )

        # Build recipient list
        names = [a.get("name") for a in (attendees or []) if a.get("name")]
        if len(names) == 1:
            recipients = names[0]
            greeting = f"Hi {names[0]},"
        elif len(names) == 2:
            recipients = f"{names[0]} and {names[1]}"
            greeting = f"Hi {names[0]} and {names[1]},"
        elif len(names) > 2:
            recipients = ", ".join(names[:-1]) + f", and {names[-1]}"
            greeting = f"Hi everyone,"
        else:
            recipients = "the team"
            greeting = "Hi team,"

        # Build the prompt
        system = (
            f"You are an executive assistant writing a {tone} follow-up email. "
            f"Write a concise, well-structured email that:\n"
            f"1. Opens with the provided greeting\n"
            f"2. Thanks attendees for the meeting\n"
            f"3. Recaps key decisions and next steps\n"
            f"4. Includes a clear subject line at the very top (format: **Subject:** ...)\n"
            f"5. Uses [TODO: confirm ...] for anything uncertain\n"
            f"6. Ends with a professional sign-off\n\n"
            f"Do not invent facts. Keep it under 250 words."
        )

        user_parts = [
            f"Greeting to use: {greeting}",
            f"Task: {task_title}",
        ]
        if task_description:
            user_parts.append(f"Details: {task_description}")
        user_parts.append(f"Meeting summary:\n{summary}")

        if research_context:
            user_parts.append(f"\nAdditional context to reference:\n{research_context}")

        user = "\n\n".join(user_parts)

        try:
            draft = await llm.complete(system=system, prompt=user, temperature=0.6)

            self.log(f"email: drafted ({len(draft)} chars) to {recipients}")

            return ToolResult(
                success=True,
                data={
                    "subject": self._extract_subject(draft),
                    "body": draft,
                    "recipients": recipients,
                    "greeting": greeting,
                },
                summary=f"Follow-up email drafted for {recipients}.",
                artifacts=[
                    {"type": "markdown", "title": f"{task_title} — Email", "content": draft},
                ],
            )

        except Exception as e:
            self.log(f"email: LLM error — {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary="Email drafting failed.",
                error=str(e),
            )

    def _extract_subject(self, draft: str) -> str:
        """Extract subject line from drafted email."""
        lines = draft.splitlines()
        for line in lines[:5]:
            line = line.strip()
            if line.lower().startswith("subject:") or line.lower().startswith("**subject:**"):
                return line.split(":", 1)[-1].strip().strip("*")
        return "Follow-up"
