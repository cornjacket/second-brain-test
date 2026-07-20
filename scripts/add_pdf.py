#!/usr/bin/env python3
"""Ingest a PDF into the brain: select → move → extract → chunk → embed → load (task #7 M5).

The end-to-end path that makes a PDF searchable. Two halves:

- **Folder-first selection** (`inbox_folders`, `list_pdfs`) — enumerate the configured source
  folders (priority order) and the PDFs inside a chosen one (sorted + paginated per config).
  Pure enumeration, so the same core drives any front-end (the CLI here; the MCP chat/elicitation
  tools at M6).
- **Ingest** (`add_pdf`) — move (or copy) the file into `vault/<para>/`, extract its text +
  page map (pdf_extract, needs the optional pypdf), write the chunk-list sidecar (embed_pdf), and
  load it into the cache (pdf_cache). **No git commit and no push** — the PDF and its sidecar are
  git-ignored (docs/pdf-ingestion.md decision 8), so ingest only touches local files + the cache.

NOT emitted into a brain yet (task #7 M6); prototyped in the golden and exercised by tests.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # noqa: E402
import embed_pdf  # noqa: E402
import pdf_cache  # noqa: E402
import pdf_config  # noqa: E402
import pdf_extract  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = REPO_ROOT / "vault"
CACHE_DIR = REPO_ROOT / "data"
DB_PATH = CACHE_DIR / "brain.db"
PARA_ROOTS = ("projects", "areas", "resources", "archive")


# --- folder-first selection --------------------------------------------------------------

def inbox_folders() -> list[Path]:
    """Configured source folders (priority order), ``~`` expanded and made absolute.

    Relative entries are resolved against the repo root, so ``vault/inbox`` means this brain's
    inbox. Every configured folder is returned (existing or not) so a front-end can show — and
    explain — the full choice; ``list_pdfs`` simply yields nothing for one that is absent.
    """
    out = []
    for entry in pdf_config.inbox_dirs():
        p = Path(entry).expanduser()
        out.append(p if p.is_absolute() else REPO_ROOT / p)
    return out


def list_pdfs(folder, *, offset: int = 0, limit: int | None = None) -> list[Path]:
    """PDFs directly in ``folder``, sorted per config, one page at a time.

    ``list_sort`` picks newest-first (mtime) or alphabetical; ``limit`` defaults to the
    configured page size. A missing folder yields ``[]``.
    """
    folder = Path(folder)
    pdfs = [p for p in folder.glob("*.pdf") if p.is_file()] if folder.is_dir() else []
    if pdf_config.list_sort() == "newest":
        pdfs.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    else:
        pdfs.sort(key=lambda p: p.name.lower())
    if limit is None:
        limit = pdf_config.list_page_size()
    return pdfs[offset:offset + limit]


# --- ingest ------------------------------------------------------------------------------

def add_pdf(pdf_path, para_root: str, *, move: bool | None = None) -> dict:
    """Ingest one PDF into ``vault/<para_root>/`` and load its chunks into the cache.

    Returns a summary ``{source_file, dest, pages, chunks, moved}``. Refuses an unknown PARA
    root or an existing destination (never silently overwrites). Does not commit or push.
    """
    pdf_path = Path(pdf_path)
    if para_root not in PARA_ROOTS:
        raise ValueError(f"unknown PARA root {para_root!r}; expected one of {PARA_ROOTS}")
    if not pdf_path.is_file():
        raise ValueError(f"no such PDF: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"not a .pdf: {pdf_path.name}")

    dest_dir = VAULT_DIR / para_root
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / pdf_path.name
    if dest.exists():
        raise ValueError(f"destination already exists, refusing to overwrite: "
                         f"{dest.relative_to(REPO_ROOT)}")

    if move is None:
        move = pdf_config.move_from_inbox()
    (shutil.move if move else shutil.copy2)(str(pdf_path), str(dest))

    # Extract -> chunk + embed -> sidecar. embed_pdf.sidecar_payload is the pure (path-free)
    # core, so we control where the sidecar lands: beside the PDF, git-ignored like every sidecar.
    doc = pdf_extract.extract(dest)
    source_file = dest.relative_to(REPO_ROOT).as_posix()
    payload = embed_pdf.sidecar_payload(
        source_file, doc.text, doc.page_spans,
        chunk_tokens=pdf_config.chunk_tokens(), chunk_overlap=pdf_config.chunk_overlap())
    sidecar = dest.parent / f".{dest.name}.embed.json"
    sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # Load into the cache in place (single-source refresh). No commit, no push.
    CACHE_DIR.mkdir(exist_ok=True)
    db = connect(DB_PATH)
    pdf_cache.ensure_tables(db)
    n = pdf_cache.update_source(db, payload)
    db.commit()
    db.close()

    return {"source_file": source_file, "dest": str(dest.relative_to(REPO_ROOT)),
            "pages": len(doc.page_spans), "chunks": n, "moved": bool(move)}


# --- CLI ---------------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ingest a PDF into the brain (task #7).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list source folders, or the PDFs in one")
    p_list.add_argument("folder", nargs="?", help="a source folder; omit to list the folders")

    p_add = sub.add_parser("add", help="ingest a PDF into vault/<para_root>/")
    p_add.add_argument("pdf")
    p_add.add_argument("para_root", choices=PARA_ROOTS)
    p_add.add_argument("--copy", action="store_true", help="copy instead of move")

    args = ap.parse_args(argv)

    if args.cmd == "list":
        if args.folder is None:
            for i, f in enumerate(inbox_folders(), 1):
                mark = "" if f.is_dir() else "  (missing)"
                print(f"{i}. {f}{mark}")
        else:
            pdfs = list_pdfs(args.folder)
            if not pdfs:
                print(f"(no PDFs in {args.folder})")
            for i, p in enumerate(pdfs, 1):
                print(f"{i}. {p.name}")
        return 0

    summary = add_pdf(args.pdf, args.para_root, move=not args.copy)
    print(f"ingested {summary['source_file']} — {summary['pages']} page(s), "
          f"{summary['chunks']} chunk(s) -> cache "
          f"({'moved' if summary['moved'] else 'copied'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
