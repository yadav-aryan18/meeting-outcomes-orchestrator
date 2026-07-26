# Meeting Outcomes Orchestrator

An intelligent post-meeting AI agent for the [SitRep](https://joinsitrep.com) Agent Marketplace. Unlike simple prompt-based agents, this agent uses an **intelligent router** to analyze meeting tasks and orchestrate specialized tools in parallel — producing structured action items, research briefs, emails, slide decks, calendar events, Slack posts, Notion pages, and Jira tickets.

## What It Does

When a meeting ends and a task is created, the agent:

1. **Retrieves** historical context from SQLite memory (past meetings, open action items)
2. **Analyzes** the task to understand what output is needed
3. **Routes** to the right combination of tools
4. **Executes** tools in parallel (web search + Wikipedia + Slack + Notion + Jira)
5. **Synthesizes** all outputs into polished, multi-format artifacts
6. **Persists** the meeting and action items to memory for future context
7. **Returns** markdown + HTML + calendar links + external confirmations

## Supported Task Types (Auto-Detected)

| Task Type | What It Produces | External Integrations |
|---|---|---|
| **Follow-up Email** | Personalized email using attendee names | + Slack notification |
| **Research Brief** | Multi-source research with citations | + Notion page |
| **Action Items** | Structured table with owners, deadlines, priorities | + Slack + Jira + Notion |
| **Project Plan** | Action items + timeline + calendar + narrative | + Jira + Notion + Slack |
| **Slide Deck** | Numbered outline + HTML preview | — |
| **Calendar Event** | Real Google Calendar event (or template link) | Google Calendar API |
| **Documentation** | PRD, spec, or technical doc with research | + Notion |
| **Mixed** | Combines multiple outputs intelligently | All available |

## Architecture

```
sitrep_agent/
├── sdk.py              # SitRep SDK (signature verify + LLM client)
├── database.py         # SQLite memory layer (meetings, action items, attendees)
└── tools/
    ├── __init__.py     # Tool registry
    ├── base.py         # Abstract BaseTool class
    ├── web_search.py   # DuckDuckGo search (no API key)
    ├── web_scraper.py  # URL content extraction
    ├── wikipedia.py    # Wikipedia REST API
    ├── calendar.py     # Google Calendar template links (no auth)
    ├── calendar_api.py # Google Calendar API (real events)
    ├── email.py        # Attendee-personalized email drafter
    ├── slides.py       # Slide outline + HTML preview
    ├── action_items.py # Structured task extractor
    ├── research.py     # Multi-source synthesizer
    ├── memory.py       # SQLite memory wrapper
    ├── slack.py        # Slack messenger
    ├── notion.py       # Notion page creator
    └── jira.py         # Jira ticket creator

handler.py              # Intelligent orchestrator (routes + executes tools)
app.py                  # HTTP wrapper (SitRep contract)
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure (optional — agent works without external integrations)
cp .env.example .env
# Edit .env to add your Slack, Notion, Jira, or Google Calendar credentials

# 3. Run locally
bash scripts/run-local.sh   # http://localhost:9000

# 4. Smoke test (new terminal)
bash scripts/smoke-test.sh
```

## External Integrations (All Optional)

The agent works out of the box with zero configuration. External integrations are **opt-in**:

| Integration | Setup | Env Vars |
|---|---|---|
| **SQLite Memory** | Zero config | `MEMORY_DB_PATH` (optional) |
| **Slack** | Webhook URL or Bot Token | `SLACK_WEBHOOK_URL` or `SLACK_BOT_TOKEN` |
| **Notion** | Integration Token + Database ID | `NOTION_TOKEN`, `NOTION_DATABASE_ID` |
| **Jira** | API Token + Project Key | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` |
| **Google Calendar** | Service Account JSON | `GOOGLE_CALENDAR_CREDENTIALS_JSON` or `GOOGLE_CALENDAR_CREDENTIALS_PATH` |

## Deploy

```bash
# Push to GitHub, then deploy to Render (free tier)
# render.yaml is included — just set SITREP_AGENT_SECRET in the dashboard
```

## Adding New Tools

The tool system is fully modular:

1. Create `sitrep_agent/tools/your_tool.py`
2. Inherit from `BaseTool`, implement `execute()`
3. Register in `sitrep_agent/tools/__init__.py`
4. Add routing logic in `handler.py`

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SITREP_AGENT_SECRET` | *(none)* | Agent signing secret from SitRep Studio |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | LLM API endpoint |
| `LLM_API_KEY` | *(none)* | API key (required for hosted providers) |
| `MODEL` | `llama3.2:1b` | Model name |
| `MEMORY_DB_PATH` | `./agent_memory.db` | SQLite database path |
| `SLACK_WEBHOOK_URL` | *(none)* | Slack incoming webhook |
| `SLACK_BOT_TOKEN` | *(none)* | Slack bot OAuth token |
| `NOTION_TOKEN` | *(none)* | Notion integration token |
| `NOTION_DATABASE_ID` | *(none)* | Notion database ID |
| `JIRA_BASE_URL` | *(none)* | Jira Cloud base URL |
| `JIRA_EMAIL` | *(none)* | Jira account email |
| `JIRA_API_TOKEN` | *(none)* | Jira API token |
| `JIRA_PROJECT_KEY` | *(none)* | Default Jira project key |
| `GOOGLE_CALENDAR_CREDENTIALS_JSON` | *(none)* | Base64-encoded service account JSON |

## License

MIT
