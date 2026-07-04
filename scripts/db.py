"""SQLite connection with the ``sqlite-vec`` extension loaded.

Prefers the stdlib ``sqlite3`` when its build supports loadable extensions, and
falls back to ``apsw`` (which bundles an extension-capable SQLite) when it does
not — common on macOS, where the system Python and the ``sqlite3`` CLI are built
without extension loading. Callers use a single uniform ``connect()`` and a thin
connection wrapper so they never have to care which backend is active.
"""
from __future__ import annotations

import sqlite_vec


def _stdlib_supports_extensions() -> bool:
    import sqlite3

    conn = sqlite3.connect(":memory:")
    try:
        return hasattr(conn, "enable_load_extension")
    finally:
        conn.close()


class _Conn:
    """Minimal uniform wrapper over a ``sqlite3`` or ``apsw`` connection."""

    def __init__(self, raw, kind: str):
        self._raw = raw
        self._kind = kind

    def execute(self, sql: str, params=()):
        """Run a statement; return an iterable of result rows (tuples)."""
        if self._kind == "apsw":
            cur = self._raw.cursor()
            cur.execute(sql, params)
            return cur
        return self._raw.execute(sql, params)

    def commit(self) -> None:
        if self._kind == "sqlite3":
            self._raw.commit()
        # apsw autocommits outside explicit transactions

    def close(self) -> None:
        self._raw.close()


def _tune(conn: _Conn) -> _Conn:
    """Apply the concurrency PRAGMAs (OQ-5 layer 1), set per connection.

    ``journal_mode=WAL`` lets many readers and the single writer run concurrently
    (a query no longer blocks — or is blocked by — a cache write). ``busy_timeout``
    makes a contended open **wait** briefly rather than fail immediately: SQLite's
    default timeout is 0, so without this a reader hitting a mid-write DB errors
    with ``SQLITE_BUSY`` instead of retrying. WAL is persisted on the DB file;
    busy_timeout is a per-connection setting — both are re-applied on every open so
    a freshly-(re)built cache is always tuned.
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")  # 5s
    return conn


def connect(path) -> _Conn:
    """Open ``path`` with sqlite-vec loaded, via stdlib sqlite3 or apsw."""
    path = str(path)
    if _stdlib_supports_extensions():
        import sqlite3

        conn = sqlite3.connect(path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return _tune(_Conn(conn, "sqlite3"))

    try:
        import apsw
    except ImportError as exc:
        raise SystemExit(
            "This Python's sqlite3 cannot load extensions and `apsw` is not "
            "installed. Run `pip install -r requirements.txt`."
        ) from exc

    conn = apsw.Connection(path)
    conn.enableloadextension(True)
    conn.loadextension(sqlite_vec.loadable_path())
    conn.enableloadextension(False)
    return _tune(_Conn(conn, "apsw"))
