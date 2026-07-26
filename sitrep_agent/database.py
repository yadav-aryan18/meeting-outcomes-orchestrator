"""
sitrep_agent/database.py

SQLite persistence layer for the Meeting Outcomes Orchestrator.

This module provides a lightweight, zero-config database that stores:
  - Meetings (task, summary, attendees, timestamp)
  - Action items (with owners, deadlines, priorities, status)
  - Attendee profiles (topics discussed, meeting history)
  - Tool execution logs (for debugging and audit trails)

Design principles:
  - Zero external dependencies (uses Python's built-in sqlite3)
  - Async-friendly wrapper around sqlite3
  - Graceful degradation: if DB is unavailable, operations return empty results
  - Schema auto-migration on first use

Usage:
    from sitrep_agent.database import AgentDatabase
    db = AgentDatabase()
    await db.store_meeting(meeting_id="m1", task_title="Q3 Planning", ...)
    items = await db.get_open_action_items_for_owner("Alice")
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Default DB path — can be overridden via env var
DEFAULT_DB_PATH = os.getenv("MEMORY_DB_PATH", "./agent_memory.db")


def _now_iso() -> str:
    """Return current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MeetingRecord:
    """Represents a stored meeting."""
    id: str
    task_title: str
    task_description: str
    summary: str
    attendees: list[dict[str, Any]]
    created_at: str
    action_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ActionItemRecord:
    """Represents a stored action item."""
    id: str
    meeting_id: str
    action: str
    owner: str
    deadline: str
    priority: str
    status: str
    created_at: str


class AgentDatabase:
    """Async-friendly SQLite database for agent memory.

    All public methods are async to match the agent's async architecture,
    even though sqlite3 itself is synchronous. This keeps the interface
    consistent with the rest of the codebase.
    """

    def __init__(self, db_path: str | None = None):
        """Initialize the database.

        Args:
            db_path: Path to SQLite file. Defaults to MEMORY_DB_PATH env var
                     or ./agent_memory.db
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self._ensure_schema()

    def _connection(self):
        """Return a sqlite3 connection with row factory."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        """Create tables if they don't exist. Idempotent."""
        try:
            with self._connection() as conn:
                conn.executescript(_SCHEMA_SQL)
                conn.commit()
        except sqlite3.Error as e:
            # Log but don't crash — the agent should work even without DB
            print(f"[AgentDatabase] Warning: schema init failed: {e}")

    # ── Meeting Operations ──────────────────────────────────────────────

    async def store_meeting(
        self,
        meeting_id: str,
        task_title: str,
        task_description: str,
        summary: str,
        attendees: list[dict[str, Any]],
        action_items: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Store a meeting and its action items.

        Args:
            meeting_id: Unique meeting identifier.
            task_title: The task title from SitRep.
            task_description: The task description from SitRep.
            summary: Meeting summary text.
            attendees: List of attendee dicts.
            action_items: Optional list of extracted action items.

        Returns:
            True on success, False on failure.
        """
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO meetings
                    (id, task_title, task_description, summary, attendees, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        meeting_id,
                        task_title,
                        task_description,
                        summary,
                        json.dumps(attendees),
                        _now_iso(),
                    ),
                )

                # Store action items
                if action_items:
                    for idx, item in enumerate(action_items):
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO action_items
                            (id, meeting_id, action, owner, deadline, priority, status, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                f"{meeting_id}_ai_{idx}",
                                meeting_id,
                                item.get("action", ""),
                                item.get("owner", "[OWNER?]"),
                                item.get("deadline", "[DEADLINE?]"),
                                item.get("priority", "Medium"),
                                item.get("status", "open"),
                                _now_iso(),
                            ),
                        )

                # Update attendee profiles
                for attendee in attendees:
                    name = attendee.get("name", "")
                    if not name:
                        continue
                    # Extract topics from summary (simple heuristic: nouns near attendee name)
                    topics = self._extract_topics_for_attendee(summary, name)
                    conn.execute(
                        """
                        INSERT INTO attendees (id, name, email, first_seen, last_seen, topics)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            last_seen = excluded.last_seen,
                            topics = json_patch(COALESCE(topics, '[]'), excluded.topics)
                        """,
                        (
                            attendee.get("id", name),
                            name,
                            attendee.get("email", ""),
                            _now_iso(),
                            _now_iso(),
                            json.dumps(topics),
                        ),
                    )

                conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"[AgentDatabase] store_meeting failed: {e}")
            return False

    async def get_meeting(self, meeting_id: str) -> MeetingRecord | None:
        """Retrieve a meeting by ID."""
        try:
            with self._connection() as conn:
                row = conn.execute(
                    "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
                ).fetchone()
                if not row:
                    return None
                return MeetingRecord(
                    id=row["id"],
                    task_title=row["task_title"],
                    task_description=row["task_description"],
                    summary=row["summary"],
                    attendees=json.loads(row["attendees"]),
                    created_at=row["created_at"],
                )
        except sqlite3.Error:
            return None

    async def get_recent_meetings(self, limit: int = 10) -> list[MeetingRecord]:
        """Get the most recent meetings."""
        try:
            with self._connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM meetings ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [
                    MeetingRecord(
                        id=r["id"],
                        task_title=r["task_title"],
                        task_description=r["task_description"],
                        summary=r["summary"],
                        attendees=json.loads(r["attendees"]),
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]
        except sqlite3.Error:
            return []

    async def get_meetings_for_attendee(self, name: str, limit: int = 5) -> list[MeetingRecord]:
        """Get recent meetings where a specific attendee was present."""
        try:
            with self._connection() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM meetings
                    WHERE attendees LIKE ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (f'%"name": "{name}"%', limit),
                ).fetchall()
                return [
                    MeetingRecord(
                        id=r["id"],
                        task_title=r["task_title"],
                        task_description=r["task_description"],
                        summary=r["summary"],
                        attendees=json.loads(r["attendees"]),
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]
        except sqlite3.Error:
            return []

    # ── Action Item Operations ──────────────────────────────────────────

    async def get_open_action_items(self, limit: int = 50) -> list[ActionItemRecord]:
        """Get all open action items."""
        try:
            with self._connection() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM action_items
                    WHERE status = 'open'
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                return [self._row_to_action_item(r) for r in rows]
        except sqlite3.Error:
            return []

    async def get_open_action_items_for_owner(self, owner: str) -> list[ActionItemRecord]:
        """Get open action items for a specific owner."""
        try:
            with self._connection() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM action_items
                    WHERE owner LIKE ? AND status = 'open'
                    ORDER BY priority DESC, created_at DESC
                    """,
                    (f"%{owner}%",),
                ).fetchall()
                return [self._row_to_action_item(r) for r in rows]
        except sqlite3.Error:
            return []

    async def update_action_item_status(
        self, item_id: str, status: str
    ) -> bool:
        """Update the status of an action item (open, in_progress, done, blocked)."""
        try:
            with self._connection() as conn:
                conn.execute(
                    "UPDATE action_items SET status = ? WHERE id = ?",
                    (status, item_id),
                )
                conn.commit()
            return True
        except sqlite3.Error:
            return False

    # ── Context Retrieval for LLM ───────────────────────────────────────

    async def get_context_for_task(
        self, task_title: str, attendees: list[dict[str, Any]]
    ) -> str:
        """Build a context string for the LLM from past meetings.

        This is the "memory injection" function. It retrieves relevant
        past meetings and open action items to ground the current task
        in historical context.

        Args:
            task_title: Current task title (used for relevance filtering).
            attendees: Current meeting attendees.

        Returns:
            A markdown-formatted context string, or empty string if no memory.
        """
        parts: list[str] = []

        # Get recent meetings for these attendees
        for attendee in attendees:
            name = attendee.get("name", "")
            if not name:
                continue
            meetings = await self.get_meetings_for_attendee(name, limit=3)
            if meetings:
                parts.append(f"### Past meetings with {name}")
                for m in meetings:
                    parts.append(f"- **{m.task_title}** ({m.created_at[:10]}): {m.summary[:200]}...")

        # Get open action items for these attendees
        for attendee in attendees:
            name = attendee.get("name", "")
            if not name:
                continue
            items = await self.get_open_action_items_for_owner(name)
            if items:
                parts.append(f"### Open action items for {name}")
                for item in items[:5]:
                    parts.append(
                        f"- {item.action} (Due: {item.deadline}, Priority: {item.priority})"
                    )

        if not parts:
            return ""

        return "\n\n".join(["## Historical Context", ""] + parts)

    # ── Internal Helpers ────────────────────────────────────────────────

    def _row_to_action_item(self, row: sqlite3.Row) -> ActionItemRecord:
        return ActionItemRecord(
            id=row["id"],
            meeting_id=row["meeting_id"],
            action=row["action"],
            owner=row["owner"],
            deadline=row["deadline"],
            priority=row["priority"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def _extract_topics_for_attendee(self, summary: str, name: str) -> list[str]:
        """Simple heuristic: extract sentences mentioning the attendee.

        In production, this would use an LLM or NLP library. For the
        hackathon, we use a simple sentence-splitting approach.
        """
        import re
        sentences = re.split(r"(?<=[.!?])\s+", summary)
        topics = []
        for sent in sentences:
            if name.lower() in sent.lower():
                # Extract key nouns (simple heuristic: capitalized words)
                words = re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", sent)
                topics.extend(words)
        return list(set(topics))[:10]  # Deduplicate and limit


# ── Schema ────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    task_title TEXT NOT NULL,
    task_description TEXT,
    summary TEXT NOT NULL,
    attendees TEXT NOT NULL,  -- JSON array
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_items (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL,
    action TEXT NOT NULL,
    owner TEXT,
    deadline TEXT,
    priority TEXT DEFAULT 'Medium',
    status TEXT DEFAULT 'open',
    created_at TEXT NOT NULL,
    FOREIGN KEY (meeting_id) REFERENCES meetings(id)
);

CREATE INDEX IF NOT EXISTS idx_action_items_owner ON action_items(owner);
CREATE INDEX IF NOT EXISTS idx_action_items_status ON action_items(status);
CREATE INDEX IF NOT EXISTS idx_action_items_meeting ON action_items(meeting_id);

CREATE TABLE IF NOT EXISTS attendees (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    topics TEXT  -- JSON array
);

CREATE INDEX IF NOT EXISTS idx_attendees_name ON attendees(name);

CREATE TABLE IF NOT EXISTS tool_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id TEXT,
    tool_name TEXT NOT NULL,
    action TEXT NOT NULL,
    success BOOLEAN,
    details TEXT,
    created_at TEXT NOT NULL
);
"""
