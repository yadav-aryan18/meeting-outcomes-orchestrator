# Testing & Verification Guide

This guide explains how to test your SitRep Orchestrator locally and in production.

---

## 🧪 1. Local Testing (Unauthenticated Mode)

When `SITREP_AGENT_SECRET` is left blank in `.env`, the agent operates in unauthenticated local development mode.

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

---

## 🔐 2. Production Authenticated Testing (HMAC Signed Request)

When `SITREP_AGENT_SECRET` is set (e.g. on Render.com), requests must include `X-SitRep-Timestamp` and `X-SitRep-Signature` headers.

### Python Automated Signed Test Script

```python
import time, hmac, hashlib, json, requests

SECRET = "YOUR_SITREP_AGENT_SECRET_HERE"
URL = "https://your-app.onrender.com/test"

payload = {
    "task": {
      "id": "prod_test_1",
      "title": "Fetch financial data and send email",
      "description": "Fetch NVIDIA financial data and email user@example.com"
    },
    "summary": "Meeting context",
    "attendees": [{"name": "Attendee", "email": "user@example.com"}]
}

body = json.dumps(payload).encode("utf-8")
ts = str(int(time.time()))
sig = "sha256=" + hmac.new(SECRET.encode("utf-8"), f"{ts}.".encode("utf-8") + body, hashlib.sha256).hexdigest()

headers = {
    "Content-Type": "application/json",
    "X-SitRep-Timestamp": ts,
    "X-SitRep-Signature": sig
}

resp = requests.post(URL, data=body, headers=headers)
print("HTTP Status:", resp.status_code)
print("Response JSON:", resp.text)
```

---

## 🖥 3. Testing via SitRep Studio Dashboard

1. Register your deployed Render URL (`https://your-app.onrender.com`) in SitRep Studio.
2. In the SitRep Studio Test panel, enter:
   - **Task Title**: `"Fetch financial data for NVIDIA and send email to user@example.com"`
   - **Meeting Summary**: `"The team requested financial records and stock tracking for NVIDIA."`
3. Click **Test Agent**.
4. Open your **Render Dashboard ➔ Web Service ➔ Logs** tab to watch live execution logs.
