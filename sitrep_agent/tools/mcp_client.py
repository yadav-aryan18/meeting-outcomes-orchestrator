"""
sitrep_agent/tools/mcp_client.py

Model Context Protocol (MCP) Client tool.

Connects to external MCP servers (HTTP / SSE / JSON-RPC transport) and exposes
their tools dynamically to the Meeting Outcomes Orchestrator.

Features:
  - Connects to remote MCP endpoints specified in MCP_SERVER_URLS
  - Discovers tools via JSON-RPC 2.0 `tools/list`
  - Executes tool calls via JSON-RPC 2.0 `tools/call`
  - Returns raw result data and formatted Markdown artifacts
  - Graceful fallback when MCP_SERVER_URLS is empty or servers are offline

Setup & Env Vars:
  MCP_SERVER_URLS — Comma-separated list of MCP server URLs (e.g. http://localhost:8000/mcp,http://slack-mcp.local/sse)

Usage:
    result = await MCPClientTool(ctx).execute(
        operation="call_tool",
        tool_name="github_create_issue",
        arguments={"repo": "owner/repo", "title": "Bug fix"}
    )
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from .base import BaseTool, ToolResult, ToolSchema

MCP_SERVER_URLS = os.getenv("MCP_SERVER_URLS", "")


class MCPClientTool(BaseTool):
    """Connect to external Model Context Protocol (MCP) servers."""

    name = "mcp_client"
    description = (
        "Connect to external MCP (Model Context Protocol) servers via HTTP/SSE/JSON-RPC "
        "to list or execute remote tools. Enables integrations with any custom MCP server "
        "(GitHub MCP, Slack MCP, Database MCP, custom internal APIs). "
        "Configured via MCP_SERVER_URLS env var."
    )

    def __init__(self, ctx: Any = None):
        super().__init__(ctx=ctx)
        self.server_urls = [
            u.strip() for u in MCP_SERVER_URLS.split(",") if u.strip() and u.strip().startswith("http")
        ]

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="mcp_client",
            description=(
                "Connect to external MCP (Model Context Protocol) servers to query available "
                "tools or execute remote tool calls. Configured via MCP_SERVER_URLS env var."
            ),
            parameters={
                "operation": {
                    "type": "string",
                    "description": "One of: list_tools, call_tool.",
                    "default": "call_tool",
                },
                "tool_name": {
                    "type": "string",
                    "description": "The name of the remote tool to execute (for call_tool).",
                },
                "arguments": {
                    "type": "object",
                    "description": "Arguments dictionary for the remote tool call.",
                    "default": {},
                },
                "server_url": {
                    "type": "string",
                    "description": "Optional specific MCP server URL to target.",
                },
            },
            required=["operation"],
            returns="Dict with 'result', 'server_url', and 'tool_name' keys.",
        )

    async def execute(
        self,
        operation: str = "call_tool",
        tool_name: str = "",
        arguments: dict[str, Any] | None = None,
        server_url: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        """Execute an MCP operation (list_tools or call_tool).

        Args:
            operation: One of: "list_tools", "call_tool".
            tool_name: Name of remote tool to execute.
            arguments: Arguments for remote tool call.
            server_url: Optional target server URL.

        Returns:
            ToolResult with remote tool output.
        """
        tool_name = tool_name or kwargs.get("name", "")
        arguments = arguments or kwargs.get("args", {})

        targets = [server_url] if server_url else self.server_urls
        if not targets:
            msg = "MCP Client not configured. Set MCP_SERVER_URLS in .env (comma-separated HTTP endpoints)."
            self.log(f"mcp_client: {msg}")
            return ToolResult(
                success=False,
                data={},
                summary=msg,
                error="Missing MCP_SERVER_URLS env var.",
            )

        if operation == "list_tools":
            return await self._list_tools_from_servers(targets)
        else:
            if not tool_name:
                return ToolResult(
                    success=False,
                    data={},
                    summary="tool_name is required for call_tool operation.",
                    error="Missing tool_name parameter.",
                )
            return await self._call_tool_on_servers(targets, tool_name, arguments)

    async def _list_tools_from_servers(self, targets: list[str]) -> ToolResult:
        """Query `tools/list` on all target MCP servers."""
        all_tools: list[dict[str, Any]] = []
        errors: list[str] = []

        for target in targets:
            self.log(f"mcp_client: listing tools from {target}")
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            }
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(target, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                tools = data.get("result", {}).get("tools", [])
                for t in tools:
                    t["_server_url"] = target
                    all_tools.append(t)
            except Exception as e:
                errors.append(f"{target}: {str(e)[:80]}")
                self.log(f"mcp_client: error querying {target} — {str(e)[:80]}")

        if not all_tools and errors:
            return ToolResult(
                success=False,
                data={"errors": errors},
                summary=f"Failed to fetch tools from MCP servers. Errors: {len(errors)}",
                error="; ".join(errors),
            )

        lines = ["| Server | Tool | Description |", "|---|---|---|"]
        for t in all_tools:
            lines.append(f"| {t.get('_server_url')} | `{t.get('name')}` | {t.get('description', '')[:60]} |")

        md = "\n".join(lines)

        return ToolResult(
            success=True,
            data={"tools": all_tools, "count": len(all_tools)},
            summary=f"Discovered {len(all_tools)} tools across {len(targets)} MCP server(s).",
            artifacts=[
                {
                    "type": "markdown",
                    "title": "Discovered MCP Tools",
                    "content": md,
                }
            ],
        )

    async def _call_tool_on_servers(
        self, targets: list[str], tool_name: str, arguments: dict[str, Any]
    ) -> ToolResult:
        """Execute `tools/call` on target MCP servers."""
        last_error = ""
        for target in targets:
            self.log(f"mcp_client: calling tool '{tool_name}' on {target}")
            payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(target, json=payload)
                    resp.raise_for_status()
                    res_json = resp.json()

                if res_json.get("error"):
                    err_msg = res_json["error"].get("message", "MCP JSON-RPC error")
                    last_error = f"{target}: {err_msg}"
                    continue

                result = res_json.get("result", {})
                content = result.get("content", [])
                is_error = result.get("isError", False)

                summary_text = f"Executed MCP tool '{tool_name}' on {target}."
                md_parts = [f"**MCP Tool:** `{tool_name}` on `{target}`\n"]

                for block in content:
                    if block.get("type") == "text":
                        md_parts.append(block.get("text", ""))

                md = "\n\n".join(md_parts)

                return ToolResult(
                    success=not is_error,
                    data={"result": result, "server_url": target, "tool_name": tool_name},
                    summary=summary_text,
                    artifacts=[
                        {
                            "type": "markdown",
                            "title": f"MCP: {tool_name}",
                            "content": md,
                        }
                    ],
                )
            except Exception as e:
                last_error = f"{target}: {str(e)[:80]}"
                self.log(f"mcp_client: call failed on {target} — {str(e)[:80]}")

        return ToolResult(
            success=False,
            data={},
            summary=f"Failed to execute MCP tool '{tool_name}'.",
            error=last_error or "All target MCP servers failed.",
        )
