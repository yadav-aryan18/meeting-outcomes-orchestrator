"""
sitrep_agent/tools/email_sender.py

Sends drafted emails via Resend or SendGrid REST API.

Features:
  - Supports Resend API (https://api.resend.com/emails)
  - Supports SendGrid API v3 (https://api.sendgrid.com/v3/mail/send)
  - Accepts recipient(s), subject, text body, and optional HTML body
  - Returns message ID and delivery confirmation artifact
  - Graceful fallback when API keys are missing

Setup & Env Vars:
  RESEND_API_KEY — Resend API Key (e.g. re_...)
  SENDGRID_API_KEY — SendGrid API Key (e.g. SG....)
  SENDER_EMAIL — Sender address (e.g. notifications@company.com)
  SENDER_NAME — Sender display name (default: "SitRep Meeting Orchestrator")

Usage:
    result = await EmailSenderTool(ctx).execute(
        to_email="alice@example.com",
        subject="Follow-up: Sprint Planning",
        body="Hi Alice, here are the meeting notes...",
    )
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from .base import BaseTool, ToolResult, ToolSchema

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
SENDER_NAME = os.getenv("SENDER_NAME", "SitRep Meeting Orchestrator")

RESEND_API_URL = "https://api.resend.com/emails"
SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


class EmailSenderTool(BaseTool):
    """Send emails via Resend or SendGrid REST API."""

    name = "email_sender"
    description = (
        "Send emails via Resend or SendGrid REST APIs. "
        "Use this tool when you need to send actual email messages (not just draft them). "
        "Requires RESEND_API_KEY or SENDGRID_API_KEY, along with SENDER_EMAIL env var."
    )

    def __init__(self, ctx: Any = None):
        super().__init__(ctx=ctx)
        self.resend_key = RESEND_API_KEY
        self.sendgrid_key = SENDGRID_API_KEY
        self.sender_email = SENDER_EMAIL
        self.sender_name = SENDER_NAME

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="email_sender",
            description=(
                "Send actual emails to meeting participants or stakeholders. "
                "Supports Resend and SendGrid APIs. "
                "Use this after drafting an email when the task involves sending the message."
            ),
            parameters={
                "to_email": {
                    "type": "string",
                    "description": "Recipient email address or comma-separated list.",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line.",
                },
                "body": {
                    "type": "string",
                    "description": "Email plain-text body content.",
                },
                "html_body": {
                    "type": "string",
                    "description": "Optional HTML formatted email body.",
                    "default": "",
                },
            },
            required=["to_email", "subject", "body"],
            returns="Dict with 'success', 'provider', 'message_id', and 'recipients' keys.",
        )

    async def execute(
        self,
        to_email: str = "",
        subject: str = "",
        body: str = "",
        html_body: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        """Send email via Resend or SendGrid.

        Args:
            to_email: Recipient email address(es).
            subject: Email subject.
            body: Plain text body.
            html_body: Optional HTML body.

        Returns:
            ToolResult with delivery confirmation details.
        """
        to_email = to_email or kwargs.get("recipients") or ""
        subject = subject or kwargs.get("task_title") or "Meeting Follow-up"

        if not to_email:
            return ToolResult(
                success=False,
                data={},
                summary="Recipient email address is required.",
                error="Missing to_email parameter.",
            )

        if not body and not html_body:
            return ToolResult(
                success=False,
                data={},
                summary="Email body content is required.",
                error="Missing body parameter.",
            )

        # Check configuration
        if not self.resend_key and not self.sendgrid_key:
            msg = "Email Sender not configured. Set RESEND_API_KEY or SENDGRID_API_KEY in .env."
            self.log(f"email_sender: {msg}")
            return ToolResult(
                success=False,
                data={},
                summary=msg,
                error="Missing RESEND_API_KEY / SENDGRID_API_KEY",
            )

        if not self.sender_email:
            msg = "SENDER_EMAIL is required in .env for sending emails."
            self.log(f"email_sender: {msg}")
            return ToolResult(
                success=False,
                data={},
                summary=msg,
                error="Missing SENDER_EMAIL env var.",
            )

        # Parse recipient list
        recipients = [e.strip() for e in to_email.split(",") if e.strip() and "@" in e]
        if not recipients:
            return ToolResult(
                success=False,
                data={},
                summary=f"Invalid email address provided: {to_email}",
                error="No valid recipient emails.",
            )

        self.log(f"email_sender: sending email to {recipients} with subject \"{subject[:40]}...\"")

        # Try Resend first if key is present
        if self.resend_key:
            return await self._send_via_resend(recipients, subject, body, html_body)
        else:
            return await self._send_via_sendgrid(recipients, subject, body, html_body)

    async def _send_via_resend(
        self, recipients: list[str], subject: str, body: str, html_body: str
    ) -> ToolResult:
        """Send email using Resend REST API."""
        headers = {
            "Authorization": f"Bearer {self.resend_key}",
            "Content-Type": "application/json",
        }
        from_address = f"{self.sender_name} <{self.sender_email}>" if self.sender_name else self.sender_email

        payload: dict[str, Any] = {
            "from": from_address,
            "to": recipients,
            "subject": subject,
            "text": body,
        }
        if html_body:
            payload["html"] = html_body

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(RESEND_API_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

            message_id = data.get("id", "resend_ok")
            self.log(f"email_sender: sent via Resend (ID={message_id})")

            recipients_str = ", ".join(recipients)
            md = (
                f"✅ **Email Sent via Resend**\n\n"
                f"**To:** {recipients_str}\n"
                f"**Subject:** {subject}\n"
                f"**Message ID:** `{message_id}`\n\n"
                f"**Body Preview:**\n{body[:400]}"
            )

            return ToolResult(
                success=True,
                data={"provider": "resend", "message_id": message_id, "recipients": recipients},
                summary=f"Email sent via Resend to {recipients_str}.",
                artifacts=[
                    {
                        "type": "markdown",
                        "title": f"Email Sent: {subject}",
                        "content": md,
                    }
                ],
            )
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.json().get("message", "")
            except Exception:
                pass
            self.log(f"email_sender: Resend HTTP error {e.response.status_code} — {detail}")
            return ToolResult(
                success=False,
                data={},
                summary=f"Resend API error (HTTP {e.response.status_code}).",
                error=detail or str(e),
            )
        except Exception as e:
            self.log(f"email_sender: Resend error — {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary="Failed to send email via Resend.",
                error=str(e),
            )

    async def _send_via_sendgrid(
        self, recipients: list[str], subject: str, body: str, html_body: str
    ) -> ToolResult:
        """Send email using SendGrid v3 REST API."""
        headers = {
            "Authorization": f"Bearer {self.sendgrid_key}",
            "Content-Type": "application/json",
        }

        content_list = [{"type": "text/plain", "value": body}]
        if html_body:
            content_list.append({"type": "text/html", "value": html_body})

        payload = {
            "personalizations": [{"to": [{"email": e} for e in recipients]}],
            "from": {"email": self.sender_email, "name": self.sender_name},
            "subject": subject,
            "content": content_list,
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(SENDGRID_API_URL, headers=headers, json=payload)
                resp.raise_for_status()

            msg_id = resp.headers.get("X-Message-Id", "sendgrid_ok")
            self.log(f"email_sender: sent via SendGrid (ID={msg_id})")

            recipients_str = ", ".join(recipients)
            md = (
                f"✅ **Email Sent via SendGrid**\n\n"
                f"**To:** {recipients_str}\n"
                f"**Subject:** {subject}\n"
                f"**Message ID:** `{msg_id}`\n\n"
                f"**Body Preview:**\n{body[:400]}"
            )

            return ToolResult(
                success=True,
                data={"provider": "sendgrid", "message_id": msg_id, "recipients": recipients},
                summary=f"Email sent via SendGrid to {recipients_str}.",
                artifacts=[
                    {
                        "type": "markdown",
                        "title": f"Email Sent: {subject}",
                        "content": md,
                    }
                ],
            )
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.json().get("errors", [{}])[0].get("message", "")
            except Exception:
                pass
            self.log(f"email_sender: SendGrid HTTP error {e.response.status_code} — {detail}")
            return ToolResult(
                success=False,
                data={},
                summary=f"SendGrid API error (HTTP {e.response.status_code}).",
                error=detail or str(e),
            )
        except Exception as e:
            self.log(f"email_sender: SendGrid error — {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary="Failed to send email via SendGrid.",
                error=str(e),
            )
