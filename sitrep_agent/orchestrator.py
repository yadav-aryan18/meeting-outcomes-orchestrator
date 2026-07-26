"""
sitrep_agent/orchestrator.py

Dynamic Tool-Calling Orchestrator — SOTA agent reasoning engine.

Replaces hardcoded if/elif routing with an LLM-driven decision loop:
  1. Discovers all registered tools and their schemas
  2. Feeds schemas to the LLM in the system prompt
  3. LLM reasons about what to do and outputs <tool_call> tags
  4. Orchestrator parses, validates, and executes tool calls
  5. Results are fed back as <observation> tags
  6. LLM synthesizes final <artifacts>

Uses XML-structured prompting (Claude-style) for maximum compatibility
with any LLM (Ollama, OpenRouter, Claude, GPT, etc.).

Architecture:
  ┌─────────────────────────────────────────────────────────────┐
  │  SYSTEM PROMPT                                               │
  │    - Agent persona                                           │
  │    - Available tools with JSON schemas                       │
  │    - ReAct instructions with XML format                      │
  │    - Examples of good reasoning                              │
  ├─────────────────────────────────────────────────────────────┤
  │  USER PROMPT                                                 │
  │    - Meeting task + summary + attendees                      │
  │    - Historical context from memory                          │
  ├─────────────────────────────────────────────────────────────┤
  │  LLM OUTPUTS:                                                │
  │    <thinking>Why I need these tools...</thinking>            │
  │    <tool_call>{"tool":"email","args":{...}}</tool_call>     │
  │    <tool_call>{"tool":"action_items","args":{...}}</tool_call>│
  ├─────────────────────────────────────────────────────────────┤
  │  ORCHESTRATOR:                                               │
  │    - Parse tool calls                                        │
  │    - Execute in parallel (independent tools)                 │
  │    - Collect results                                         │
  ├─────────────────────────────────────────────────────────────┤
  │  FEEDBACK LOOP (max 3 iterations):                         │
  │    <observation>email: success, body=...</observation>     │
  │    <observation>action_items: success, items=...</observation>│
  │    → LLM may output more <tool_call> or <done>              │
  ├─────────────────────────────────────────────────────────────┤
  │  FINAL SYNTHESIS:                                            │
  │    <artifacts>[{...}, {...}]</artifacts>                     │
  │    <done/>                                                   │
  └─────────────────────────────────────────────────────────────┘

Design principles:
  - The LLM is the router, not the code
  - Tools are self-describing via get_schema()
  - Parallel execution of independent tools
  - Graceful degradation on tool failure
  - Max iteration safety limit (prevents infinite loops)
  - 100% compatible with starter kit SDK
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from sitrep_agent.sdk import AgentInput, Ctx
from sitrep_agent.tools import TOOL_REGISTRY, BaseTool, ToolResult, ToolSchema
from sitrep_agent.tools.memory import MemoryTool
from sitrep_agent.tools.vector_memory import VectorMemoryTool


class DynamicOrchestrator:
    """LLM-driven dynamic tool orchestrator using ReAct reasoning.

    This is the core intelligence layer. It replaces hardcoded routing
    with a reasoning loop where the LLM decides which tools to call,
    in what order, and how to synthesize the final output.
    """

    def __init__(self, ctx: Ctx):
        """Initialize the orchestrator.

        Args:
            ctx: The SitRep Ctx object (provides llm, instructions, logs).
        """
        self.ctx = ctx
        self.llm = ctx.llm
        self.max_iterations = 3
        self.tool_instances: dict[str, BaseTool] = {}
        self.tool_schemas: list[ToolSchema] = []
        self._discover_tools()

    def _discover_tools(self) -> None:
        """Discover all registered tools and collect their schemas.

        This happens once at initialization. New tools added to
        TOOL_REGISTRY are automatically discovered.
        """
        for name, tool_class in TOOL_REGISTRY.items():
            try:
                # Instantiate with ctx for logging
                instance = tool_class(ctx=self.ctx)
                self.tool_instances[name] = instance
                schema = instance.get_schema()
                self.tool_schemas.append(schema)
            except Exception as e:
                self.ctx.log(f"orchestrator: failed to discover tool '{name}': {e}")

    # ── Public API ──────────────────────────────────────────────────────

    async def run(self, input_data: AgentInput) -> dict:
        """Execute the full ReAct orchestration loop.

        Args:
            input_data: The SitRep AgentInput with task, summary, attendees.

        Returns:
            Dict with {"artifacts": [...]} matching the SitRep contract.
        """
        task = input_data.task
        title = task.get("title") or "Draft"
        description = task.get("description") or ""
        summary = input_data.summary or ""
        attendees = input_data.attendees or []
        meeting_id = task.get("id", "unknown")

        self.ctx.log(f"orchestrator: starting dynamic orchestration for '{title}'")
        self.ctx.log(f"orchestrator: discovered {len(self.tool_schemas)} tools")

        # Step 0: Retrieve historical context from memory & vector RAG
        memory = MemoryTool(ctx=self.ctx)
        vector_memory = VectorMemoryTool(ctx=self.ctx)

        historical_context = await memory.get_context(input_data)

        # Retrieve RAG semantic context
        rag_query = f"{title} {description}".strip()
        if rag_query:
            rag_res = await vector_memory.execute(operation="search", query=rag_query, top_k=3)
            if rag_res.success and rag_res.artifacts:
                rag_md = rag_res.artifacts[0].get("content", "")
                if rag_md:
                    historical_context = (historical_context + "\n\n" + rag_md).strip()

        if historical_context:
            self.ctx.log(f"orchestrator: loaded {len(historical_context)} chars of memory/RAG context")

        # Step 1: Build the system prompt with all tool schemas
        system_prompt = self._build_system_prompt()

        # Step 2: Build the user prompt with meeting context
        user_prompt = self._build_user_prompt(
            title=title,
            description=description,
            summary=summary,
            attendees=attendees,
            historical_context=historical_context,
        )

        # Step 3: ReAct loop
        conversation = user_prompt
        all_tool_results: list[dict] = []
        all_action_items: list[dict] = []

        for iteration in range(self.max_iterations):
            self.ctx.log(f"orchestrator: iteration {iteration + 1}/{self.max_iterations}")

            # Call LLM
            try:
                response = await self.llm.complete(
                    system=system_prompt,
                    prompt=conversation,
                    temperature=0.3,
                )
            except Exception as e:
                self.ctx.log(f"orchestrator: LLM call failed — {str(e)[:100]}")
                break

            # Parse thinking
            thinking = self._extract_thinking(response)
            if thinking:
                self.ctx.log(f"orchestrator: thinking — {thinking[:120]}...")

            # Check for done signal
            if self._is_done(response):
                self.ctx.log("orchestrator: received <done> signal")
                break

            # Parse tool calls
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                self.ctx.log("orchestrator: no tool calls found, proceeding to synthesis")
                break

            self.ctx.log(f"orchestrator: executing {len(tool_calls)} tool call(s)")

            # Execute tool calls (parallel where possible)
            results = await self._execute_tool_calls(tool_calls, input_data)
            all_tool_results.extend(results)

            # Collect action items from results for external integrations
            for result in results:
                if result.get("tool") == "action_items" and result.get("success"):
                    items = result.get("data", {}).get("items", [])
                    all_action_items.extend(items)

            # Build observation prompt for next iteration
            observation = self._build_observation(results)
            conversation = (
                f"{conversation}\n\n"
                f"{response}\n\n"
                f"{observation}\n\n"
                f"Based on these observations, decide if you need more tool calls or if you are ready to synthesize the final output. "
                f"If you need more tools, output <tool_call> tags. If you are done, output <artifacts> and <done/>."
            )

        # Step 4: Final synthesis — ask LLM to produce artifacts
        self.ctx.log("orchestrator: requesting final synthesis")
        synthesis_prompt = (
            f"{conversation}\n\n"
            f"You have completed all necessary tool calls. Now synthesize the FINAL OUTPUT.\n"
            f"Output ONLY a <artifacts> block containing a JSON array of artifact objects.\n"
            f"Each artifact must have: type (markdown|html|link), title, content.\n"
            f"Then output <done/> to signal completion.\n"
            f"Do NOT output any <tool_call> tags at this stage."
        )

        try:
            final_response = await self.llm.complete(
                system=system_prompt,
                prompt=synthesis_prompt,
                temperature=0.2,
            )
        except Exception as e:
            self.ctx.log(f"orchestrator: final synthesis failed — {str(e)[:100]}")
            final_response = ""

        # Parse artifacts
        artifacts = self._extract_artifacts(final_response)

        # If no artifacts parsed, generate fallback from tool results or local deterministic tools
        if not artifacts:
            self.ctx.log("orchestrator: no artifacts parsed, generating fallback")
            artifacts = await self._generate_fallback_artifacts(all_tool_results, input_data)

        # Step 5: Post-processing — external integrations
        await self._post_process(
            input_data=input_data,
            artifacts=artifacts,
            all_action_items=all_action_items,
            all_results=all_tool_results,
        )

        # Step 6: Persist to memory & vector store
        self.ctx.log("orchestrator: persisting to memory & vector RAG")
        await memory.store_meeting(
            input_data=input_data,
            action_items=all_action_items,
        )
        await vector_memory.execute(
            operation="store",
            meeting_data={
                "task": input_data.task,
                "summary": input_data.summary,
            },
        )

        self.ctx.log(f"orchestrator: complete — returning {len(artifacts)} artifacts")
        return {"artifacts": artifacts}

    # ── System Prompt Builder ────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Build the system prompt with tool schemas and ReAct instructions.

        This is the "brain" of the agent. The LLM uses this to understand
        what tools are available and how to use them.
        """
        tool_descriptions = []
        for schema in self.tool_schemas:
            tool_descriptions.append(self._format_schema(schema))

        tools_block = "\n\n".join(tool_descriptions)

        return f"""You are the Meeting Outcomes Orchestrator, an advanced AI agent that transforms meeting discussions into structured, actionable work products.

Your job is to analyze a meeting task and intelligently select the right tools to produce the most valuable output. You are NOT a hardcoded script — you reason dynamically about what the user needs.

## Available Tools

You have access to the following tools. Each tool has a name, description, parameters, and return value.

{tools_block}

## How to Use Tools

When you need to use a tool, output a <tool_call> tag with a JSON object inside:

<tool_call>
{{"tool": "TOOL_NAME", "args": {{"param1": "value1", "param2": "value2"}}}}
</tool_call>

You can output MULTIPLE <tool_call> tags in one response. They will be executed in parallel.

## ReAct Reasoning Format

Always wrap your reasoning in <thinking> tags before making tool calls:

<thinking>
1. The user wants [X] based on the task title and description.
2. The meeting summary mentions [Y] which suggests [Z].
3. I should call [tool A] to [reason], and [tool B] to [reason].
4. These tools are independent so I can call them in parallel.
</thinking>

<tool_call>{{...}}</tool_call>
<tool_call>{{...}}</tool_call>

## Rules

1. **Be selective**: Only call tools that are genuinely needed. Don't call research if the meeting summary already has all the information.
2. **Parallelize**: Call independent tools in parallel (multiple <tool_call> tags in one response).
3. **Sequence**: If one tool's output is needed by another, make them in separate iterations.
4. **Never invent facts**: If information is missing, mark it with [TODO: confirm ...].
5. **Be concise**: The user is a busy executive. Keep outputs focused and actionable.
6. **Memory-aware**: If historical context is provided, reference it when relevant.
7. **Graceful**: If a tool fails, adapt your plan. Don't crash.

## Final Output

When you are done with all tool calls, output your final answer as a JSON array inside <artifacts> tags:

<artifacts>
[
  {{"type": "markdown", "title": "Action Items", "content": "..."}},
  {{"type": "link", "title": "Calendar Event", "content": "https://..."}},
  {{"type": "html", "title": "Slide Preview", "content": "<section>..."}}
]
</artifacts>

<done/>

Artifact types:
- "markdown" — formatted text with headings, tables, lists
- "html" — semantic HTML fragment (no scripts, no inline styles)
- "link" — a URL the user can click

Then output <done/> to signal completion.
"""

    def _format_schema(self, schema: ToolSchema) -> str:
        """Format a ToolSchema as a markdown description for the LLM."""
        lines = [
            f"### {schema.name}",
            f"**Description:** {schema.description}",
            "**Parameters:**",
        ]
        for param_name, param_info in schema.parameters.items():
            req = " (required)" if param_name in schema.required else ""
            default = f" [default: {param_info.get('default', 'none')}]" if "default" in param_info else ""
            desc = param_info.get("description", "")
            lines.append(f"  - `{param_name}`{req}{default}: {desc}")
        lines.append(f"**Returns:** {schema.returns}")
        return "\n".join(lines)

    # ── User Prompt Builder ──────────────────────────────────────────────

    def _build_user_prompt(
        self,
        title: str,
        description: str,
        summary: str,
        attendees: list[dict],
        historical_context: str,
    ) -> str:
        """Build the user prompt with meeting context."""
        attendee_names = ", ".join(a.get("name", "") for a in attendees if a.get("name")) or "unknown"

        parts = [
            f"## Meeting Task",
            f"**Title:** {title}",
        ]
        if description:
            parts.append(f"**Description:** {description}")
        parts.extend([
            f"**Attendees:** {attendee_names}",
            f"",
            f"## Meeting Summary",
            f"{summary}",
        ])

        if historical_context:
            parts.extend([
                f"",
                f"## Historical Context (from previous meetings)",
                f"{historical_context}",
            ])

        parts.extend([
            f"",
            f"## Instructions",
            f"Analyze this meeting task and determine the best tools to use. "
            f"Start by reasoning in <thinking> tags, then call the appropriate tools. "
            f"Remember: you can call multiple tools in parallel if they are independent.",
        ])

        return "\n".join(parts)

    # ── XML Parsing ─────────────────────────────────────────────────────

    def _extract_thinking(self, text: str) -> str:
        """Extract content from <thinking> tags."""
        match = re.search(r"<thinking>(.*?)</thinking>", text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _extract_tool_calls(self, text: str) -> list[dict]:
        """Extract and parse all <tool_call> tags from text.

        Returns a list of dicts: {"tool": str, "args": dict}
        """
        calls = []
        pattern = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL | re.IGNORECASE)
        for match in pattern.finditer(text):
            raw = match.group(1).strip()
            try:
                parsed = json.loads(raw)
                normalized = self._normalize_parsed_tool_call(parsed)
                if normalized:
                    calls.append(normalized)
            except json.JSONDecodeError:
                # Try to fix common LLM JSON errors
                try:
                    fixed = self._fix_json(raw)
                    parsed = json.loads(fixed)
                    normalized = self._normalize_parsed_tool_call(parsed)
                    if normalized:
                        calls.append(normalized)
                except Exception:
                    self.ctx.log(f"orchestrator: failed to parse tool call JSON: {raw[:100]}")
        return calls

    def _normalize_parsed_tool_call(self, parsed: Any) -> dict | None:
        if not isinstance(parsed, dict) or "tool" not in parsed:
            return None
        tool_name = str(parsed["tool"])
        if "args" in parsed and isinstance(parsed["args"], dict):
            return {"tool": tool_name, "args": parsed["args"]}
        # Top-level args
        args = {k: v for k, v in parsed.items() if k != "tool"}
        return {"tool": tool_name, "args": args}

    def _fix_json(self, raw: str) -> str:
        """Attempt to fix common LLM JSON formatting errors."""
        # Remove markdown code fences
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"```\s*$", "", raw)
        # Fix trailing commas
        raw = re.sub(r",\s*([}\]])", r"", raw)
        return raw.strip()

    def _is_done(self, text: str) -> bool:
        """Check if the response contains a <done/> signal."""
        return bool(re.search(r"<done\s*/?>", text, re.IGNORECASE))

    def _extract_artifacts(self, text: str) -> list[dict]:
        """Extract and parse the <artifacts> JSON array."""
        match = re.search(r"<artifacts>(.*?)</artifacts>", text, re.DOTALL | re.IGNORECASE)
        if not match:
            return []
        raw = match.group(1).strip()
        try:
            # Remove markdown code fences if present
            raw = re.sub(r"^```json\s*", "", raw)
            raw = re.sub(r"```\s*$", "", raw)
            artifacts = json.loads(raw)
            if isinstance(artifacts, list):
                # Validate each artifact
                valid = []
                for art in artifacts:
                    if isinstance(art, dict) and "type" in art and "title" in art and "content" in art:
                        valid.append(art)
                return valid
        except json.JSONDecodeError:
            self.ctx.log(f"orchestrator: failed to parse artifacts JSON: {raw[:200]}")
        return []

    # ── Tool Execution ──────────────────────────────────────────────────

    async def _execute_tool_calls(
        self, tool_calls: list[dict], input_data: AgentInput
    ) -> list[dict]:
        """Execute a batch of tool calls in parallel.

        Args:
            tool_calls: List of {"tool": str, "args": dict}.
            input_data: The original AgentInput (for context injection).

        Returns:
            List of result dicts with tool name, success, data, and summary.
        """
        tasks = []
        for call in tool_calls:
            tool_name = call.get("tool", "")
            args = call.get("args", {})
            tasks.append(self._execute_single_tool(tool_name, args, input_data))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = []
        for i, result in enumerate(results):
            tool_name = tool_calls[i].get("tool", "unknown")
            if isinstance(result, Exception):
                self.ctx.log(f"orchestrator: tool '{tool_name}' crashed — {str(result)[:100]}")
                output.append({
                    "tool": tool_name,
                    "success": False,
                    "data": {},
                    "summary": f"Tool '{tool_name}' failed: {str(result)[:100]}",
                    "error": str(result),
                })
            else:
                output.append({
                    "tool": tool_name,
                    "success": result.success,
                    "data": result.data,
                    "summary": result.summary,
                    "error": result.error,
                    "artifacts": result.artifacts,
                })
        return output

    async def _execute_single_tool(
        self, tool_name: str, args: dict, input_data: AgentInput
    ) -> ToolResult:
        """Execute a single tool call."""
        if tool_name not in self.tool_instances:
            return ToolResult(
                success=False,
                data={},
                summary=f"Unknown tool: '{tool_name}'",
                error=f"Tool '{tool_name}' not found in registry.",
            )

        tool = self.tool_instances[tool_name]
        self.ctx.log(f"orchestrator: calling '{tool_name}' with args {list(args.keys())}")

        # Inject common context if the tool expects it
        if tool_name in ("email", "action_items", "slides", "research", "email_sender") and "llm" not in args:
            args["llm"] = self.llm

        if tool_name in ("email", "action_items", "slides", "hubspot") and "attendees" not in args:
            args["attendees"] = input_data.attendees

        if tool_name in ("email", "action_items", "slides", "research", "notion", "jira", "linear", "hubspot") and "summary" not in args:
            args["summary"] = input_data.summary

        if tool_name in ("email", "action_items", "slides") and "task_title" not in args:
            args["task_title"] = args.get("title") or input_data.task.get("title", "Draft")

        if tool_name in ("calendar", "calendar_api", "notion", "hubspot") and "title" not in args:
            args["title"] = args.get("task_title") or input_data.task.get("title", "Draft")

        if tool_name in ("research", "web_search") and "query" not in args and "topic" in args:
            args["query"] = args["topic"]

        if tool_name == "wikipedia" and "topic" not in args and "query" in args:
            args["topic"] = args["query"]

        try:
            result = await tool.execute(**args)
            self.ctx.log(f"orchestrator: '{tool_name}' returned success={result.success}")
            return result
        except Exception as e:
            self.ctx.log(f"orchestrator: '{tool_name}' threw {type(e).__name__}: {str(e)[:100]}")
            return ToolResult(
                success=False,
                data={},
                summary=f"Tool '{tool_name}' crashed during execution.",
                error=str(e),
            )

    def _build_observation(self, results: list[dict]) -> str:
        """Build the observation prompt from tool execution results.

        This is fed back to the LLM so it can see what happened.
        """
        lines = ["## Tool Execution Results"]
        for result in results:
            tool_name = result["tool"]
            success = result["success"]
            summary = result.get("summary", "")
            error = result.get("error", "")

            status = "✅ SUCCESS" if success else "❌ FAILED"
            lines.append(f"\n### {tool_name} — {status}")
            if summary:
                lines.append(f"Summary: {summary}")
            if error:
                lines.append(f"Error: {error}")

        return "\n".join(lines)

    # ── Fallback Artifact Generation ────────────────────────────────────

    async def _generate_fallback_artifacts(
        self, results: list[dict], input_data: AgentInput | None = None
    ) -> list[dict]:
        """Generate artifacts from tool results when LLM synthesis fails.

        If no artifacts exist from tool results, runs deterministic local tools
        (ActionItemsTool, EmailTool) to ensure useful output is always returned.
        """
        artifacts = []
        for result in results:
            if not result.get("success"):
                continue
            tool_name = result["tool"]
            tool_artifacts = result.get("artifacts", [])
            artifacts.extend(tool_artifacts)

        # Deduplicate
        seen = set()
        unique = []
        for art in artifacts:
            key = (art.get("type"), art.get("title"))
            if key not in seen:
                seen.add(key)
                unique.append(art)

        if unique:
            return unique

        # Guaranteed Fallback: Execute local tools on input_data
        if input_data and input_data.summary:
            title = input_data.task.get("title", "Meeting Outcome")
            self.ctx.log("orchestrator: running local fallback tools for guaranteed artifacts")

            ai_tool = self.tool_instances.get("action_items")
            if ai_tool:
                try:
                    res = await ai_tool.execute(summary=input_data.summary, task_title=title)
                    if res.artifacts:
                        unique.extend(res.artifacts)
                except Exception as e:
                    self.ctx.log(f"orchestrator: fallback action_items error — {e}")

            email_tool = self.tool_instances.get("email")
            if email_tool:
                try:
                    res = await email_tool.execute(
                        summary=input_data.summary,
                        task_title=title,
                        attendees=input_data.attendees,
                    )
                    if res.artifacts:
                        unique.extend(res.artifacts)
                except Exception as e:
                    self.ctx.log(f"orchestrator: fallback email error — {e}")

        return unique

    # ── Post-Processing ───────────────────────────────────────────────────

    async def _post_process(
        self,
        input_data: AgentInput,
        artifacts: list[dict],
        all_action_items: list[dict],
        all_results: list[dict],
    ) -> None:
        """Run post-processing for external integrations (Slack, Notion, Jira, Linear, HubSpot).

        These are triggered ONLY when explicitly requested by the user in the task title,
        description, or instructions.
        """
        tool_names_called = {r["tool"] for r in all_results}
        title = input_data.task.get("title", "Draft")
        description = input_data.task.get("description", "")
        summary = input_data.summary or ""
        attendees = input_data.attendees or []

        user_intent = f"{title} {description} {self.ctx.instructions}".lower()

        # Slack: post only if explicitly requested and not already called
        if "slack" in user_intent and "slack" not in tool_names_called:
            slack = self.tool_instances.get("slack")
            if slack:
                try:
                    text = f"*Meeting Outcomes: {title}*\n\n"
                    if all_action_items:
                        text += f"Action items extracted: {len(all_action_items)}\n"
                    text += f"Summary: {summary[:500]}"
                    result = await slack.execute(text=text)
                    if result.success:
                        artifacts.extend(result.artifacts)
                        self.ctx.log("orchestrator: posted to Slack per user request")
                except Exception as e:
                    self.ctx.log(f"orchestrator: Slack post failed — {str(e)[:80]}")

        # Notion: save only if explicitly requested and not already called
        if "notion" in user_intent and "notion" not in tool_names_called:
            notion = self.tool_instances.get("notion")
            if notion:
                try:
                    result = await notion.execute(
                        title=title,
                        summary=summary,
                        action_items=all_action_items,
                        attendees=attendees,
                        tags=["meeting-notes"],
                    )
                    if result.success:
                        artifacts.extend(result.artifacts)
                        self.ctx.log("orchestrator: saved to Notion per user request")
                except Exception as e:
                    self.ctx.log(f"orchestrator: Notion save failed — {str(e)[:80]}")

        # Jira: create tickets only if explicitly requested and action items exist
        if "jira" in user_intent and "jira" not in tool_names_called and all_action_items:
            jira = self.tool_instances.get("jira")
            if jira:
                try:
                    result = await jira.execute(
                        action_items=all_action_items,
                        summary=summary,
                    )
                    if result.success:
                        artifacts.extend(result.artifacts)
                        self.ctx.log("orchestrator: created Jira tickets per user request")
                except Exception as e:
                    self.ctx.log(f"orchestrator: Jira ticket creation failed — {str(e)[:80]}")

        # Linear: create issues only if explicitly requested and action items exist
        if "linear" in user_intent and "linear" not in tool_names_called and all_action_items:
            linear = self.tool_instances.get("linear")
            if linear:
                try:
                    result = await linear.execute(
                        action_items=all_action_items,
                        summary=summary,
                    )
                    if result.success:
                        artifacts.extend(result.artifacts)
                        self.ctx.log("orchestrator: created Linear issues per user request")
                except Exception as e:
                    self.ctx.log(f"orchestrator: Linear issue creation failed — {str(e)[:80]}")

        # HubSpot: log meeting activity and tasks only if explicitly requested
        if ("hubspot" in user_intent or "crm" in user_intent) and "hubspot" not in tool_names_called:
            hubspot = self.tool_instances.get("hubspot")
            if hubspot:
                try:
                    result = await hubspot.execute(
                        title=title,
                        summary=summary,
                        attendees=attendees,
                        action_items=all_action_items,
                    )
                    if result.success:
                        artifacts.extend(result.artifacts)
                        self.ctx.log("orchestrator: logged to HubSpot CRM per user request")
                except Exception as e:
                    self.ctx.log(f"orchestrator: HubSpot logging failed — {str(e)[:80]}")

        # Email Sender: send email only if explicitly requested to send (e.g. "send email")
        if "send email" in user_intent and "email_sender" not in tool_names_called:
            email_sender = self.tool_instances.get("email_sender")
            if email_sender and attendees:
                recipients = ", ".join([a.get("email") for a in attendees if a.get("email")])
                if recipients:
                    try:
                        result = await email_sender.execute(
                            to_email=recipients,
                            subject=f"Follow-up: {title}",
                            body=summary,
                        )
                        if result.success:
                            artifacts.extend(result.artifacts)
                            self.ctx.log("orchestrator: sent email per user request")
                    except Exception as e:
                        self.ctx.log(f"orchestrator: email send failed — {str(e)[:80]}")

        # Calendar: create event if scheduling keywords present and not already called
        if "calendar_api" not in tool_names_called and "calendar" not in tool_names_called:
            schedule_keywords = ["schedule", "calendar", "book meeting", "set up call"]
            needs_calendar = any(kw in user_intent for kw in schedule_keywords)
            if needs_calendar:
                cal = self.tool_instances.get("calendar_api") or self.tool_instances.get("calendar")
                if cal:
                    try:
                        result = await cal.execute(
                            title=f"Follow-up: {title}",
                            details=summary[:500],
                        )
                        if result.success:
                            artifacts.extend(result.artifacts)
                            self.ctx.log("orchestrator: created calendar event per user request")
                    except Exception as e:
                        self.ctx.log(f"orchestrator: calendar event failed — {str(e)[:80]}")
