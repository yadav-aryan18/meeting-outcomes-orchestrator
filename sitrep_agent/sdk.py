"""SitRep Agent SDK — request signature verification + a tiny LLM client.

You normally don't edit this file. It gives you:

  * verify_signature(...)  — confirm a /run or /test request really came from
    SitRep (HMAC-SHA256 over "<timestamp>.<body>" using your agent secret).
  * LLM                    — an OpenAI-compatible chat client that defaults to a
    local Ollama, or any BYOK provider via env vars.
  * Ctx / AgentInput       — the objects passed to your handler().
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field
from typing import Any

import asyncio
import httpx
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ── Config (env) ─────────────────────────────────────────────────────
SITREP_AGENT_SECRET = os.getenv("SITREP_AGENT_SECRET", "")
SIGNATURE_MAX_AGE_SECONDS = int(os.getenv("SITREP_SIGNATURE_MAX_AGE", "300"))
# LLM: defaults to local Ollama (free, no signup). BYOK by overriding these.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
MODEL = os.getenv("MODEL", "llama3.2:1b")

# Google AI Studio (Gemini API) support
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_PRIMARY_MODEL = os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3.5-flash-lite")
GEMINI_SECONDARY_MODEL = os.getenv("GEMINI_SECONDARY_MODEL", "gemini-3.1-flash-lite")

# Fallbacks
FALLBACK_MODELS_STR = os.getenv(
    "FALLBACK_MODELS",
    "google/gemma-2-9b-it:free,meta-llama/llama-3.2-3b-instruct:free,mistralai/mistral-7b-instruct:free",
)
FALLBACK_MODELS = [m.strip() for m in FALLBACK_MODELS_STR.split(",") if m.strip()]
FALLBACK_BASE_URL = os.getenv("FALLBACK_BASE_URL", "")
FALLBACK_API_KEY = os.getenv("FALLBACK_API_KEY", "")


def verify_signature(timestamp: str | None, signature: str | None, body: bytes) -> bool:
    """Return True iff the request is a fresh, correctly-signed SitRep call.

    If SITREP_AGENT_SECRET is unset (pure local dev) this returns True so you can
    iterate without wiring a secret. Set the secret in production.
    """
    if not SITREP_AGENT_SECRET:
        return True
    if not timestamp or not signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > SIGNATURE_MAX_AGE_SECONDS:
            return False  # replay guard
    except ValueError:
        return False
    expected = "sha256=" + hmac.new(
        SITREP_AGENT_SECRET.encode(),
        msg=f"{timestamp}.".encode() + body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


class LLM:
    """Minimal OpenAI-compatible chat client supporting Google AI Studio (Gemini),
    OpenAI, OpenRouter, Ollama, and automatic multi-provider fallback."""

    def __init__(self, model: str):
        self.model = model

    def _build_candidates(self) -> list[tuple[str, str, str]]:
        """Construct an ordered list of (base_url, api_key, model) candidates."""
        candidates: list[tuple[str, str, str]] = []

        # If GEMINI_API_KEY is present, prioritize Google AI Studio Gemini models
        if GEMINI_API_KEY:
            candidates.append((GEMINI_BASE_URL, GEMINI_API_KEY, GEMINI_PRIMARY_MODEL))
            candidates.append((GEMINI_BASE_URL, GEMINI_API_KEY, GEMINI_SECONDARY_MODEL))

        # Add configured LLM_BASE_URL & MODEL
        candidates.append((LLM_BASE_URL, LLM_API_KEY, self.model if self.model != "dummy" else GEMINI_PRIMARY_MODEL))

        # Add alternative models on LLM_BASE_URL
        for alt in FALLBACK_MODELS:
            candidates.append((LLM_BASE_URL, LLM_API_KEY, alt))

        # Add optional fallback provider or local Ollama
        if FALLBACK_BASE_URL:
            candidates.append((FALLBACK_BASE_URL, FALLBACK_API_KEY or LLM_API_KEY, "llama3.2:1b"))
        elif LLM_BASE_URL != "http://localhost:11434/v1":
            candidates.append(("http://localhost:11434/v1", "", "llama3.2:1b"))

        # Remove duplicate candidates preserving order
        unique: list[tuple[str, str, str]] = []
        seen = set()
        for c in candidates:
            key = (c[0].rstrip("/"), c[1], c[2])
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    async def complete(self, system: str, prompt: str, temperature: float = 0.7) -> str:
        candidates = self._build_candidates()
        # Ensure target self.model is tried first if explicitly specified and not dummy
        if self.model and self.model != "dummy" and not GEMINI_API_KEY:
            candidates.insert(0, (LLM_BASE_URL, LLM_API_KEY, self.model))

        last_exception = None

        for base_url, api_key, model_name in candidates:
            url = base_url.rstrip("/") + "/chat/completions"
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            payload = {
                "model": model_name,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            }

            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                choices = data.get("choices", [])
                if choices and isinstance(choices, list) and len(choices) > 0:
                    message = choices[0].get("message", {})
                    content = message.get("content") or ""
                    if content.strip():
                        return content
            except httpx.HTTPStatusError as e:
                last_exception = e
                # Retry next candidate on rate-limit (429) or server error (5xx)
                if e.response.status_code in (429, 500, 502, 503, 504):
                    await asyncio.sleep(0.5)
                    continue
            except Exception as e:
                last_exception = e
                continue

        if last_exception:
            raise last_exception
        return ""


@dataclass
class Ctx:
    instructions: str
    tools: list[str]
    llm: LLM
    logs: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        self.logs.append(message)
        print(f"[AGENT] {message}", flush=True)


@dataclass
class AgentInput:
    task: dict[str, Any]
    summary: str
    attendees: list[dict[str, Any]]
    agent: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: dict) -> "AgentInput":
        return cls(
            task=payload.get("task") or {},
            summary=payload.get("summary") or "",
            attendees=payload.get("attendees") or [],
            agent=payload.get("agent") or {},
        )
