# Example agents

Working, copy-over handlers to start from. **Copy any one over `handler.py`** in the
repo root, keeping the function name `handler` — then run `bash scripts/run-local.sh`
and `bash scripts/smoke-test.sh` to see it produce artifacts.

```bash
cp examples/followup_email_handler.py handler.py   # then run + smoke-test
```

Each one is small on purpose and demonstrates a different capability of the SDK
(`sitrep_agent/sdk.py`):

| File | Technique it shows | Artifact types |
|---|---|---|
| `slide_outline_handler.py` | multi-step LLM chain (outline → HTML) | markdown + html |
| `followup_email_handler.py` | personalizing with `input.attendees` | markdown |
| `research_brief_handler.py` | calling an external API (httpx) + `ctx.log()` | markdown |
| `calendar_link_handler.py` | returning a `link` artifact (a URL) | markdown + link |

Mix and match — chain LLM calls, hit external APIs, and emit multiple artifacts
however your agent needs. The only hard rules are the signature
(`async def handler(input: AgentInput, ctx: Ctx) -> dict`) and the return shape
(`{"artifacts": [{"type", "title", "content"}]}`), both covered in the main
[README](../README.md#the-contract).
