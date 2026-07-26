# Environment Variables & Deployment Reference

Complete reference for `.env` configuration and cloud deployment on Render.com.

---

## ⚙️ Environment Variables Reference

| Variable Name | Default | Required | Description |
|---|---|---|---|
| `SITREP_AGENT_SECRET` | *(blank)* | Production | HMAC signing secret provided by SitRep Studio |
| `SITREP_SIGNATURE_MAX_AGE` | `300` | No | Signature replay window in seconds |
| `GEMINI_API_KEY` | *(blank)* | Recommended | Google AI Studio Gemini API Key |
| `GEMINI_PRIMARY_MODEL` | `gemini-3.5-flash-lite` | No | Primary LLM model |
| `GEMINI_SECONDARY_MODEL` | `gemini-3.1-flash-lite` | No | Failover LLM model |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | No | Secondary OpenAI-compatible endpoint |
| `LLM_API_KEY` | *(blank)* | Optional | API Key for secondary LLM provider |
| `MODEL` | `llama3.2:1b` | No | Model name for secondary LLM |
| `MCP_SERVER_URLS` | *(blank)* | Optional | Comma-separated remote MCP server URLs |
| `MCP_API_TOKEN` | *(blank)* | Optional | Bearer token for remote MCP servers |
| `MEMORY_DB_PATH` | `./agent_memory.db` | No | SQLite database file path |
| `VECTOR_DB_PATH` | `./vector_memory_store.json` | No | Vector RAG database file path |

---

## 🌐 Deploying to Render.com

1. Create a **Web Service** on [Render Dashboard](https://dashboard.render.com).
2. Connect your GitHub repository.
3. Configure settings:
   - **Runtime**: Python 3.10+
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python -m uvicorn app:app --host 0.0.0.0 --port $PORT`
4. Under the **Environment** tab, set all key-value pairs.
   > **CRITICAL**: Do NOT include quotation marks (`"`) around variable values in the Render Dashboard UI.

---

## 🔐 Security Notes

- Keep `.env` listed in `.gitignore`. Never commit API keys or secret tokens to public repositories.
- Use `SITREP_AGENT_SECRET` in production to prevent unauthenticated public HTTP access to your agent endpoints.
