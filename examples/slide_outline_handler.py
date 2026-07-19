"""Example CODE agent: turns a meeting task into a slide-deck outline.

Copy this over handler.py to use it (keep the function name `handler`). Shows a
two-step LLM chain and an html artifact.
"""
from __future__ import annotations

from sitrep_agent.sdk import AgentInput, Ctx


async def handler(input: AgentInput, ctx: Ctx) -> dict:
    title = input.task.get("title") or "Deck"

    # Step 1: outline the deck.
    outline = await ctx.llm.complete(
        system="You are a presentation strategist. Produce a numbered slide-by-slide "
        "outline (title + 2-3 bullets per slide). 6-10 slides.",
        prompt=f"Topic: {title}\n\nMeeting summary:\n{input.summary}",
    )

    # Step 2: render a simple HTML preview (sanitized server-side by SitRep).
    html = await ctx.llm.complete(
        system="Convert this slide outline into a clean semantic HTML fragment "
        "(h2 per slide, ul of bullets). No <script>, no inline styles.",
        prompt=outline,
    )

    return {
        "artifacts": [
            {"type": "markdown", "title": f"{title} — outline", "content": outline},
            {"type": "html", "title": f"{title} — preview", "content": html},
        ]
    }
