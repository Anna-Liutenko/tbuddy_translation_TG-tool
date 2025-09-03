"""Minimal DB abstraction layer.

This module centralizes database access for ChatSettings. It currently implements
an SQLite-backed implementation only. The API is intentionally small and
stable so switching to Postgres or another backend later is easy.

Behavior:
- If the environment variable `DATABASE_URL` is set, this module will raise
  NotImplementedError to avoid accidental usage until a production backend is
  implemented. This keeps the runtime behavior safe for the current deploy.

Usage (future): import this module and call `get_chat_settings`, `upsert_chat_settings`.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Optional, Dict, List

_SQLITE_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), 'chat_settings.db'))
DATABASE_URL = os.getenv('DATABASE_URL')


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS ChatSettings (
            chat_id TEXT PRIMARY KEY,
            language_codes TEXT,
            language_names TEXT,
            updated_at TEXT
        )
        '''
    )
    conn.commit()


def _get_sqlite_conn(sqlite_file: Optional[str] = None) -> sqlite3.Connection:
    path = sqlite_file or _SQLITE_DB
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    _ensure_table(conn)
    return conn


def init_db(sqlite_file: Optional[str] = None) -> None:
    """Ensure DB file and table exist (SQLite only)."""
    if DATABASE_URL:
        raise NotImplementedError("DATABASE_URL is set but no non-SQLite backend is implemented yet.")
    conn = _get_sqlite_conn(sqlite_file)
    conn.close()


def get_chat_settings(chat_id: str, sqlite_file: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Return a dict for the chat_id or None if not found."""
    if DATABASE_URL:
        raise NotImplementedError("Postgres backend not implemented - remove DATABASE_URL or implement backend.")
    conn = _get_sqlite_conn(sqlite_file)
    cur = conn.execute('SELECT chat_id, language_codes, language_names, updated_at FROM ChatSettings WHERE chat_id = ?', (str(chat_id),))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {k: row[k] for k in row.keys()}


def upsert_chat_settings(chat_id: str, language_codes: str, language_names: str, updated_at: str, sqlite_file: Optional[str] = None) -> None:
    """Insert or replace the chat settings row.

    This mirrors the current SQLite behaviour used elsewhere in the project.
    """
    if DATABASE_URL:
        raise NotImplementedError("Postgres backend not implemented - remove DATABASE_URL or implement backend.")
    conn = _get_sqlite_conn(sqlite_file)
    conn.execute(
        'REPLACE INTO ChatSettings (chat_id, language_codes, language_names, updated_at) VALUES (?, ?, ?, ?)',
        (str(chat_id), language_codes, language_names, updated_at),
    )
    conn.commit()
    conn.close()


def dump_all(sqlite_file: Optional[str] = None) -> List[Dict[str, str]]:
    """Return all rows as list of dicts."""
    if DATABASE_URL:
        raise NotImplementedError("Postgres backend not implemented - remove DATABASE_URL or implement backend.")
    conn = _get_sqlite_conn(sqlite_file)
    cur = conn.execute('SELECT chat_id, language_codes, language_names, updated_at FROM ChatSettings')
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_chat_settings(chat_id: str, sqlite_file: Optional[str] = None) -> None:
    """Delete the chat settings row for a given chat_id."""
    if DATABASE_URL:
        raise NotImplementedError("Postgres backend not implemented - remove DATABASE_URL or implement backend.")
    conn = _get_sqlite_conn(sqlite_file)
    conn.execute('DELETE FROM ChatSettings WHERE chat_id = ?', (str(chat_id),))
    conn.commit()
    conn.close()


if __name__ == '__main__':
    # quick smoke: log rows instead of printing to stdout
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger('db')
    init_db()
    for r in dump_all():
        log.info("row=%s", r)
