"""Example CODE agent: an agenda plus a one-click "Add to Calendar" link.

Copy this over handler.py to use it (keep the function name `handler`). Shows how
to return a `link` artifact — its content must be a URL — alongside markdown. The
Google Calendar template URL needs no credentials.
"""
from __future__ import annotations

import urllib.parse

from sitrep_agent.sdk import AgentInput, Ctx

CALENDAR_BASE = "https://calendar.google.com/calendar/render"


def calendar_url(title: str, details: str) -> str:
    """Build a Google Calendar 'add event' template URL (no auth required)."""
    params = {"action": "TEMPLATE", "text": title, "details": details}
    return CALENDAR_BASE + "?" + urllib.parse.urlencode(params)


async def handler(input: AgentInput, ctx: Ctx) -> dict:
    title = input.task.get("title") or "Meeting follow-up"

    # Draft a short agenda for the follow-up event.
    agenda = await ctx.llm.complete(
        system="You are a meeting planner. Draft a focused agenda (3-5 bullet "
        "items) for a follow-up meeting on the task below. Keep it under 120 words.",
        prompt=f"Task: {title}\n\nMeeting summary:\n{input.summary}",
    )

    ctx.log("building calendar link")
    url = calendar_url(f"Follow-up: {title}", agenda)

    return {
        "artifacts": [
            {"type": "markdown", "title": f"{title} — agenda", "content": agenda},
            {"type": "link", "title": "Add to Google Calendar", "content": url},
        ]
    }
