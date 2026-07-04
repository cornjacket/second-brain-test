#!/usr/bin/env python3
"""doctor.py — is this brain ready to rely on?

Two tiers of check, then an optional ``--repair``:

1. **Health / preflight** — the runtime this brain needs to actually work: the
   ``sqlite-vec`` cache extension (or the ``apsw`` fallback), a readable
   ``config/embedder.toml``, and — when the active backend is ``ollama`` — a
   reachable Ollama server with the embedding model pulled.

2. **Consistency** — the three layers that must agree for search to be trusted::

       vault note (.md)  ──embed──▶  sidecar (.embed.json)  ──hydrate──▶  db row

   Every PARA note should have a sidecar, every sidecar a matching note and a
   cache row, and every row a sidecar — with all sidecars stamped by the active
   backend (the same-model invariant). A note present on disk but missing from
   the cache is exactly the drift this command exists to catch.

``--repair`` reconciles what it safely can: drop orphan sidecars, (re)embed notes
whose sidecar is missing / wrong-dim / wrong-backend, then rebuild the cache from
the reconciled sidecars. Re-embedding uses the active backend, so ``--repair``
needs that backend live (e.g. Ollama up) when notes actually need embedding.

Exit ``0`` = healthy & consistent; non-zero = at least one problem remains.

    python3 scripts/doctor.py
    python3 scripts/doctor.py --repair
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
VAULT_DIR = REPO_ROOT / "vault"
DB_PATH = REPO_ROOT / "data" / "brain.db"
CONFIG_PATH = REPO_ROOT / "config" / "embedder.toml"
PARA_ROOTS = ("projects", "areas", "resources", "archive")

sys.path.insert(0, str(SCRIPTS))
from embedder import EMBED_DIM, backend_id, backend_name  # noqa: E402
import embed_staged as es  # noqa: E402  (write_sidecar / sidecar_path helpers)


class Report:
    """Console reporter that also tallies problems for the exit code."""

    def __init__(self) -> None:
        self.problems = 0

    def ok(self, msg: str) -> None:
        print(f"  ok    {msg}")

    def fail(self, msg: str) -> None:
        print(f"  FAIL  {msg}")
        self.problems += 1

    def info(self, msg: str) -> None:
        print(f"        {msg}")


# --------------------------------------------------------------------------- #
# Tier 1 — health / preflight
# --------------------------------------------------------------------------- #

def _stdlib_supports_extensions() -> bool:
    # Inlined from db.py rather than imported: db.py imports sqlite_vec at module
    # load, which would crash the very dep check that must survive its absence.
    import sqlite3

    conn = sqlite3.connect(":memory:")
    try:
        return hasattr(conn, "enable_load_extension")
    finally:
        conn.close()


def check_deps(rep: Report) -> None:
    try:
        import sqlite_vec  # noqa: F401
        rep.ok("sqlite-vec importable")
    except ImportError:
        rep.fail("sqlite-vec not installed — run `pip install -r requirements.txt`")

    # apsw is only *needed* when the stdlib sqlite3 can't load extensions.
    if _stdlib_supports_extensions():
        rep.info("stdlib sqlite3 loads extensions; apsw fallback not required")
    else:
        try:
            import apsw  # noqa: F401
            rep.ok("apsw fallback available (stdlib sqlite3 can't load extensions)")
        except ImportError:
            rep.fail("stdlib sqlite3 can't load extensions and apsw missing — "
                     "run `pip install -r requirements.txt`")


def check_config(rep: Report) -> str:
    if not CONFIG_PATH.exists():
        rep.info("no config/embedder.toml — defaulting to the 'test' backend")
    rep.ok(f"active embedder backend: {backend_id()}")
    return backend_name()


def check_ollama(rep: Report) -> None:
    import os
    import urllib.error
    import urllib.request

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("SECOND_BRAIN_EMBED_MODEL", "nomic-embed-text")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as resp:
            tags = json.loads(resp.read())
    except (urllib.error.URLError, OSError) as exc:
        rep.fail(f"Ollama unreachable at {host} ({exc}) — is `ollama serve` running?")
        return
    rep.ok(f"Ollama reachable at {host}")

    # A pulled model is listed as e.g. 'nomic-embed-text:latest'; match the base.
    names = {m.get("name", "") for m in tags.get("models", [])}
    if any(n == model or n.split(":")[0] == model for n in names):
        rep.ok(f"embedding model '{model}' is pulled")
    else:
        rep.fail(f"embedding model '{model}' not pulled — run `ollama pull {model}`")


# --------------------------------------------------------------------------- #
# Tier 2 — consistency (vault ↔ sidecar ↔ db)
# --------------------------------------------------------------------------- #

def para_notes() -> set[str]:
    """Every indexable PARA note, as a repo-relative posix path."""
    notes: set[str] = set()
    for root in PARA_ROOTS:
        for p in (VAULT_DIR / root).rglob("*.md"):
            notes.add(p.relative_to(REPO_ROOT).as_posix())
    return notes


def all_sidecars() -> list[Path]:
    out: list[Path] = []
    for root in PARA_ROOTS:
        out.extend((VAULT_DIR / root).rglob(".*.embed.json"))
    return out


def note_for_sidecar(sc: Path) -> str:
    """Map ``…/.<stem>.embed.json`` back to its note ``…/<stem>.md``."""
    stem = sc.name[len("."):-len(".embed.json")]
    return (sc.parent / f"{stem}.md").relative_to(REPO_ROOT).as_posix()


def db_source_files() -> set[str] | None:
    """Cache rows keyed by source_file; ``None`` if the db file is absent."""
    if not DB_PATH.exists():
        return None
    from db import connect

    db = connect(DB_PATH)
    try:
        try:
            return {row[0] for row in db.execute("SELECT source_file FROM notes")}
        except Exception:  # noqa: BLE001 — sqlite3/apsw differ; table not created yet
            return set()
    finally:
        db.close()


def scan() -> dict:
    """Pure scan of the three layers; returns the discrepancy sets (no output)."""
    notes = para_notes()
    sidecars = {note_for_sidecar(sc): sc for sc in all_sidecars()}
    active = backend_id()

    bad_dim: set[str] = set()
    mixed: set[str] = set()
    unreadable: set[str] = set()
    for note, sc in sidecars.items():
        try:
            payload = json.loads(sc.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            unreadable.add(note)
            continue
        if len(payload.get("vector", [])) != EMBED_DIM:
            bad_dim.add(note)
        if payload.get("type") != active:
            mixed.add(note)

    notes_wo_sidecar = notes - set(sidecars)
    orphan_sidecars = set(sidecars) - notes
    expected = notes & set(sidecars)  # a note is cacheable once it has a sidecar

    rows = db_source_files()
    if rows is None:
        missing_from_db, stale_in_db = expected, set()
    else:
        missing_from_db = expected - rows
        stale_in_db = rows - expected

    return {
        "notes": notes,
        "sidecars": sidecars,
        "active": active,
        "notes_wo_sidecar": notes_wo_sidecar,
        "orphan_sidecars": orphan_sidecars,
        "missing_from_db": missing_from_db,
        "stale_in_db": stale_in_db,
        "mixed": mixed,
        "bad_dim": bad_dim,
        "unreadable": unreadable,
        "db_missing": rows is None,
    }


def report_consistency(rep: Report, st: dict) -> None:
    for note in sorted(st["notes_wo_sidecar"]):
        rep.fail(f"note not embedded (no sidecar): {note}")
    for note in sorted(st["orphan_sidecars"]):
        rep.fail(f"orphan sidecar (note gone): "
                 f"{st['sidecars'][note].relative_to(REPO_ROOT).as_posix()}")
    if st["db_missing"]:
        # The whole cache is gone; one line says it all — don't also flag every
        # note as drift (that's the *symptom* of the missing db, not N problems).
        rep.fail(f"cache {DB_PATH.relative_to(REPO_ROOT).as_posix()} missing — "
                 "run hydrate_cache.py")
    else:
        for note in sorted(st["missing_from_db"]):
            rep.fail(f"note missing from cache (drift): {note}")
    for note in sorted(st["stale_in_db"]):
        rep.fail(f"stale cache row (no sidecar): {note}")
    for note in sorted(st["mixed"]):
        rep.fail(f"sidecar backend != active ({st['active']}): {note}")
    for note in sorted(st["bad_dim"]):
        rep.fail(f"sidecar has wrong vector dim (expected {EMBED_DIM}): {note}")
    for note in sorted(st["unreadable"]):
        rep.fail(f"unreadable sidecar: "
                 f"{st['sidecars'][note].relative_to(REPO_ROOT).as_posix()}")

    clean = not any(st[k] for k in (
        "notes_wo_sidecar", "orphan_sidecars", "missing_from_db", "stale_in_db",
        "mixed", "bad_dim", "unreadable")) and not st["db_missing"]
    if clean:
        rep.ok(f"vault↔sidecar↔db in sync ({len(st['notes'])} note(s))")


# --------------------------------------------------------------------------- #
# --repair
# --------------------------------------------------------------------------- #

def do_repair(st: dict) -> None:
    """Reconcile the layers: drop orphans, (re)embed, rebuild the cache."""
    # 1. Drop orphan sidecars (their note is gone; the vector can't be trusted).
    for note in sorted(st["orphan_sidecars"]):
        sc = st["sidecars"][note]
        sc.unlink()
        print(f"  repair: removed orphan sidecar "
              f"{sc.relative_to(REPO_ROOT).as_posix()}")

    # 2. (Re)embed notes that are missing / wrong-dim / wrong-backend. Restrict to
    #    notes that actually exist — orphans are handled above, not re-embedded.
    to_embed = ((st["notes_wo_sidecar"] | st["mixed"] | st["bad_dim"]
                 | st["unreadable"]) & st["notes"])
    for note in sorted(to_embed):
        es.write_sidecar(note)  # uses the active backend
        print(f"  repair: embedded {note}")

    # 3. Rebuild the cache from the reconciled sidecars. hydrate wipes+rebuilds,
    #    which resolves both missing-from-db and stale-in-db in one pass.
    import hydrate_cache

    print("  repair: rebuilding cache …")
    hydrate_cache.main()


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Check this brain's health & consistency.")
    ap.add_argument("--repair", action="store_true",
                    help="reconcile sidecars and rebuild the cache before reporting")
    args = ap.parse_args(argv)

    rep = Report()

    print("health:")
    check_deps(rep)
    backend = check_config(rep)
    if backend == "ollama":
        check_ollama(rep)

    if args.repair:
        print("repair:")
        do_repair(scan())

    print("consistency:")
    report_consistency(rep, scan())

    print()
    if rep.problems:
        print(f"doctor: {rep.problems} problem(s) found"
              + ("" if args.repair else " — re-run with --repair to fix"))
        return 1
    print("doctor: brain healthy & consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
