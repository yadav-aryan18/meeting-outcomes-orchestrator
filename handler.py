"""
👋 THE INTELLIGENT ORCHESTRATOR

This is the core of the Meeting Outcomes Agent. It does NOT just pass a prompt
to an LLM. Instead it:

  1. ANALYZES the task to understand what the user actually needs
  2. ROUTES to the right combination of tools
  3. EXECUTES tools in parallel where possible (web search + Wikipedia)
  4. SYNTHESIZES all outputs into polished, multi-format artifacts
  5. RETURNS markdown + HTML + calendar links as appropriate

Supported task types (auto-detected):
  - follow_up_email  → Personalized email to attendees
  - research_brief   → Multi-source research with citations
  - action_items     → Structured task extraction with owners/deadlines
  - project_plan     → Action items + calendar links + timeline
  - slide_deck       → Outline + HTML preview
  - calendar_event   → Google Calendar scheduling link
  - documentation    → Technical docs / PRD generation
  - mixed            → Combines multiple outputs intelligently

Design principles:
  - Every tool is async and runs independently
  - Failures in one tool don't crash the agent
  - ctx.log() tracks every decision for transparency
  - Output is always useful even if external APIs fail
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from sitrep_agent.sdk import AgentInput, Ctx
from sitrep_agent.tools import (
    ActionItemsTool,
    CalendarTool,
    EmailTool,
    ResearchTool,
    SlidesTool,
    ToolResult,
)

# Fallback prompt for no-code mode (rarely used since we override everything)
SYSTEM_PROMPT = Path(__file__).with_name("prompt.txt").read_text(encoding="utf-8").strip()

# Task classification prompt — this is the "brain" of the router
TASK_ANALYSIS_SYSTEM = """You are a task classifier for a post-meeting AI agent.
Analyze the meeting task and determine which outputs would be most valuable.

Respond with EXACTLY one of these categories:
- follow_up_email    → The task is about sending an email, following up, or communicating
- research_brief     → The task asks for research, competitive analysis, or background info
- action_items       → The task is about extracting tasks, decisions, or next steps
- project_plan       → The task involves planning, roadmaps, sprints, or timelines
- slide_deck         → The task mentions slides, presentation, deck, or board meeting
- calendar_event     → The task is about scheduling, setting up a meeting, or finding a time
- documentation      → The task asks for docs, PRD, technical spec, or requirements
- mixed              → Multiple categories apply, or you're unsure

Also suggest 1-3 tool names that would help:
Available tools: web_search, wikipedia, web_scraper, calendar, email, slides, action_items, research

Format your response EXACTLY like this (no extra text):
CATEGORY: <category>
TOOLS: <tool1>, <tool2>
REASON: <one sentence explaining why>"""


async def analyze_task(task_title: str, task_description: str, summary: str, llm) -> dict:
    """Use LLM to classify the task and recommend tools."""
    user = (
        f"Task title: {task_title}\n"
        f"Task description: {task_description}\n\n"
        f"Meeting summary:\n{summary[:1500]}"
    )

    raw = await llm.complete(system=TASK_ANALYSIS_SYSTEM, prompt=user, temperature=0.2)

    # Parse the structured response
    category = "mixed"
    tools = []
    reason = ""

    for line in raw.splitlines():
        line = line.strip()
        if line.lower().startswith("category:"):
            category = line.split(":", 1)[1].strip().lower()
        elif line.lower().startswith("tools:"):
            tools = [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]
        elif line.lower().startswith("reason:"):
            reason = line.split(":", 1)[1].strip()

    # Normalize category
    valid_categories = {
        "follow_up_email", "research_brief", "action_items",
        "project_plan", "slide_deck", "calendar_event", "documentation", "mixed"
    }
    if category not in valid_categories:
        category = "mixed"

    return {
        "category": category,
        "tools": tools,
        "reason": reason or "Auto-classified based on task content.",
    }


async def handler(input: AgentInput, ctx: Ctx) -> dict:
    """Main entry point — the intelligent orchestrator."""
    task = input.task
    title = task.get("title") or "Draft"
    description = task.get("description") or ""
    summary = input.summary or ""
    attendees = input.attendees or []

    ctx.log(f"orchestrator: received task '{title}'")
    ctx.log(f"orchestrator: {len(attendees)} attendees, summary length {len(summary)}")

    # ── Step 1: Analyze the task ─────────────────────────────────────────
    ctx.log("orchestrator: analyzing task intent...")
    analysis = await analyze_task(title, description, summary, ctx.llm)
    category = analysis["category"]
    ctx.log(f"orchestrator: classified as '{category}' — {analysis['reason']}")

    # ── Step 2: Select and execute tools based on category ───────────────
    artifacts: list[dict] = []
    all_results: list[ToolResult] = []

    if category == "follow_up_email":
        # Email tool handles everything
        email_tool = EmailTool(ctx=ctx)
        result = await email_tool.execute(
            task_title=title,
            task_description=description,
            summary=summary,
            attendees=attendees,
            llm=ctx.llm,
        )
        all_results.append(result)
        artifacts.extend(result.artifacts)

    elif category == "research_brief":
        # Research tool orchestrates web search + Wikipedia + synthesis
        research_tool = ResearchTool(ctx=ctx)
        result = await research_tool.execute(
            query=title,
            summary=summary,
            llm=ctx.llm,
            scrape_urls=True,
            max_scrape=2,
        )
        all_results.append(result)
        artifacts.extend(result.artifacts)

    elif category == "action_items":
        # Extract structured action items
        action_tool = ActionItemsTool(ctx=ctx)
        result = await action_tool.execute(
            task_title=title,
            summary=summary,
            attendees=attendees,
            llm=ctx.llm,
        )
        all_results.append(result)
        artifacts.extend(result.artifacts)

    elif category == "project_plan":
        # Parallel: action items + calendar link
        action_tool = ActionItemsTool(ctx=ctx)
        cal_tool = CalendarTool(ctx=ctx)

        action_result, cal_result = await asyncio.gather(
            action_tool.execute(task_title=title, summary=summary, attendees=attendees, llm=ctx.llm),
            cal_tool.execute(title=f"Follow-up: {title}", details=summary[:500]),
        )
        all_results.extend([action_result, cal_result])
        artifacts.extend(action_result.artifacts)
        artifacts.extend(cal_result.artifacts)

        # Also generate a project plan narrative
        plan = await ctx.llm.complete(
            system="You are a project manager. Write a concise project plan markdown doc "
                   "with: Objectives, Milestones, Timeline, Owners, and Risks. "
                   "Base it strictly on the meeting summary. Use [TODO] for unknowns.",
            prompt=f"Project: {title}\n\nMeeting summary:\n{summary}",
            temperature=0.5,
        )
        artifacts.append({"type": "markdown", "title": f"{title} — Project Plan", "content": plan})

    elif category == "slide_deck":
        slides_tool = SlidesTool(ctx=ctx)
        result = await slides_tool.execute(
            task_title=title,
            summary=summary,
            llm=ctx.llm,
        )
        all_results.append(result)
        artifacts.extend(result.artifacts)

    elif category == "calendar_event":
        cal_tool = CalendarTool(ctx=ctx)
        result = await cal_tool.execute(
            title=title,
            details=description or summary[:800],
        )
        all_results.append(result)
        artifacts.extend(result.artifacts)

        # Also draft a brief meeting agenda
        agenda = await ctx.llm.complete(
            system="Draft a focused meeting agenda (3-5 items) in markdown.",
            prompt=f"Meeting: {title}\n\nContext:\n{summary}",
            temperature=0.5,
        )
        artifacts.append({"type": "markdown", "title": f"{title} — Agenda", "content": agenda})

    elif category == "documentation":
        # Research context first, then generate docs
        research_tool = ResearchTool(ctx=ctx)
        research_result = await research_tool.execute(
            query=title,
            summary=summary,
            llm=ctx.llm,
            scrape_urls=False,
        )

        research_context = ""
        if research_result.success:
            research_context = research_result.data.get("brief", "")
            artifacts.extend(research_result.artifacts)

        doc = await ctx.llm.complete(
            system="You are a technical writer. Produce a well-structured markdown document "
                   "(PRD, spec, or documentation) based on the meeting. Include: "
                   "Overview, Goals, Requirements, Acceptance Criteria, Timeline. "
                   "Use [TODO] for anything unclear.",
            prompt=f"Document: {title}\n\nMeeting summary:\n{summary}\n\n"
                   f"Research context:\n{research_context}",
            temperature=0.4,
        )
        artifacts.append({"type": "markdown", "title": f"{title} — Documentation", "content": doc})

    else:  # mixed or fallback
        ctx.log("orchestrator: running mixed-mode pipeline")

        # Always extract action items
        action_tool = ActionItemsTool(ctx=ctx)
        action_result = await action_tool.execute(
            task_title=title, summary=summary, attendees=attendees, llm=ctx.llm
        )
        all_results.append(action_result)
        artifacts.extend(action_result.artifacts)

        # Always draft an email if attendees exist
        if attendees:
            email_tool = EmailTool(ctx=ctx)
            email_result = await email_tool.execute(
                task_title=title,
                task_description=description,
                summary=summary,
                attendees=attendees,
                llm=ctx.llm,
            )
            all_results.append(email_result)
            artifacts.extend(email_result.artifacts)

        # Research if the task sounds like it needs external info
        research_keywords = ["research", "competitive", "market", "analysis", "background", "evaluate"]
        needs_research = any(kw in (title + " " + description).lower() for kw in research_keywords)

        if needs_research:
            research_tool = ResearchTool(ctx=ctx)
            research_result = await research_tool.execute(
                query=title, summary=summary, llm=ctx.llm, scrape_urls=True, max_scrape=2
            )
            all_results.append(research_result)
            artifacts.extend(research_result.artifacts)

        # Calendar if scheduling keywords present
        schedule_keywords = ["schedule", "meeting", "follow-up", "sync", "check-in", "call"]
        needs_calendar = any(kw in (title + " " + description).lower() for kw in schedule_keywords)

        if needs_calendar:
            cal_tool = CalendarTool(ctx=ctx)
            cal_result = await cal_tool.execute(
                title=f"Follow-up: {title}",
                details=description or summary[:500],
            )
            all_results.append(cal_result)
            artifacts.extend(cal_result.artifacts)

    # ── Step 3: Deduplicate and finalize ─────────────────────────────────
    # Remove duplicate artifacts by (type, title) key
    seen = set()
    unique_artifacts = []
    for art in artifacts:
        key = (art.get("type"), art.get("title"))
        if key not in seen:
            seen.add(key)
            unique_artifacts.append(art)

    ctx.log(f"orchestrator: returning {len(unique_artifacts)} artifacts")

    return {
        "artifacts": unique_artifacts,
    }
