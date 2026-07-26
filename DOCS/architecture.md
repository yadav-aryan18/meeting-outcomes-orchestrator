# System Architecture & Core Engine

SitRep Meeting Outcomes Orchestrator v3.0 is built on a SOTA ReAct (Reasoning + Acting) Agent Architecture.

---

## 🏛 Core Architectural Components

### 1. Dynamic ReAct Orchestrator (`sitrep_agent/orchestrator.py`)
- **Reasoning Loop**: Operates on an iterative ReAct cycle: `<thinking>` ➔ `<tool_call>` ➔ `<observation>`.
- **Zero Hardcoded Routing**: Dynamically inspects registered tool schemas (`get_schema()`) and auto-discovered remote MCP schemas to decide execution trajectories.
- **Parallel Tool Execution**: Identifies independent tool calls within a single step and executes them concurrently using `asyncio.gather`.

---

### 2. Pure SOTA Task Audit Checklist
To prevent premature loop termination when an LLM emits `<done/>` early:
- On every observation step, `_build_observation()` dynamically injects a side-by-side comparison:
  - **Original Task**: User's title & description.
  - **Tools Executed So Far**: Dynamic list of succeeded tool names (`['web_search', 'slides']`).
  - **Self-Audit Instruction**: Prompts the LLM to verify if any requested actions (such as sending emails or creating records) remain unexecuted before finalizing synthesis.

---

### 3. Remote MCP Client Engine (`sitrep_agent/tools/mcp_client.py`)
- Auto-discovers remote MCP tools over HTTP/SSE endpoints (e.g., Smithery).
- Supports 3-tiered authentication:
  1. **Explicit URL JSON Mapping**: `MCP_SERVER_AUTH` map.
  2. **Positional Token Matching**: `MCP_SERVER_URLS` & `MCP_API_TOKENS`.
  3. **Global Fallback Token**: `MCP_API_TOKEN`.

---

### 4. Hybrid Context & Semantic RAG Memory
- **SQLite Memory (`sitrep_agent/database.py` & `memory.py`)**: Stores historical meeting metadata, attendees, and action items.
- **Vector RAG Store (`sitrep_agent/tools/vector_memory.py`)**: Performs local TF-IDF semantic vector search over past meetings to provide contextually relevant historical facts.

---

### 5. Multi-Provider LLM Failover (`sitrep_agent/sdk.py`)
- Primary Provider: Google AI Studio (Gemini 3.5 & 3.1 Flash Lite).
- Failover Chain: Automatically retries on rate limits (429) or server errors (5xx) using OpenRouter, Groq, OpenAI, or local Ollama endpoints.
