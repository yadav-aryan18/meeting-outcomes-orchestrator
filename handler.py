"""
👋 THE INTELLIGENT ORCHESTRATOR — v3.0 (Dynamic ReAct)

This handler is now a thin wrapper around the DynamicOrchestrator.
All routing, tool selection, and reasoning lives in sitrep_agent/orchestrator.py.

The orchestrator uses SOTA ReAct pattern:
  1. Discovers all registered tools dynamically via get_schema()
  2. Feeds tool schemas to the LLM in the system prompt
  3. LLM reasons about what to do and outputs <tool_call> tags
  4. Orchestrator parses, validates, and executes tool calls in parallel
  5. Results are fed back as <observation> tags
  6. LLM synthesizes final <artifacts>

This replaces the hardcoded if/elif routing with true agent intelligence.
"""
from __future__ import annotations

from pathlib import Path

from sitrep_agent.orchestrator import DynamicOrchestrator
from sitrep_agent.sdk import AgentInput, Ctx

# Fallback prompt for no-code mode (rarely used since orchestrator overrides everything)
SYSTEM_PROMPT = Path(__file__).with_name("prompt.txt").read_text(encoding="utf-8").strip()


async def handler(input: AgentInput, ctx: Ctx) -> dict:
    """Main entry point — delegates to the DynamicOrchestrator.

    The orchestrator handles all reasoning, tool selection, execution,
    and synthesis. This function is just a thin adapter between
    the SitRep contract and the orchestrator.
    """
    ctx.log("handler: delegating to DynamicOrchestrator")
    orchestrator = DynamicOrchestrator(ctx=ctx)
    return await orchestrator.run(input)
