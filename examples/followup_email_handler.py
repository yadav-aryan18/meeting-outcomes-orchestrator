"""Example CODE agent: drafts a follow-up email to the meeting attendees.

Copy this over handler.py to use it (keep the function name `handler`). Shows how
to use `input.attendees` to personalize the output with a single LLM call.
"""
from __future__ import annotations

from sitrep_agent.sdk import AgentInput, Ctx


async def handler(input: AgentInput, ctx: Ctx) -> dict:
    task = input.task
    title = task.get("title") or "Follow-up"

    # Pull attendee names off the input so the email can address them.
    names = [a.get("name") for a in input.attendees if a.get("name")]
    recipients = ", ".join(names) if names else "the team"
    ctx.log(f"drafting email to {len(names)} attendee(s)")

    user = (
        f"Action item: {title}\n"
        f"{('Details: ' + task['description']) if task.get('description') else ''}\n"
        f"Recipients: {recipients}\n\n"
        f"Meeting summary:\n{input.summary}"
    )

    email = await ctx.llm.complete(
        system="You are an executive assistant. Write a concise, friendly follow-up "
        "email that recaps the relevant decisions and states clear next steps. "
        "Address the recipients by name in the greeting. Include a subject line. "
        "Don't invent facts not in the summary — use [TODO: confirm ...] instead.",
        prompt=user,
    )

    return {
        "artifacts": [
            {"type": "markdown", "title": f"{title} — email", "content": email},
        ]
    }
