# SitRep Intelligent Meeting Outcomes Orchestrator

This repository provides an advanced, production-ready framework for building Intelligent Meeting Agents that interact with the [SitRep](https://joinsitrep.com) platform.

Unlike simple prompt-based agents, this orchestrator uses a modular, multi-tool architecture to transform meeting transcripts into high-quality, actionable artifacts, such as structured project plans, technical PRDs, personalized emails, and research briefs.

---

## Key Features

*   **Intelligent Orchestration**: The core orchestrator (`handler.py`) automatically analyzes meeting transcripts to classify the user's intent and routes tasks to the appropriate tool suite.
*   **Modular Tooling**: A robust, extensible `sitrep_agent/tools/` suite provides reusable components for web search, scraping, Wikipedia lookups, calendar scheduling, email drafting, and slide generation.
*   **Parallel Execution**: The orchestrator leverages Python's `asyncio` to execute independent tools (e.g., searching Wikipedia and performing a web scrape) concurrently, significantly reducing agent response time.
*   **Extensible Design**: Adding a new tool is straightforward — implement a new class inheriting from `BaseTool` and register it in the `TOOL_REGISTRY`.
*   **Standardized Output**: All tools adhere to a consistent `ToolResult` format, ensuring the orchestrator can reliably synthesize final artifacts for the user.

---

## Project Architecture

```text
.
├── app.py                  # HTTP wrapper, handles SitRep contract routes (/run, /test, /health)
├── handler.py              # The orchestrator brain, manages task analysis, routing, and synthesis
├── sitrep_agent/           # Core library directory
│   ├── __init__.py         
│   ├── sdk.py              # SDK managing signature verification and LLM client interactions
│   └── tools/              # Modular tool suite
│       ├── __init__.py     # Tool registry
│       ├── action_items.py # Extracts structured task information
│       ├── base.py         # Defines Abstract BaseTool for all tools
│       ├── calendar.py     # Generates Google Calendar event links
│       ├── email.py        # Drafts personalized follow-up emails
│       ├── research.py     # Synthesizes multi-source research briefs
│       ├── slides.py       # Generates slide outlines and previews
│       ├── web_scraper.py  # Performs URL content extraction and cleaning
│       ├── web_search.py   # Executes DuckDuckGo searches
│       └── wikipedia.py    # Fetches Wikipedia page summaries
├── examples/               # Reference implementation handlers
├── scripts/                # Utility scripts for local development and testing
│   ├── run-local.sh        # Starts the agent locally
│   ├── smoke-test.sh       # Runs a smoke test on the agent
│   └── tunnel.sh           # Exposes local agent to public URL
├── Dockerfile              # Container definition
├── Procfile                # Procfile for deployment platforms
├── render.yaml             # Deployment configuration for Render
└── requirements.txt        # Python dependency list
```

---

## Supported Task Types

| Task Type | What It Produces |
|---|---|
| **Follow-up Email** | Personalized email using attendee names, with next steps |
| **Research Brief** | Multi-source research with web search, Wikipedia, citations |
| **Action Items** | Structured table with owners, deadlines, priorities, risks |
| **Project Plan** | Action items + timeline + calendar link + narrative plan |
| **Slide Deck** | Numbered outline + HTML preview |
| **Calendar Event** | One-click Google Calendar link + agenda |
| **Documentation** | PRD, spec, or technical doc with research context |
| **Mixed** | Combines multiple outputs intelligently |

---

## Quickstart

1.  **Configure**:
    ```bash
    cp .env.example .env
    # Add your LLM configuration to .env (defaults to Ollama)
    ```

2.  **Run Locally**:
    ```bash
    bash scripts/run-local.sh   # Serves on http://localhost:9000
    ```

3.  **Smoke-Test**:
    ```bash
    bash scripts/smoke-test.sh  # Executes a test task and prints results
    ```

---

## Extending the Orchestrator

### 1. Adding a New Tool
To create a new capability (e.g., interacting with a CRM):
1.  Create `sitrep_agent/tools/your_tool.py`.
2.  Inherit from `BaseTool` and implement the `execute` method.
3.  Register your tool in `sitrep_agent/tools/__init__.py`.
4.  The orchestrator will now automatically recognize and utilize the tool when a relevant task is detected.

### 2. Adjusting Task Routing
Modify `handler.py`'s `handler` function to define how your new tool should be invoked. You can update the classification logic in `TASK_ANALYSIS_SYSTEM` or add specific routing rules in the `category` switch-case block.

---

## Contract (The Orchestrator Interface)

SitRep POSTs to `<your-url>/run`.

### Request
```jsonc
{
  "task":     { "id": "...", "title": "...", "description": "..." },
  "summary":  "the meeting summary",
  "attendees":[ { "id": "...", "name": "..." } ],
  "agent":    { "instructions": "...", "tools": [], "model": "..." }
}
```

### Response
```jsonc
{ 
  "artifacts": [ 
    { "type": "markdown" | "html" | "link", "title": "...", "content": "..." } 
  ],
  "logs": ["..."]
}
```

---

## Deployment

Tunnels created by `scripts/tunnel.sh` are for local development only. For production:

1.  **Render**: Push to GitHub and connect via the Render dashboard (uses `render.yaml`).
2.  **Dockerized Hosts**: Use the provided `Dockerfile` and `Procfile` to deploy to platforms like Railway, Fly.io, or AWS ECS.
3.  **Security**: Ensure `SITREP_AGENT_SECRET` is set in your production environment variables to verify incoming requests.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SITREP_AGENT_SECRET` | *(none)* | Agent signing secret from SitRep Studio |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | LLM API endpoint |
| `LLM_API_KEY` | *(none)* | API key (required for hosted providers) |
| `MODEL` | `llama3.2:1b` | Model name |

---

## Credits

This project is built using the [SitRep Agent Starter Kit](https://github.com/SitRepAI/AgentStarterKit) developed by [SitRep AI](https://joinsitrep.com).
