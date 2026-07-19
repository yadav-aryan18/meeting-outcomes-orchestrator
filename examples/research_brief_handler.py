"""Example CODE agent: a research brief backed by a real external API.

Copy this over handler.py to use it (keep the function name `handler`). Shows how
to call an external HTTP API (keyless Wikipedia REST — no signup) with httpx, log
progress with ctx.log(), and fold the result into an LLM synthesis step.
"""
from __future__ import annotations

import urllib.parse

import httpx

from sitrep_agent.sdk import AgentInput, Ctx

WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
# Wikipedia's API requires a descriptive User-Agent (else 403). Identify your agent.
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "sitrep-agent-example/1.0 (https://joinsitrep.com)",
}


async def fetch_wikipedia(topic: str) -> str:
    """Return a short Wikipedia extract for `topic`, or "" if none is found."""
    url = WIKI_SUMMARY + urllib.parse.quote(topic.strip().replace(" ", "_"))
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            return resp.json().get("extract", "")
    except (httpx.HTTPError, ValueError):
        # Network hiccup or non-JSON body — degrade gracefully, don't crash.
        return ""


async def handler(input: AgentInput, ctx: Ctx) -> dict:
    title = input.task.get("title") or "Research brief"

    # Step 1: let the LLM pick one concrete topic to look up.
    topic = (
        await ctx.llm.complete(
            system="Extract the single most relevant topic to research as a short "
            "Wikipedia-style title. Reply with ONLY the topic, no punctuation.",
            prompt=f"Task: {title}\n\nMeeting summary:\n{input.summary}",
            temperature=0.0,
        )
    ).strip().splitlines()[0]

    # Step 2: fetch external context.
    ctx.log(f"fetching external context for: {topic}")
    extract = await fetch_wikipedia(topic)
    ctx.log("external context found" if extract else "no external context found")

    # Step 3: synthesize a brief from the summary + fetched context.
    context = extract or "(no external reference material was found)"
    brief = await ctx.llm.complete(
        system="You are a research analyst. Write a tight brief with sections: "
        "Overview, Key facts, Open questions. Ground it in the provided reference "
        "material; clearly mark anything unverified.",
        prompt=f"Task: {title}\n\nMeeting summary:\n{input.summary}\n\n"
        f"Reference material on '{topic}':\n{context}",
    )

    return {
        "artifacts": [
            {"type": "markdown", "title": f"{title} — brief", "content": brief},
        ]
    }
