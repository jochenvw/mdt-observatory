import sqlite3
from pathlib import Path
from typing import Protocol

from mdt.models import Meeting, Memory


class Persistence(Protocol):
    """Synchronous storage contract; the engine calls it from one worker thread."""

    def save(self, meeting: Meeting) -> None: ...
    def save_snapshot(self, meeting_id: str, created_at: str, payload: str) -> None: ...
    def get(self, meeting_id: str) -> Meeting | None: ...
    def latest(self) -> Meeting | None: ...
    def count(self) -> int: ...
    def ready(self) -> None: ...
    def memories(
        self, seeds: list[Memory], clinician_id: str = "demo-clinician"
    ) -> list[Memory]: ...
    def save_memory(self, memory: Memory) -> None: ...
    def close(self) -> None: ...


class Store:
    """One writer, atomic snapshots; DELETE journal supports the Azure Files mount."""

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.connection.execute("PRAGMA journal_mode=DELETE")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS meetings "
            "(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, snapshot TEXT NOT NULL)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS memories "
            "(id TEXT NOT NULL, clinician_id TEXT NOT NULL, snapshot TEXT NOT NULL, "
            "PRIMARY KEY(id, clinician_id))"
        )
        self.connection.commit()

    def memories(self, seeds: list[Memory], clinician_id: str = "demo-clinician") -> list[Memory]:
        with self.connection:
            for memory in seeds:
                self.connection.execute(
                    "INSERT OR IGNORE INTO memories VALUES (?, ?, ?)",
                    (memory.id, memory.clinician_id, memory.model_dump_json()),
                )
        rows = self.connection.execute(
            "SELECT snapshot FROM memories WHERE clinician_id=? ORDER BY id", (clinician_id,)
        ).fetchall()
        memories = [Memory.model_validate_json(row[0]) for row in rows]
        for memory in memories:
            if memory.status != "FORGOTTEN":
                memory.status = "AVAILABLE"
        return memories

    def save_memory(self, memory: Memory) -> None:
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE memories SET snapshot=? WHERE id=? AND clinician_id=?",
                (memory.model_dump_json(), memory.id, memory.clinician_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Cannot update a memory that has not been initialized.")

    def save(self, meeting: Meeting) -> None:
        self.save_snapshot(meeting.id, meeting.created_at, meeting.model_dump_json())

    def save_snapshot(self, meeting_id: str, created_at: str, payload: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO meetings VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot",
                (meeting_id, created_at, payload),
            )

    def get(self, meeting_id: str) -> Meeting | None:
        row = self.connection.execute(
            "SELECT snapshot FROM meetings WHERE id=?", (meeting_id,)
        ).fetchone()
        return Meeting.model_validate_json(row[0]) if row else None

    def latest(self) -> Meeting | None:
        row = self.connection.execute(
            "SELECT snapshot FROM meetings ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return Meeting.model_validate_json(row[0]) if row else None

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM meetings").fetchone()[0])

    def ready(self) -> None:
        self.connection.execute("SELECT 1").fetchone()

    def close(self) -> None:
        self.connection.close()
