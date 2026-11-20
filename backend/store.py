from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_COLUMNS = (
    "id", "filename", "folder", "size_bytes", "file_type", "status", "progress_done",
    "progress_total", "error", "chunk_count", "replaces_id", "created_at", "updated_at",
)
_UPDATABLE = frozenset(_COLUMNS) - {"id", "created_at", "updated_at"}
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init(path: str | Path) -> None:
    global _conn
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                folder TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                file_type TEXT NOT NULL CHECK (file_type IN ('pdf','docx','xlsx')),
                status TEXT NOT NULL CHECK (status IN ('indexing','ready','error')),
                progress_done INTEGER NOT NULL DEFAULT 0,
                progress_total INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                replaces_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        _conn.commit()


def _query(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _conn.execute(sql, args).fetchall()]


def _write(sql: str, args: tuple = ()) -> None:
    with _lock, _conn:
        _conn.execute(sql, args)


def create(id: str, filename: str, folder: str, size_bytes: int, file_type: str,
           replaces_id: str | None = None) -> dict:
    now = _now()
    _write(
        "INSERT INTO documents (id, filename, folder, size_bytes, file_type, status, replaces_id,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'indexing', ?, ?, ?)",
        (id, filename, folder, size_bytes, file_type, replaces_id, now, now),
    )
    return get(id)


def get(id: str) -> dict | None:
    rows = _query("SELECT * FROM documents WHERE id = ?", (id,))
    return rows[0] if rows else None


def list(folder: str | None = None) -> list[dict]:
    order = " ORDER BY created_at DESC, rowid DESC"
    if folder is None:
        return _query("SELECT * FROM documents" + order)
    return _query("SELECT * FROM documents WHERE folder = ?" + order, (folder,))


def folders() -> list[dict]:
    return _query("SELECT folder AS name, COUNT(*) AS count FROM documents GROUP BY folder ORDER BY folder")


def update(id: str, **fields) -> None:
    bad = set(fields) - _UPDATABLE
    if bad:
        raise ValueError(f"unknown columns: {sorted(bad)}")
    fields["updated_at"] = _now()
    sets = ", ".join(f"{c} = ?" for c in fields)
    _write(f"UPDATE documents SET {sets} WHERE id = ?", (*fields.values(), id))


def delete(id: str) -> None:
    _write("DELETE FROM documents WHERE id = ?", (id,))


def find_ready(folder: str, filename: str) -> dict | None:
    rows = _query("SELECT * FROM documents WHERE folder = ? AND filename = ? AND status = 'ready'", (folder, filename))
    return rows[0] if rows else None


def list_indexing() -> list[dict]:
    return _query("SELECT * FROM documents WHERE status = 'indexing' ORDER BY created_at, rowid")
