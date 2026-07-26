"""
sitrep_agent/tools/slack.py

Slack integration for posting meeting outcomes to channels.

Supports two authentication modes:
  1. Webhook URL (simplest — just a URL, no token management)
  2. Bot Token (more powerful — can post to any channel, thread, DM)

Features:
  - Posts meeting summaries to a channel
  - Posts action items as a formatted Slack message
  - Supports threading (replies to a parent message)
  - Graceful fallback if Slack is not configured

Setup:
  1. Create a Slack app at https://api.slack.com/apps
  2. Add "chat:write" scope (for bot token) or create an Incoming Webhook
  3. Copy the token/webhook URL to env vars

Env vars:
  SLACK_WEBHOOK_URL — Incoming webhook URL (preferred for simple setups)
  SLACK_BOT_TOKEN — xoxb-... bot token (for advanced use)
  SLACK_CHANNEL — Default channel ID or name (e.g., #general or C123456)

Usage:
    result = await SlackTool(ctx).execute(
        text="Meeting summary...",
        blocks=[...],  # optional rich blocks
        channel="#general"
    )
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from .base import BaseTool, ToolResult, ToolSchema

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "")

SLACK_API_BASE = "https://slack.com/api"


class SlackTool(BaseTool):
    """Post messages to Slack channels."""

    name = "slack"
    description = (
        "Post meeting summaries, action items, and follow-ups to a Slack channel. "
        "Use this to distribute meeting outcomes to the team in real-time. "
        "Requires SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN env var."
    )

    def __init__(self, ctx: Any = None):
        super().__init__(ctx=ctx)
        self.webhook_url = SLACK_WEBHOOK_URL
        self.bot_token = SLACK_BOT_TOKEN
        self.default_channel = SLACK_CHANNEL


    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="slack",
            description=(
                "Post meeting summaries, action items, and follow-ups to a Slack channel. "
                "Use this to distribute meeting outcomes to the team in real-time. "
                "Requires SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN env var. "
                "Use this when you want to notify the team about meeting outcomes."
            ),
            parameters={
                "text": {
                    "type": "string",
                    "description": "Plain text message (fallback for notifications).",
                },
                "channel": {
                    "type": "string",
                    "description": "Channel ID or name (e.g., '#general' or 'C123456'). Defaults to SLACK_CHANNEL env var.",
                },
                "blocks": {
                    "type": "array",
                    "description": "Optional Slack Block Kit blocks for rich formatting.",
                },
                "thread_ts": {
                    "type": "string",
                    "description": "Optional thread timestamp to reply in a thread.",
                },
            },
            required=["text"],
            returns="Dict with 'channel', 'ts', and 'permalink' keys.",
        )

    async def execute(
        self,
        text: str = "",
        channel: str | None = None,
        blocks: list[dict] | None = None,
        thread_ts: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Post a message to Slack.

        Args:
            text: Plain text message (fallback for notifications).
            channel: Channel ID or name (e.g., "#general" or "C123456").
                     Defaults to SLACK_CHANNEL env var.
            blocks: Optional Slack Block Kit blocks for rich formatting.
            thread_ts: Optional thread timestamp to reply in a thread.

        Returns:
            ToolResult with message details and a link artifact.
        """
        # Check configuration
        if not self.webhook_url and not self.bot_token:
            self.log("slack: not configured — no webhook or bot token")
            return ToolResult(
                success=False,
                data={},
                summary="Slack is not configured. Set SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN.",
                error="Missing Slack credentials.",
            )

        target_channel = channel or self.default_channel
        if not target_channel and self.bot_token:
            return ToolResult(
                success=False,
                data={},
                summary="No Slack channel specified. Set SLACK_CHANNEL or pass channel=.",
                error="Missing channel.",
            )

        self.log(f"slack: posting to {target_channel or 'webhook'}")

        try:
            if self.webhook_url:
                # Webhook mode — simple POST
                payload = {"text": text}
                if blocks:
                    payload["blocks"] = blocks

                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(self.webhook_url, json=payload)
                    resp.raise_for_status()

                self.log("slack: message posted via webhook")
                return ToolResult(
                    success=True,
                    data={"method": "webhook", "channel": target_channel},
                    summary=f"Message posted to Slack via webhook.",
                    artifacts=[
                        {
                            "type": "markdown",
                            "title": "Slack Notification Sent",
                            "content": f"✅ Posted to Slack channel `{target_channel or 'webhook'}`\n\n{text[:500]}",
                        },
                    ],
                )

            else:
                # Bot token mode — use Slack Web API
                headers = {
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json",
                }
                payload: dict[str, Any] = {
                    "channel": target_channel,
                    "text": text,
                    "unfurl_links": False,
                }
                if blocks:
                    payload["blocks"] = blocks
                if thread_ts:
                    payload["thread_ts"] = thread_ts

                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        f"{SLACK_API_BASE}/chat.postMessage",
                        headers=headers,
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                if not data.get("ok"):
                    error = data.get("error", "unknown")
                    self.log(f"slack: API error — {error}")
                    return ToolResult(
                        success=False,
                        data={},
                        summary=f"Slack API error: {error}",
                        error=error,
                    )

                msg_ts = data.get("ts", "")
                permalink = data.get("permalink", "")

                self.log(f"slack: message posted to {target_channel} (ts={msg_ts})")

                return ToolResult(
                    success=True,
                    data={
                        "channel": target_channel,
                        "ts": msg_ts,
                        "permalink": permalink,
                    },
                    summary=f"Message posted to Slack #{target_channel}.",
                    artifacts=[
                        {
                            "type": "markdown",
                            "title": "Slack Notification Sent",
                            "content": (
                                f"✅ Posted to **#{target_channel}**\n\n"
                                f"{text[:500]}"
                                + (f"\n\n[View in Slack]({permalink})" if permalink else "")
                            ),
                        },
                    ],
                )

        except httpx.HTTPError as e:
            self.log(f"slack: HTTP error — {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary="Failed to post to Slack (network error).",
                error=str(e),
            )
        except Exception as e:
            self.log(f"slack: error — {type(e).__name__}: {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary="Slack posting failed.",
                error=str(e),
            )

    def build_action_items_blocks(
        self, title: str, action_items: list[dict[str, str]]
    ) -> list[dict]:
        """Build Slack Block Kit blocks for action items.

        Args:
            title: Meeting title.
            action_items: List of action item dicts.

        Returns:
            Slack Block Kit blocks list.
        """
        blocks: list[dict] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📋 Action Items: {title}",
                    "emoji": True,
                },
            },
            {"type": "divider"},
        ]

        for item in action_items:
            owner = item.get("owner", "[OWNER?]")
            deadline = item.get("deadline", "[DEADLINE?]")
            priority = item.get("priority", "Medium")
            action = item.get("action", "")

            priority_emoji = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(priority, "⚪")

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{priority_emoji} *{action}*\n"
                        f"> 👤 Owner: {owner} | 📅 Deadline: {deadline}"
                    ),
                },
            })

        return blocks
