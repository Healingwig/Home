"""Almacenamiento en SQLite. Sin ORM: son cuatro consultas."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Iterable

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id           TEXT PRIMARY KEY,
    source_url   TEXT NOT NULL,
    status       TEXT NOT NULL,          -- pending | processing | ready | error
    error        TEXT,
    title        TEXT,
    author       TEXT,
    caption      TEXT,
    transcript   TEXT,
    data         TEXT,                   -- receta en JSON
    thumbnail    TEXT,                   -- nombre de fichero dentro de media/
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS recipes_created_at ON recipes (created_at DESC);
CREATE INDEX IF NOT EXISTS recipes_source_url ON recipes (source_url);
"""


def connect() -> sqlite3.Connection:
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def create_recipe(source_url: str) -> str:
    recipe_id = uuid.uuid4().hex[:12]
    now = time.time()
    with connect() as conn:
        conn.execute(
            "INSERT INTO recipes (id, source_url, status, created_at, updated_at)"
            " VALUES (?, ?, 'pending', ?, ?)",
            (recipe_id, source_url, now, now),
        )
    return recipe_id


def update_recipe(recipe_id: str, **fields: Any) -> None:
    if not fields:
        return
    if "data" in fields and not isinstance(fields["data"], (str, type(None))):
        fields["data"] = json.dumps(fields["data"], ensure_ascii=False)
    fields["updated_at"] = time.time()
    columns = ", ".join(f"{key} = ?" for key in fields)
    with connect() as conn:
        conn.execute(
            f"UPDATE recipes SET {columns} WHERE id = ?",
            (*fields.values(), recipe_id),
        )


def get_recipe(recipe_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return _row_to_dict(row) if row else None


def find_by_url(source_url: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM recipes WHERE source_url = ? AND status IN ('pending','processing','ready')"
            " ORDER BY created_at DESC LIMIT 1",
            (source_url,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_recipes(limit: int = 200, query: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM recipes"
    params: list[Any] = []
    if query:
        sql += " WHERE title LIKE ? OR data LIKE ?"
        params += [f"%{query}%", f"%{query}%"]
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def delete_recipe(recipe_id: str) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    return cursor.rowcount > 0


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    if item.get("data"):
        try:
            item["data"] = json.loads(item["data"])
        except json.JSONDecodeError:
            item["data"] = None
    return item


def iter_stale_processing(older_than_seconds: int) -> Iterable[dict[str, Any]]:
    """Recetas que se quedaron a medias (p. ej. reinicio del servidor)."""
    cutoff = time.time() - older_than_seconds
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM recipes WHERE status IN ('pending','processing') AND updated_at < ?",
            (cutoff,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]
