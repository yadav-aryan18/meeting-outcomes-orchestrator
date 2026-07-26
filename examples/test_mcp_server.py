"""
examples/test_mcp_server.py

Demonstration & Test Script for Model Context Protocol (MCP) Server Integration.

This script starts a live HTTP/JSON-RPC 2.0 MCP server offering dynamic tools,
then uses SitRep's MCPClientTool to discover and execute remote tools.

Usage:
    python examples/test_mcp_server.py
"""
import asyncio
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# Ensure workspace root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sitrep_agent.sdk import Ctx, LLM
from sitrep_agent.tools.mcp_client import MCPClientTool


class LiveMCPServer(BaseHTTPRequestHandler):
    """Model Context Protocol (MCP) HTTP / JSON-RPC 2.0 Server Implementation."""

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        payload = json.loads(body.decode("utf-8"))

        method = payload.get("method")
        req_id = payload.get("id")

        if method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "get_live_stock_price",
                            "description": "Fetch live market stock prices for ticker symbols.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"ticker": {"type": "string"}},
                                "required": ["ticker"],
                            },
                        },
                        {
                            "name": "search_customer_support_tickets",
                            "description": "Search Zendesk / Salesforce support ticket records.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"customer_email": {"type": "string"}},
                                "required": ["customer_email"],
                            },
                        },
                    ]
                },
            }
        elif method == "tools/call":
            params = payload.get("params", {})
            tool_name = params.get("name")
            args = params.get("arguments", {})

            if tool_name == "get_live_stock_price":
                ticker = args.get("ticker", "GOOGL").upper()
                text = f"Stock Price [{ticker}]: $192.45 (+1.85% today). Volume: 14.2M"
            elif tool_name == "search_customer_support_tickets":
                email = args.get("customer_email", "")
                text = f"Support Tickets for '{email}': 2 open tickets (Ticket #9042: Urgent, Ticket #8812: Pending)."
            else:
                text = "Tool execution not recognized by MCP server."

            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": False,
                },
            }
        else:
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": "Method not found"},
            }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress HTTP server output logs


async def test_mcp_client(server_url: str):
    print("=" * 70)
    print(f"🚀 SITREP MCP CLIENT TEST — Target Endpoint: {server_url}")
    print("=" * 70)

    ctx = Ctx(instructions="", tools=[], llm=LLM("dummy"))
    mcp_tool = MCPClientTool(ctx=ctx)

    # 1. Discover tools
    print("\n🔍 Step 1: Querying tools/list from MCP server...")
    list_res = await mcp_tool.execute(operation="list_tools", server_url=server_url)
    print(f"Status: {'✅ SUCCESS' if list_res.success else '❌ FAILED'}")
    print(f"Summary: {list_res.summary}")
    if list_res.artifacts:
        print("\nDiscovered Tools Table:")
        print(list_res.artifacts[0]["content"])

    # 2. Execute get_live_stock_price
    print("\n⚡ Step 2: Calling remote tool 'get_live_stock_price' (ticker=GOOGL)...")
    call_res1 = await mcp_tool.execute(
        operation="call_tool",
        tool_name="get_live_stock_price",
        arguments={"ticker": "GOOGL"},
        server_url=server_url,
    )
    print(f"Status: {'✅ SUCCESS' if call_res1.success else '❌ FAILED'}")
    print(f"Summary: {call_res1.summary}")
    if call_res1.artifacts:
        print("\nTool Output Artifact:")
        print(call_res1.artifacts[0]["content"])

    # 3. Execute search_customer_support_tickets
    print("\n⚡ Step 3: Calling remote tool 'search_customer_support_tickets' (email=owais@company.com)...")
    call_res2 = await mcp_tool.execute(
        operation="call_tool",
        tool_name="search_customer_support_tickets",
        arguments={"customer_email": "owais@company.com"},
        server_url=server_url,
    )
    print(f"Status: {'✅ SUCCESS' if call_res2.success else '❌ FAILED'}")
    print(f"Summary: {call_res2.summary}")
    if call_res2.artifacts:
        print("\nTool Output Artifact:")
        print(call_res2.artifacts[0]["content"])

    print("\n" + "=" * 70)
    print("🎉 MCP CLIENT TEST COMPLETED SUCCESSFULLY!")
    print("=" * 70)


def main():
    target_url = os.getenv("MCP_SERVER_URLS")

    # If user provided a remote URL, test directly against it
    if target_url and target_url.startswith("http"):
        endpoint = target_url.split(",")[0].strip()
        asyncio.run(test_mcp_client(endpoint))
    else:
        # Otherwise, start live local MCP HTTP server on port 9876
        server_address = ("127.0.0.1", 9876)
        httpd = HTTPServer(server_address, LiveMCPServer)
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        print(f"Started live MCP HTTP server on http://127.0.0.1:9876")

        try:
            asyncio.run(test_mcp_client("http://127.0.0.1:9876"))
        finally:
            httpd.shutdown()


if __name__ == "__main__":
    main()
