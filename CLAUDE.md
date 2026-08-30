# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
docker compose up -d                                   # local Postgres w/ pgvector on :5432
uv run python3 db/client.py                            # (re)create schema — DESTRUCTIVE, see below
uv run uvicorn api.main:app --reload --port 8000        # API + frontend at http://localhost:8000
uv run python3 ingester/run.py <repo_id> <github_url>   # run ingestion in the foreground (debugging)
uv run python3 db/migrate.py                            # ADDITIVE migration — safe on live data
uv run python3 preflight.py                            # verify Docker, pgvector, keys, 768-dim contract
uv run python3 -m pytest                               # test suite
uv run python3 eval/author.py                          # write golden-set questions (validates spans)
uv run python3 eval/run.py                             # run the retrieval ladder
```

Tests are `pytest` under `tests/` (dev deps in `requirements-dev.txt`); there is no linter or
typechecker. The root-level `test_*.py` are throwaway scripts that hit the live provider APIs — they
are not unit tests and take no arguments. `tests/test_lexical_pg.py` needs Postgres and skips without it.

Secrets come from `.env` via `python-dotenv` (loaded in [db/client.py](db/client.py), which every entry
point imports): `DATABASE_URL`, `ANTHROPIC_API_KEY`, `FIREWORKS_API_KEY`.

## Architecture

RAG over a cloned GitHub repo. Three processes, one Postgres:

1. **API** ([api/main.py](api/main.py)) — FastAPI, also mounts `static/` at `/` so the whole app is one
   service locally. Routers: `/index`, `/ask`, `/overview|/snippet|/file`.
2. **Ingester** ([ingester/run.py](ingester/run.py)) — a *detached subprocess*, not a task queue.
   `POST /index` inserts a `repos` row as `pending`, then `subprocess.Popen`s `ingester/run.py` with
   `start_new_session=True`, logging to `/tmp/{repo_id}_ingest.log`. The pipeline is
   clone (shallow) → chunk → embed+store → LLM metadata → `status='ready'`; the clone dir `/tmp/{repo_id}`
   is always deleted in `finally`. The API never waits — the frontend polls `GET /overview/{repo_id}`
   every 2s until `status` is `ready` or `failed`.
3. **Postgres + pgvector** ([db/schema.sql](db/schema.sql)) — `repos` (status/error/metadata JSONB) and
   `chunks` (file_path, line range, raw_text, `VECTOR(768)`).

The `files` table stores full file content, so `/file/{repo_id}` returns it verbatim; chunk-stitching
survives only as a fallback for repos indexed before that table existed. Anything not matching
`ALLOW_EXTENSIONS` in [ingester/chunk.py](ingester/chunk.py) is invisible to the whole app. `.rst` is
on that list deliberately: most Python projects write their manual in it, and without it no prose
question is answerable.

`chunks.chunk_label` lets one repo hold several chunkings side by side (`line100`, `ast`) so retrieval
configurations can be compared without re-cloning. Retrieval is driven by `RetrievalConfig`
([config/retrieval.py](config/retrieval.py)); `/ask` and the eval harness share one entry point so the
shipped and measured systems cannot drift. See [SPEC.md](SPEC.md).

## Constraints that bite

- **`db/client.py` drops and recreates both tables.** `schema.sql` starts with `DROP TABLE ... CASCADE`,
  and `zerops.yml` runs it in `initCommands` — every Zerops deploy wipes all indexed repos. Intentional
  (it lets the embedding dimension change), but never run it against data you want to keep. Use
  [db/migrate.py](db/migrate.py) instead, which is additive and idempotent. `schema.sql` and `migrate.py`
  must be kept in step, or a fresh bootstrap and a migrated database will disagree.
- **768 is load-bearing.** The model and dimension live in [config/embedding.py](config/embedding.py);
  every call site imports from there. It must equal `VECTOR(768)` in the schema, so changing the
  embedding model means changing that module, the schema, and re-indexing.
- **Citations are a text contract.** [api/prompt.py](api/prompt.py) instructs Claude to emit
  `[file_path:start-end]`, [api/retrieval.py](api/retrieval.py) builds context chunks in exactly that
  format, and `routes_ask.py` regex-scrapes the answer for it. Editing the prompt's citation format
  silently empties the `citations` array and breaks the frontend's clickable file links.
- Both Anthropic calls go through [api/llm.py](api/llm.py), which owns the model name and attaches
  `anthropic-workspace-id` when `ANTHROPIC_WORKSPACE_ID` is set — identity-linked keys are rejected
  with a 400 without it. Metadata generation swallows its own failures and writes the error string
  into `metadata.overview`, so a bad model name surfaces as overview text rather than a failed index.
- `voyageai` in `requirements.txt` is unused, left from an earlier provider. The `VOYAGE_API_KEY`
  fallback it went with has been removed from both embedding call sites.
- Embedding retries are 5 attempts × a flat 15s sleep, all inside one open DB connection; large repos
  hold that connection for a long time.

## Zerops deployment

[zerops.yml](zerops.yml) defines two services: `app` (Python) and `frontend` (static, serves `static/`).
`db/setup_extension.py` runs first as init and needs the superuser env vars Zerops injects
(`DB_SUPERUSER`, `DB_SUPERUSER_PASSWORD`, `DB_HOSTNAME`, `DB_PORT`, `DB_NAME`) — `CREATE EXTENSION vector`
requires superuser, and the app's normal `DATABASE_URL` user cannot do it. Missing superuser vars is a
soft skip, not an error. When the frontend is served from the static service instead of FastAPI, it needs
`window.API_BASE` set to the API host; [static/app.js](static/app.js) defaults it to same-origin.
