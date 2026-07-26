# Model Context Protocol (MCP) Integration Guide

SitRep v3.0 connects to remote Model Context Protocol (MCP) servers to execute cloud operations (Gmail, Google Drive, Google Calendar, Semantic Scholar, Cloudflare, etc.).

---

## 🌐 How Remote MCP Discovery Works

1. At application startup, `DynamicOrchestrator` initializes `MCPClientTool`.
2. `MCPClientTool.fetch_remote_schemas()` sends an HTTP request to each configured endpoint in `MCP_SERVER_URLS`.
3. Remote tool schemas are fetched dynamically, converted to `ToolSchema` objects, and injected into the LLM's system prompt.
4. When the LLM outputs `<tool_call> {"tool": "gmail.send_email", ...} </tool_call>`, the orchestrator routes the tool call directly to `mcp_client.py` for remote execution.

---

## 🔑 Authentication Configuration Strategies

Configure your remote MCP authentication in `.env` using one of three strategies:

### Strategy 1: Global Default Bearer Token (Recommended for Single Server)
```bash
MCP_SERVER_URLS=https://mcp.smithery.run/your_username
MCP_API_TOKEN=your_mcp_api_token_here
```

### Strategy 2: Positional Token Matching
```bash
MCP_SERVER_URLS=https://mcp.smithery.run/user1,https://mcp.cloudflare.com/sse
MCP_API_TOKENS=token_for_user1,token_for_cloudflare
```

### Strategy 3: Explicit JSON Auth Mapping
```bash
MCP_SERVER_AUTH='{"https://mcp.smithery.run/user1": "Bearer token1", "https://mcp.cloudflare.com/sse": "Bearer token2"}'
```

---

## 🛠 Supported Remote MCP Tool Suites

When connected to Smithery or compatible MCP servers, the agent automatically gains access to:
- **Gmail MCP**: `gmail.send_email`, `gmail.create_email_draft`, `gmail.list_threads`, etc.
- **Google Drive MCP**: `googledrive.create_file_from_text`, `googledrive.upload_file`, `googledrive.list_files`, etc.
- **Google Calendar MCP**: `googlecalendar.create_event`, `googlecalendar.find_free_slots`, etc.
- **Semantic Scholar MCP**: `hamid-vakilzadeh-mcpsemanticscholar.*` academic research tools.
