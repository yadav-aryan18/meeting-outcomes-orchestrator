# SitRep Meeting Outcomes Orchestrator v3.0

An advanced, production-grade AI Agent designed for the [SitRep](https://joinsitrep.com) Agent Marketplace, built around the [AgentStarterKit](https://github.com/SitRepAI/AgentStarterKit).

SitRep v3.0 operates as a **SOTA ReAct Dynamic Orchestrator**. It auto-discovers local tools and remote Model Context Protocol (MCP) servers (such as Smithery, Gmail, Google Drive, Google Calendar, and Semantic Scholar), performs multi-turn ReAct reasoning, executes parallel tool operations, and self-audits task execution using a dynamic task checklist.

> [!IMPORTANT]
> **REMOTE MCP TOOLS CONFIGURATION REQUIREMENT:**  
> **Remote MCP tools (such as Gmail, Google Drive, Google Calendar, Slack, GitHub, etc.) MUST be added by the user. You can set up your remote MCP server endpoints using [Smithery.ai](https://smithery.ai) or any other MCP server provider/client, and add them into your `.env` file via `MCP_SERVER_URLS` and `MCP_API_TOKEN`.**

---

## 🌟 High-Level Capabilities

- **Dynamic ReAct Orchestrator**: Multi-turn reasoning loops using `<thinking>`, `<tool_call>`, and `<observation>` tags. Zero hardcoded routing.
- **Multi-Server Remote MCP Discovery**: Automatically discovers remote MCP tool schemas dynamically from remote HTTP/SSE endpoints.
- **Pure Task Audit Checklist**: Prevents premature loop termination by cross-referencing task requirements against executed tools on every step.
- **Multi-Tier MCP Authentication**: 3-tiered authentication strategy (URL JSON mapping, positional matching, global Bearer fallback).
- **Hybrid Context & Vector RAG Memory**: SQLite meeting persistence combined with local TF-IDF semantic vector search.
- **Multi-Provider Failover**: Automatic failover across Google AI Studio (Gemini 3.5 & 3.1 Flash Lite), OpenRouter, Groq, OpenAI, and local Ollama.
- **HMAC Signature Verification**: Complies with SitRep's HMAC-SHA256 request verification (`X-SitRep-Timestamp` & `X-SitRep-Signature`).

---

## 🤝 SitRep API Contract

SitRep POSTs to `<your-url>/run` (and `/test` for the Studio button) with the following JSON structure:

```json
{
  "task":     { "id": "...", "title": "...", "description": "..." },
  "summary":  "the meeting summary",
  "attendees":[ { "id": "...", "name": "..." } ],
  "agent":    { "instructions": "your Studio prompt", "tools": [], "model": "llama3.1" }
}
```

The agent responds with:

```json
{
  "artifacts": [
    {
      "type": "markdown | html | link",
      "title": "...",
      "content": "..."
    }
  ],
  "logs": ["optional log lines"]
}
```

### Artifact Rules & Request Signing
- `html` artifacts are sanitized by SitRep before display; `link` content must be a valid URL.
- Requests are signed with the header `X-SitRep-Signature: sha256=<hmac(secret, "<timestamp>.<body>")>` plus `X-SitRep-Timestamp`.
- `sitrep_agent/sdk.verify_signature()` checks this signature automatically (and is skipped when `SITREP_AGENT_SECRET` is unset for local development).

---

## 📂 Codebase Directory Tree

```text
.
├── app.py                      # FastAPI HTTP entry point (/health, /run, /test)
├── handler.py                  # Thin adapter delegating to DynamicOrchestrator
├── render.yaml                 # Infrastructure-as-code for Render.com deployment
├── requirements.txt            # Python dependencies
├── DOCS/                       # Detailed Documentation Suite
│   ├── architecture.md         # Deep-dive ReAct & Task Checklist engine architecture
│   ├── mcp_integration.md      # Remote MCP discovery & 3-tier auth guide
│   ├── environment_variables.md# Complete .env reference & Render setup
│   └── testing_and_usage.md    # Local testing & HMAC signed client scripts
└── sitrep_agent/
    ├── orchestrator.py         # SOTA ReAct Orchestrator & Task Audit Checklist Engine
    ├── database.py             # SQLite persistence layer for meetings & action items
    ├── sdk.py                  # SitRep SDK (HMAC verification & multi-provider LLM client)
    └── tools/
        ├── __init__.py         # Central tool registry
        ├── base.py             # Abstract BaseTool and ToolResult classes
        ├── mcp_client.py       # Multi-server remote MCP client with 3-tier auth
        ├── memory.py           # Historical meeting context retrieval
        ├── vector_memory.py    # Semantic TF-IDF Vector RAG storage & search
        ├── web_search.py       # Local DuckDuckGo web search
        ├── web_scraper.py      # HTML text extraction tool
        ├── wikipedia.py        # Wikipedia REST API tool
        ├── slides.py           # Slide outline & HTML preview generator
        ├── email.py            # Local email drafting tool
        ├── action_items.py     # Action item extraction tool
        ├── research.py         # Multi-source research synthesizer
        ├── slack.py            # Slack messenger integration
        ├── notion.py           # Notion database integration
        ├── jira.py             # Jira issue creation integration
        ├── calendar.py         # Google Calendar link generator
        └── calendar_api.py     # Google Calendar API integration
```

---

## ⚡ Quick Start & Testing

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment variables
cp .env.example .env

# 3. Start local development server
python3 -m uvicorn app:app --host 0.0.0.0 --port 9000
```

Verify health:
```bash
curl http://localhost:9000/health
# {"ok": true}
```

### Testing via `curl`

#### 1. Unauthenticated Local Test (When `SITREP_AGENT_SECRET` is unset)

```bash
curl -X POST http://localhost:9000/test \
  -H "Content-Type: application/json" \
  -d '{
    "task": {
      "id": "local_test_1",
      "title": "Fetch financial data and send email to attendee",
      "description": "Fetch NVIDIA market cap and send an email to user@example.com"
    },
    "summary": "Meeting context regarding financial records.",
    "attendees": [{"name": "Attendee", "email": "user@example.com"}]
  }'
```

#### 2. Authenticated Production Test (HMAC Signed `curl` with Secret)

```bash
SECRET="YOUR_SITREP_AGENT_SECRET_HERE"
URL="https://your-app.onrender.com/test"
PAYLOAD='{"task":{"id":"prod_test_1","title":"Fetch financial data and send email","description":"Fetch NVIDIA financial data and email user@example.com"},"summary":"Meeting context","attendees":[{"name":"Attendee","email":"user@example.com"}]}'

TS=$(date +%s)
SIG="sha256="$(echo -n "${TS}.${PAYLOAD}" | openssl dgst -sha256 -hmac "${SECRET}" | awk '{print $2}')

curl -X POST "${URL}" \
  -H "Content-Type: application/json" \
  -H "X-SitRep-Timestamp: ${TS}" \
  -H "X-SitRep-Signature: ${SIG}" \
  -d "${PAYLOAD}"
```

---

## 📚 Detailed Documentation Index

For in-depth technical documentation, refer to the guides in the `DOCS/` folder:

- 🏛 [Architecture & Core Engine](DOCS/architecture.md): SOTA ReAct loop, Dynamic Task Audit Checklist, and vector RAG design.
- 🌐 [Remote MCP Integration Guide](DOCS/mcp_integration.md): Auto-discovery, 3-tier authentication strategies, and remote tool suites.
- ⚙️ [Environment Variables & Deployment](DOCS/environment_variables.md): Detailed `.env` reference and Render.com setup guide.
- 🧪 [Testing & Verification Guide](DOCS/testing_and_usage.md): Testing unauthenticated and HMAC-signed requests locally and in production.

---

## 📜 License

MIT License. Developed for the SitRep Agent Ecosystem.
