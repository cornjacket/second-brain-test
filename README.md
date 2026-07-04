# Second Brain

A personal knowledge base with **two faces over one source of truth**: you write
plain-Markdown notes (in [Obsidian](https://obsidian.md) or any editor), and an AI
(Claude / Gemini) searches them **semantically**. Notes are organized with
**PARA**; a git pre-commit hook keeps a per-note vector in sync, and those vectors
hydrate a local SQLite cache that powers search — no cloud, no external services.

> This repo is the **golden reference** for
> [`second-brain-devkit`](https://github.com/cornjacket/second-brain-devkit) — the
> hand-built, known-good output the generator is validated against. The design
> internals (sidecar schema, embedding contract, pipeline stages) are in
> [SPEC.md](SPEC.md).

## Setup (one-time)

```bash
git config core.hooksPath .githooks    # activate the embed-on-commit hook
pip install -r requirements.txt         # sqlite-vec (+ apsw fallback)
```

This brain's embedding backend is set in **`config/embedder.toml`** (override a
single command with the `SECOND_BRAIN_EMBEDDER` env var). Two backends:

- **`ollama`** — real semantic search; needs a local [Ollama](https://ollama.com)
  server running `nomic-embed-text` (the default backend for a fresh brain).
- **`test`** — deterministic, dependency-free plumbing; stable but *not* semantic.

Notes and queries must share a backend (the same-model invariant), so this one
switch keeps the whole brain consistent.

### Turn on semantic search (Ollama)

Real retrieval needs a local Ollama server and the embedding model. One-time:

```bash
# 1. Install Ollama — https://ollama.com (macOS: `brew install ollama`)
# 2. Start the server (leave it running; on macOS the app starts it for you)
ollama serve
# 3. Pull the embedding model this brain uses
ollama pull nomic-embed-text
```

Then confirm the brain is actually ready — deps installed, Ollama reachable, model
pulled, and the vault↔cache in sync — with one command:

```bash
python3 scripts/doctor.py          # health + consistency report
python3 scripts/doctor.py --repair  # ...and fix what it safely can
```

`doctor.py` exits `0` when the brain is healthy and consistent, and prints an
actionable line for anything that isn't (Ollama down, model missing, a note not yet
embedded, a stale cache row). Run it whenever search behaves oddly.

## Everyday use

**Record knowledge** — write a note under a PARA root, then commit it:

```bash
#  vault/projects/  goal-bound effort      vault/resources/  durable reference
#  vault/areas/     ongoing responsibility  vault/archive/    inactive
git add vault/areas/my-note.md && git commit -m "note: my-note"
```

Filenames are lowercase kebab-case `.md` with YAML frontmatter (`tags: [...]`);
link notes with `[[wikilinks]]`. On commit the **pre-commit** hook embeds the note
and the **post-commit** hook refreshes the cache — so it's searchable right away,
no manual step.

> **Tip — phrase a note the way you'll search for it.** Search ranks a note by how
> close its *wording and meaning* are to your query, so a note that mirrors the
> question you'll later ask is much easier to find. For a quick fact, lead with the
> question **and** answer near the top:
>
> ```markdown
> ---
> tags: [ops]
> ---
> # Deploy rollback
> **Q: How do I roll back a bad deploy?**
> A: `kubectl rollout undo deployment/<name>` — reverts to the previous revision.
> ```
>
> It's not that a question is special — it's that the note now matches *how you'll
> ask*. The closer the note's language is to your future query, the higher it ranks.

**Query knowledge** — just search:

```bash
python3 scripts/search_vault.py "vector search"
```

After a **bulk** change (e.g. `scripts/embed_vault.py`, or editing many notes at
once), rebuild the cache manually: `python3 scripts/hydrate_cache.py`.

**Self-check** (optional) — two complementary checks:

```bash
python3 scripts/self_test.py   # is the embed pipeline wired correctly? (no model)
python3 scripts/doctor.py      # is the brain ready & consistent? (deps, Ollama, cache)
```

`self_test.py` proves the plumbing reproduces byte-for-byte with no model; `doctor.py`
checks the live runtime (Ollama up, model pulled) and that the vault, sidecars, and
cache all agree — add `--repair` to fix drift.

## Query it from any project (AI skill)

The point of a second brain is for an **AI to consult it while you build something
else** — surfacing existing conventions, past decisions, and tribal knowledge
*before* it designs. This brain ships a skill for **Claude Code / Gemini CLI** that
does exactly that. Install it once (a symlink — nothing is copied):

```bash
python3 scripts/install_skill.py --global --nudge --apply      # every project
python3 scripts/install_skill.py --project ~/work/app --apply  # or just one repo
```

Omit `--apply` for a dry run (nothing is changed until you pass it). After that,
when you run the AI in another project it consults this brain automatically (it
runs `skill/second-brain/query.py`, which searches this vault and returns the
matching notes as absolute paths). The skill is written to trigger proactively —
before proposing an architecture or convention — and you can also invoke it
directly with `/second-brain`.

- **`--global`** links the skill into `~/.claude/skills/` (and `~/.gemini/skills/`) — all projects.
- **`--project <path>`** links it into that repo's `.claude/skills/` — opt-in, per repo.
- **`--nudge`** (optional, recommended) adds a short *"consult the second-brain
  before designing"* reminder to your global memory (`~/.claude/CLAUDE.md`,
  `~/.gemini/GEMINI.md`) so the AI reaches for the brain reflexively, not only when
  the skill's own description happens to fire. It's a marked, idempotent block —
  safe to re-run.
- Requires Ollama running (queries are embedded with it).

**Uninstall** — remove whichever parts you named; only this brain's symlinks and
the marked nudge block are touched, the rest of your config is left intact:

```bash
python3 scripts/install_skill.py --uninstall --global --nudge --apply
```

Prefer to add the nudge by hand instead of `--nudge`? Paste this into your global
`~/.claude/CLAUDE.md`:

```markdown
<!-- second-brain:begin -->
## Second brain

Before designing a system, choosing conventions or naming, or answering "how do we
do X / what did we decide about Y", consult the personal **second-brain** first
(via the `second-brain` skill) — it holds prior decisions, conventions, and
hard-won context. Do this proactively, before proposing a design.
<!-- second-brain:end -->
```

## Use from Claude Desktop (MCP)

The skill above covers any client that can run a shell command (Claude Code, Gemini
CLI). **Claude Desktop can't** — it reaches tools only over [MCP](https://modelcontextprotocol.io).
For that one case this brain ships an optional **MCP server** (`scripts/mcp_server.py`)
exposing the same read-only search over stdio. It's a thin wrapper over this brain's
own embed + search, so results match the skill exactly. It exposes two tools:
`search_second_brain(query, k)` → matching notes (absolute paths + distance) and
`get_note(source_file)` → a note's Markdown. **Read-only** (notes are written through
the git-committed vault flow) and **local-only** (a browser like claude.ai can't
reach a local stdio server, so web chat isn't covered).

### Setup, step by step

1. **Install Claude Desktop** — download the app from
   [claude.ai/download](https://claude.ai/download) and sign in.

2. **Install the MCP dependency** (once), from this brain's root:
   ```bash
   pip install -r requirements-mcp.txt   # optional — only for the Desktop path
   ```
   Install it into the **same** Python you'll name in step 4, and make sure Ollama
   is running (`scripts/doctor.py` verifies readiness).

3. **Find your interpreter's absolute path.** Desktop launches the server with a
   minimal environment, so a bare `python3` — especially a **pyenv/conda _shim_** —
   may resolve to the wrong Python or one without `mcp`. Get the real binary:
   ```bash
   which python3                 # if this is a pyenv shim (…/shims/python3):
   pyenv which python3           #   → the real binary, e.g. ~/.pyenv/versions/3.13.14/bin/python3
   ```
   Use that resolved path in the next step, not `python3`.

4. **Register the server.** In Claude Desktop: **Settings → Developer → Edit Config**
   (this opens `~/Library/Application Support/Claude/claude_desktop_config.json` on
   macOS). Add the `mcpServers` block — merge it in if the file already has other
   top-level keys, and use **absolute** paths for both the interpreter and the server:
   ```json
   {
     "mcpServers": {
       "second-brain": {
         "command": "/ABSOLUTE/PATH/TO/python3",
         "args": ["/ABSOLUTE/PATH/TO/second-brain/scripts/mcp_server.py"]
       }
     }
   }
   ```

5. **Restart fully** — quit with **Cmd+Q** (closing the window isn't enough) and
   reopen, so Desktop launches the server and reads its tools.

6. **Confirm the tools loaded.** Open **Customize → Connectors** (or Settings →
   Connectors) and select **`second-brain`**. It should list `search_second_brain`
   and `get_note`. If it says *"no tools available,"* see troubleshooting below.

7. **Use it** — in a plain **Chat** (not Cowork/Code), ask something that points at
   the tool:
   > *Use the second-brain tool to search my notes for vector search, then summarize
   > what you find.*

   The first call shows an in-app **"Allow tool?"** prompt — approve it. Claude then
   calls `search_second_brain`, optionally `get_note` on a hit, and answers from your
   notes.

### Verify without Claude Desktop

An MCP server talks JSON-RPC over stdin/stdout, so you can exercise it with a small
client instead of the app. Save as `mcp_smoke.py`, set the path, `python3 mcp_smoke.py`:

```python
import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = "/ABSOLUTE/PATH/TO/second-brain/scripts/mcp_server.py"

async def main():
    async with stdio_client(StdioServerParameters(command="python3", args=[SERVER])) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("tools:", [t.name for t in (await s.list_tools()).tools])
            res = await s.call_tool("search_second_brain", {"query": "vector search", "k": 3})
            print(res.content[0].text)   # a JSON string of the ranked hits

asyncio.run(main())
```

You should see both tool names and a few ranked note paths.

### Troubleshooting

- **"This connector has no tools available."** Claude Desktop's MCP client may be
  older than a server feature. This brain's server already avoids the known trap (it
  disables *structured output* / `outputSchema`, which older Desktop builds silently
  drop). If you customize the server to re-enable structured output and tools vanish,
  that's why — set `structured_output=False` on each `@mcp.tool()` and restart.
- **Server won't start / tools never appear.** Almost always the `command` path — a
  shim or a Python without `mcp`. Use the absolute interpreter from step 3. Logs live
  at `~/Library/Logs/Claude/mcp-server-second-brain.log`.
- **Client can't handshake.** Something wrote to stdout; on stdio that's the JSON-RPC
  channel. This server routes its own output to stderr to keep stdout clean.
- **Empty results.** Ollama isn't running or the cache is unbuilt — run
  `python3 scripts/doctor.py --repair`.

## Layout

```
├── .githooks/pre-commit   # embeds staged notes locally + line-count guard
├── scripts/               # embedder, db, embed_staged, embed_vault, hydrate/update_cache, search, register, self_test, doctor, install_skill, mcp_server
├── skill/second-brain/    # AI skill — consult this brain from any project (install_skill.py)
├── vault/                 # your notes — point Obsidian here
│   ├── projects/  areas/  resources/  archive/    # PARA roots (embedding scope)
│   └── …/.<note>.embed.json   # per-note vectors — DERIVED, git-ignored
├── tests/fixtures/vault/  # committed test-backend fixtures for self_test
├── data/brain.db          # SQLite vector cache — DERIVED, git-ignored
└── config/                # optional tool-specific config
```

> **Committed vs derived.** Your live note vectors are *derived* and git-ignored —
> regenerated locally, never committed (they're machine/model-dependent). The only
> committed vectors are the deterministic `test`-backend fixtures under
> `tests/fixtures/vault/`, which anchor `self_test`.

## How it works

```
note.md ─(pre-commit)→ .note.embed.json ─(hydrate)→ SQLite vec cache ─(search)→ AI
```

Embed a note into a vector on commit → hydrate pours every vector into one
searchable cache → search embeds your query with the **same** backend and returns
the nearest notes. (Notes and queries must use the same embedder, or results are
meaningless — everything routes through `scripts/embedder.py`.)

> **Tip for Obsidian:** open the `vault/` directory as your vault root (not the
> repo root), so Obsidian doesn't index scripts or the database as notes.

## Registering a project

To have another repo deposit its learnings here, run
`python3 scripts/register.py <project-path>` — it adds an idempotent block to that
project's `CLAUDE.md` pointing its agent at this brain.
