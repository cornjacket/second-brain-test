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


def connect(path) -> _Conn:
    """Open ``path`` with sqlite-vec loaded, via stdlib sqlite3 or apsw."""
    path = str(path)
    if _stdlib_supports_extensions():
        import sqlite3

        conn = sqlite3.connect(path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return _Conn(conn, "sqlite3")

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
    return _Conn(conn, "apsw")
