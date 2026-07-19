"""
sitrep_agent/tools/calendar.py

Google Calendar link generator — creates one-click "Add to Calendar" URLs.
No API key or OAuth required — uses Google Calendar's public template URL.

Features:
  - Generates Google Calendar event template links
  - Auto-formats dates and times
  - Includes meeting title, details, and attendees
  - Returns both the link and a markdown-formatted invitation
  - Zero authentication needed

Usage:
    result = await CalendarTool(ctx).execute(
        title="Q3 Planning Follow-up",
        details="Discuss roadmap priorities...",
        duration_minutes=60
    )
    # result.data = {"url": "https://calendar.google.com/...", "markdown": "..."}
"""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta
from typing import Any

from .base import BaseTool, ToolResult

GOOGLE_CALENDAR_BASE = "https://calendar.google.com/calendar/render"


class CalendarTool(BaseTool):
    """Generate Google Calendar 'add event' template links."""

    name = "calendar"
    description = (
        "Generate a one-click Google Calendar event link for scheduling follow-up meetings. "
        "No Google account or API key required — the link opens Google Calendar with pre-filled "
        "event details that the recipient can save. Use this whenever a meeting task involves "
        "scheduling a follow-up, setting a deadline, or planning a recurring check-in."
    )

    async def execute(
        self,
        title: str,
        details: str = "",
        duration_minutes: int = 60,
        start_time: str | None = None,
        attendees: list[str] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Generate a Google Calendar event link.

        Args:
            title: Event title.
            details: Event description/body.
            duration_minutes: Meeting duration in minutes (default 60).
            start_time: ISO-format start time, or None for "tomorrow 9am".
            attendees: List of email addresses to pre-populate.

        Returns:
            ToolResult with {"url": str, "markdown": str, "title": str} in .data
        """
        self.log(f"calendar: generating link for \"{title[:50]}...\"")

        if not title:
            return ToolResult(
                success=False,
                data={},
                summary="Event title is required.",
                error="Missing event title.",
            )

        # Determine start/end times
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                start_dt = datetime.now() + timedelta(days=1)
                start_dt = start_dt.replace(hour=9, minute=0, second=0, microsecond=0)
        else:
            # Default: tomorrow at 9:00 AM local time
            start_dt = datetime.now() + timedelta(days=1)
            start_dt = start_dt.replace(hour=9, minute=0, second=0, microsecond=0)

        end_dt = start_dt + timedelta(minutes=duration_minutes)

        # Google Calendar uses UTC format: YYYYMMDDTHHMMSSZ
        def fmt(dt: datetime) -> str:
            return dt.strftime("%Y%m%dT%H%M%SZ")

        params: dict[str, str] = {
            "action": "TEMPLATE",
            "text": title,
            "details": details,
            "dates": f"{fmt(start_dt)}/{fmt(end_dt)}",
        }

        if attendees:
            params["add"] = ",".join(attendees)

        url = GOOGLE_CALENDAR_BASE + "?" + urllib.parse.urlencode(params)

        # Build a nice markdown snippet
        time_str = start_dt.strftime("%A, %B %d at %I:%M %p")
        md = (
            f"### 📅 Follow-up Meeting: {title}\n\n"
            f"**Proposed Time:** {time_str} ({duration_minutes} min)\n\n"
            f"**Details:**\n{details}\n\n"
            f"[➕ Add to Google Calendar]({url})"
        )

        self.log(f"calendar: link generated ({len(url)} chars)")

        return ToolResult(
            success=True,
            data={"url": url, "markdown": md, "title": title},
            summary=f"Google Calendar link created for \"{title}\" on {time_str}.",
            artifacts=[
                {"type": "link", "title": f"Add to Calendar: {title}", "content": url},
            ],
        )
