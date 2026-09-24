import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol

from mdt.models import Meeting, Memory

_COMPACT = {"ensure_ascii": False, "separators": (",", ":")}


def split_snapshot(payload: str) -> tuple[str, str]:
    """Separate the static dossier from per-event state.

    The case, role contexts and evidence are fixed when a meeting starts but make up
    most of every snapshot. They are stored once per meeting; each event stores only
    the rest. A dynamic record has no ``case`` key, which is how it differs from a
    legacy full snapshot.
    """
    data = json.loads(payload)
    contexts = {name: role.pop("context", {}) for name, role in data.get("roles", {}).items()}
    static = {
        "case": data.pop("case", {}),
        "evidence": data.pop("evidence", []),
        "contexts": contexts,
    }
    return json.dumps(static, **_COMPACT), json.dumps(data, **_COMPACT)  # type: ignore[arg-type]


def join_snapshot(dynamic: str, static: str | None) -> Meeting:
    """Rebuild a meeting from its records; legacy full snapshots load unchanged."""
    data: dict[str, Any] = json.loads(dynamic)
    if "case" not in data:
        if static is None:
            raise ValueError("Meeting state is missing its static dossier record.")
        fixed = json.loads(static)
        data["case"] = fixed["case"]
        data["evidence"] = fixed["evidence"]
        for name, role in data.get("roles", {}).items():
            role["context"] = fixed["contexts"].get(name, {})
    return Meeting.model_validate(data)


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
            "CREATE TABLE IF NOT EXISTS meeting_static "
            "(id TEXT PRIMARY KEY, snapshot TEXT NOT NULL)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS memories "
            "(id TEXT NOT NULL, clinician_id TEXT NOT NULL, snapshot TEXT NOT NULL, "
            "PRIMARY KEY(id, clinician_id))"
        )
        self.connection.commit()
        self._static: dict[str, str] = {}
        self.bytes_written = 0
        """Meeting-record bytes written since start; lets tests bound write volume."""

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
        static, dynamic = split_snapshot(payload)
        changed = self._static.get(meeting_id) != static
        # One transaction: a reader never sees new state without its dossier.
        with self.connection:
            if changed:
                self.connection.execute(
                    "INSERT INTO meeting_static VALUES (?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot",
                    (meeting_id, static),
                )
            self.connection.execute(
                "INSERT INTO meetings VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot",
                (meeting_id, created_at, dynamic),
            )
        if changed:
            self._static[meeting_id] = static
            self.bytes_written += len(static.encode("utf-8"))
        self.bytes_written += len(dynamic.encode("utf-8"))

    def _load(self, row: tuple[str, str] | None) -> Meeting | None:
        if not row:
            return None
        meeting_id, dynamic = row
        fixed = self.connection.execute(
            "SELECT snapshot FROM meeting_static WHERE id=?", (meeting_id,)
        ).fetchone()
        if fixed:
            self._static[meeting_id] = fixed[0]
        return join_snapshot(dynamic, fixed[0] if fixed else None)

    def get(self, meeting_id: str) -> Meeting | None:
        return self._load(
            self.connection.execute(
                "SELECT id, snapshot FROM meetings WHERE id=?", (meeting_id,)
            ).fetchone()
        )

    def latest(self) -> Meeting | None:
        return self._load(
            self.connection.execute(
                "SELECT id, snapshot FROM meetings ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        )

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM meetings").fetchone()[0])

    def ready(self) -> None:
        self.connection.execute("SELECT 1").fetchone()

    def close(self) -> None:
        self.connection.close()
