"""
sitrep_agent/tools/vector_memory.py

Vector Memory / RAG tool for semantic search across historical meetings.

Stores meeting summaries, decisions, and action items as vectorized chunks
in disk-backed storage to enable RAG semantic search.

Features:
  - Disk-backed JSON vector database at VECTOR_DB_PATH
  - Sub-word & term frequency vectorizer with cosine similarity scoring
  - Automatic indexing when meetings complete
  - Returns relevance scores, dates, and cited meeting snippets

Setup & Env Vars:
  VECTOR_DB_PATH — File path for local vector database (default: ./vector_memory_store.json)

Usage:
    result = await VectorMemoryTool(ctx).execute(
        operation="search",
        query="What did we decide about pricing in Q2?"
    )
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult, ToolSchema

DEFAULT_VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "./vector_memory_store.json")


def _tokenize(text: str) -> list[str]:
    """Extract normalized word tokens for vector embedding."""
    return re.findall(r"\b[a-z0-9]{2,}\b", text.lower())


def _build_vector(text: str) -> dict[str, float]:
    """Build a term-frequency vector normalized to unit length."""
    tokens = _tokenize(text)
    if not tokens:
        return {}
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1

    # Compute Euclidean norm
    length = math.sqrt(sum(c * c for c in counts.values()))
    if length == 0:
        return {}
    return {k: v / length for k, v in counts.items()}


def _cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    """Compute cosine similarity between two term-frequency vectors."""
    if not vec1 or not vec2:
        return 0.0
    # Iterate over smaller dict for speed
    if len(vec1) > len(vec2):
        vec1, vec2 = vec2, vec1
    return sum(val * vec2.get(key, 0.0) for key, val in vec1.items())


class VectorMemoryTool(BaseTool):
    """Semantic vector memory and RAG retrieval across past meetings."""

    name = "vector_memory"
    description = (
        "Semantic search across past meeting summaries, decisions, and action items. "
        "Uses vector embeddings to find relevant historical context. "
        "Answers questions like 'What did we decide about pricing?' or 'Who was assigned to the launch?'"
    )

    def __init__(self, ctx: Any = None, db_path: str | None = None):
        super().__init__(ctx=ctx)
        self.db_path = Path(db_path or DEFAULT_VECTOR_DB_PATH)
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Create vector store file if missing."""
        if not self.db_path.exists():
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self.db_path.write_text(json.dumps({"documents": []}, indent=2), encoding="utf-8")
            except Exception as e:
                self.log(f"vector_memory: failed to create db at {self.db_path} — {e}")

    def _load_documents(self) -> list[dict[str, Any]]:
        """Load stored document vectors."""
        try:
            if self.db_path.exists():
                data = json.loads(self.db_path.read_text(encoding="utf-8"))
                return data.get("documents", [])
        except Exception as e:
            self.log(f"vector_memory: error loading db — {e}")
        return []

    def _save_documents(self, documents: list[dict[str, Any]]) -> bool:
        """Save document vectors to disk."""
        try:
            self.db_path.write_text(json.dumps({"documents": documents}, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            self.log(f"vector_memory: error saving db — {e}")
            return False

    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name="vector_memory",
            description=(
                "Perform semantic RAG search across historical meetings or index a new meeting summary. "
                "Use this to retrieve decisions, context, or action items from previous meetings."
            ),
            parameters={
                "operation": {
                    "type": "string",
                    "description": "One of: search, store.",
                    "default": "search",
                },
                "query": {
                    "type": "string",
                    "description": "Semantic search query string (for search operation).",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of top matching meeting chunks to return (default 3).",
                    "default": 3,
                },
                "meeting_data": {
                    "type": "object",
                    "description": "Meeting record dict with title, summary, date, action_items (for store operation).",
                },
            },
            required=["operation"],
            returns="Dict with 'results' list, 'count', and Markdown summary.",
        )

    async def execute(
        self,
        operation: str = "search",
        query: str = "",
        top_k: int = 3,
        meeting_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute a vector memory operation (search or store).

        Args:
            operation: "search" or "store".
            query: Search query text.
            top_k: Number of results to return.
            meeting_data: Dict with meeting info to index.

        Returns:
            ToolResult with search results or store confirmation.
        """
        query = query or kwargs.get("topic") or kwargs.get("text") or ""
        meeting_data = meeting_data or kwargs.get("input_data")

        if operation == "store":
            return await self._store_document(meeting_data)
        else:
            if not query:
                return ToolResult(
                    success=False,
                    data={},
                    summary="Query string is required for vector_memory search.",
                    error="Missing query parameter.",
                )
            return await self._search_documents(query, top_k)

    async def _store_document(self, meeting_data: dict[str, Any] | None) -> ToolResult:
        """Vectorize and store a meeting summary in the vector database."""
        if not meeting_data:
            return ToolResult(success=False, error="No meeting_data provided for vector store.")

        task = meeting_data.get("task", {}) if isinstance(meeting_data, dict) else {}
        title = task.get("title") or meeting_data.get("title") or "Untitled Meeting"
        summary = meeting_data.get("summary") or ""
        meeting_id = task.get("id") or meeting_data.get("id") or f"m_{int(datetime.now().timestamp())}"
        date_str = meeting_data.get("created_at") or datetime.now(timezone.utc).isoformat()[:10]

        content = f"Title: {title}\nSummary: {summary}"
        vector = _build_vector(content)

        docs = self._load_documents()

        # Update existing document or append
        existing_idx = next((i for i, d in enumerate(docs) if d.get("id") == meeting_id), -1)
        doc_entry = {
            "id": meeting_id,
            "title": title,
            "summary": summary,
            "date": date_str,
            "content": content,
            "vector": vector,
        }

        if existing_idx >= 0:
            docs[existing_idx] = doc_entry
        else:
            docs.append(doc_entry)

        success = self._save_documents(docs)

        if success:
            self.log(f"vector_memory: indexed meeting '{title}' (total docs={len(docs)})")
            return ToolResult(
                success=True,
                data={"id": meeting_id, "title": title, "indexed": True},
                summary=f"Meeting '{title}' indexed into vector memory.",
            )
        else:
            return ToolResult(success=False, error="Failed to save document to vector store.")

    async def _search_documents(self, query: str, top_k: int) -> ToolResult:
        """Perform cosine similarity vector search against stored meetings."""
        self.log(f"vector_memory: searching for \"{query[:50]}...\"")

        query_vec = _build_vector(query)
        if not query_vec:
            return ToolResult(
                success=True,
                data={"results": [], "count": 0},
                summary="Query produced empty vector tokens.",
            )

        docs = self._load_documents()
        if not docs:
            return ToolResult(
                success=True,
                data={"results": [], "count": 0},
                summary="Vector memory database is empty.",
            )

        scored: list[dict[str, Any]] = []
        for doc in docs:
            doc_vec = doc.get("vector", {})
            score = _cosine_similarity(query_vec, doc_vec)
            if score > 0.05:  # Relevance threshold
                scored.append({
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "summary": doc.get("summary"),
                    "date": doc.get("date"),
                    "score": round(score, 4),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        top_results = scored[:top_k]

        if not top_results:
            return ToolResult(
                success=True,
                data={"results": [], "count": 0},
                summary=f"No vector memory matches found for query: \"{query}\"",
            )

        # Build Markdown summary artifact
        lines = [f"### 🔍 Vector Memory RAG Results for: *{query}*\n"]
        for idx, res in enumerate(top_results, 1):
            lines.append(
                f"**{idx}. {res['title']}** (Date: `{res['date']}`, Score: `{res['score']}`)\n"
                f"> {res['summary'][:300]}...\n"
            )

        md = "\n".join(lines)

        return ToolResult(
            success=True,
            data={"results": top_results, "count": len(top_results)},
            summary=f"Retrieved {len(top_results)} vector memory result(s) for \"{query}\".",
            artifacts=[
                {
                    "type": "markdown",
                    "title": f"Vector RAG: {query}",
                    "content": md,
                }
            ],
        )
