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
import hashlib
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
from features import hybrid_search, rrf_k  # noqa: E402
import embed_staged as es  # noqa: E402  (write_sidecar / sidecar_path helpers)
from note_view import content_hash  # noqa: E402  (the embed-input fingerprint)


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
    mode = "hybrid (vector + lexical)" if hybrid_search() else "vector-only"
    rep.ok(f"search: {mode}, RRF K={rrf_k()}")
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


def db_pdf_sources() -> set[str] | None:
    """Distinct PDF sources in the chunk cache; ``None`` if the db is absent, ``set()`` if the
    PDF tables were never created (a brain that has ingested no PDF — task #7)."""
    if not DB_PATH.exists():
        return None
    from db import connect

    db = connect(DB_PATH)
    try:
        try:
            return {row[0] for row in db.execute("SELECT DISTINCT source_file FROM pdf_chunks_meta")}
        except Exception:  # noqa: BLE001 — table absent until the first PDF is ingested
            return set()
    finally:
        db.close()


def pdf_source_for_sidecar(sc: Path) -> str:
    """Map a chunk sidecar ``…/.<name>.embed.json`` back to its source ``…/<name>`` (task #7)."""
    name = sc.name[len("."):-len(".embed.json")]  # ".paper.pdf.embed.json" -> "paper.pdf"
    return (sc.parent / name).relative_to(REPO_ROOT).as_posix()


def _pypdf_available() -> bool:
    try:
        import pypdf  # noqa: F401
        return True
    except ImportError:
        return False


def _scan_pdf(pdf_sidecars: dict, active: str) -> dict:
    """Consistency of chunked PDF sources: sidecar ↔ PDF ↔ cache (task #7, mirrors the note pass).

    Staleness (the sidecar's content_hash no longer matches the PDF's current extracted text)
    needs pypdf to re-extract; without it, those sources are reported *unverifiable*, not clean.
    """
    orphan, mixed, bad_dim, stale, unverifiable = set(), set(), set(), set(), set()
    have_pypdf = _pypdf_available()
    for source, (sc, payload) in pdf_sidecars.items():
        pdf_here = (REPO_ROOT / source).exists()
        if not pdf_here:
            orphan.add(source)
        if payload.get("type") != active:
            mixed.add(source)
        if any(len(ch.get("vector", [])) != EMBED_DIM for ch in payload.get("chunks", [])):
            bad_dim.add(source)
        if pdf_here:
            if not have_pypdf:
                unverifiable.add(source)
            else:
                try:
                    import pdf_extract
                    doc = pdf_extract.extract(REPO_ROOT / source)
                    current = "sha256:" + hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
                    if payload.get("content_hash") != current:
                        stale.add(source)
                except Exception:  # noqa: BLE001 — a broken PDF can't be re-verified; say so
                    unverifiable.add(source)

    db_rows = db_pdf_sources()
    # If the whole cache is gone, the note pass already reports it — don't double-count here.
    missing_from_db = set() if db_rows is None else (set(pdf_sidecars) - orphan) - db_rows

    return {"sidecars": {s: sc for s, (sc, _) in pdf_sidecars.items()},
            "orphan": orphan, "mixed": mixed, "bad_dim": bad_dim, "stale": stale,
            "unverifiable": unverifiable, "missing_from_db": missing_from_db}


def scan() -> dict:
    """Pure scan of the three layers; returns the discrepancy sets (no output)."""
    notes = para_notes()
    active = backend_id()

    # Split sidecars by content: a note sidecar has a single "vector"; a PDF sidecar (task #7)
    # has a "chunks" list. Both live under PARA roots and match .*.embed.json, so without this
    # a PDF sidecar would be mis-read as an orphan, wrong-dim note.
    sidecars: dict[str, Path] = {}
    pdf_sidecars: dict[str, tuple[Path, dict]] = {}
    for sc in all_sidecars():
        try:
            payload = json.loads(sc.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            sidecars[note_for_sidecar(sc)] = sc  # unreadable — flagged in the note pass below
            continue
        if "chunks" in payload:
            pdf_sidecars[pdf_source_for_sidecar(sc)] = (sc, payload)
        else:
            sidecars[note_for_sidecar(sc)] = sc

    bad_dim: set[str] = set()
    mixed: set[str] = set()
    unreadable: set[str] = set()
    stale_hash: set[str] = set()
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
        # Stale embed: the sidecar's stored content_hash no longer matches what the note's
        # canonical substance view hashes to NOW. Two ways this happens, both meaning "the vector
        # was produced from an input that is no longer current": (a) the note's substance was
        # edited but not re-embedded, or (b) the canonical-view *definition* changed under it —
        # e.g. an upgrade added wikilink-stripping (#26) but update_brain never re-embeds, so every
        # note silently carries a vector from the old view. Search still works, which is exactly
        # why nothing else notices. Recompute and compare; a stored hash that predates the field
        # (older sidecar) is treated as stale so an upgrade re-embeds it.
        try:
            current = content_hash((REPO_ROOT / note).read_text(encoding="utf-8"))
        except OSError:
            continue  # note vanished mid-scan; the orphan/missing sets own that case
        if payload.get("content_hash") != current:
            stale_hash.add(note)

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
        "stale_hash": stale_hash,
        "db_missing": rows is None,
        "pdf": _scan_pdf(pdf_sidecars, active),
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
    for note in sorted(st["stale_hash"]):
        rep.fail(f"stale embedding (vector predates the note's current content — re-embed): "
                 f"{note}")

    # PDF chunk sources (task #7) — mirrors the note checks at the document grain.
    pdf = st.get("pdf", {})
    for source in sorted(pdf.get("orphan", ())):
        rep.fail(f"orphan PDF sidecar (source PDF gone): "
                 f"{pdf['sidecars'][source].relative_to(REPO_ROOT).as_posix()}")
    if not st["db_missing"]:
        for source in sorted(pdf.get("missing_from_db", ())):
            rep.fail(f"PDF not in cache (drift): {source}")
    for source in sorted(pdf.get("mixed", ())):
        rep.fail(f"PDF sidecar backend != active ({st['active']}): {source}")
    for source in sorted(pdf.get("bad_dim", ())):
        rep.fail(f"PDF sidecar has a chunk with wrong vector dim (expected {EMBED_DIM}): {source}")
    for source in sorted(pdf.get("stale", ())):
        rep.fail(f"stale PDF embedding (chunks predate the PDF's current text — re-ingest): {source}")
    for source in sorted(pdf.get("unverifiable", ())):
        rep.info(f"PDF staleness unverifiable without pypdf (install requirements-pdf.txt): {source}")

    pdf_problem = any(pdf.get(k) for k in ("orphan", "missing_from_db", "mixed", "bad_dim", "stale"))
    clean = not any(st[k] for k in (
        "notes_wo_sidecar", "orphan_sidecars", "missing_from_db", "stale_in_db",
        "mixed", "bad_dim", "unreadable", "stale_hash")) and not st["db_missing"] and not pdf_problem
    if clean:
        pdf_tail = f" + {len(pdf.get('sidecars', {}))} pdf(s)" if pdf.get("sidecars") else ""
        rep.ok(f"vault↔sidecar↔db in sync ({len(st['notes'])} note(s){pdf_tail})")


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
                 | st["unreadable"] | st["stale_hash"]) & st["notes"])
    for note in sorted(to_embed):
        es.write_sidecar(note, force=True)  # repair must rewrite even a hash-matching sidecar
        print(f"  repair: embedded {note}")

    # 2b. PDF sources (task #7): drop orphan chunk sidecars, then re-ingest stale / wrong-backend
    #     / wrong-dim ones — which needs pypdf to re-extract. Missing-from-cache is fixed by the
    #     rebuild below (hydrate reloads chunk sidecars).
    pdf = st.get("pdf", {})
    for source in sorted(pdf.get("orphan", ())):
        sc = pdf["sidecars"][source]
        sc.unlink()
        print(f"  repair: removed orphan PDF sidecar {sc.relative_to(REPO_ROOT).as_posix()}")
    reingest = ((pdf.get("stale", set()) | pdf.get("mixed", set()) | pdf.get("bad_dim", set()))
                - pdf.get("orphan", set()))
    if reingest:
        if _pypdf_available():
            import pdf_config
            import pdf_extract
            import embed_pdf
            for source in sorted(reingest):
                doc = pdf_extract.extract(REPO_ROOT / source)
                payload = embed_pdf.sidecar_payload(
                    source, doc.text, doc.page_spans,
                    chunk_tokens=pdf_config.chunk_tokens(), chunk_overlap=pdf_config.chunk_overlap())
                pdf["sidecars"][source].write_text(json.dumps(payload, indent=2) + "\n",
                                                   encoding="utf-8")
                print(f"  repair: re-embedded PDF {source}")
        else:
            print("  repair: cannot re-embed PDFs without pypdf "
                  "(install requirements-pdf.txt); rebuilding cache only")

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
