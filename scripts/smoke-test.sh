#!/usr/bin/env bash
# Fire a sample /test request at your locally-running agent (no signature needed
# when SITREP_AGENT_SECRET is unset). Run scripts/run-local.sh first.
set -euo pipefail
curl -s -X POST http://localhost:9000/test \
  -H 'Content-Type: application/json' \
  -d '{
    "task": {"id": "t1", "title": "Draft the launch announcement email", "description": "Cover the new pricing and the June ship date."},
    "summary": "Team agreed to launch the new pricing on June 30 and announce via email and LinkedIn.",
    "attendees": [{"id": "a1", "name": "Owais"}],
    "agent": {"instructions": "", "tools": [], "model": "llama3.1"}
  }' | python3 -m json.tool
