# Repo Onboarding Assistant — Complete Reference

RAG over a cloned GitHub repository. Point it at a repo, it clones, chunks, embeds and
indexes the source, then answers natural-language questions with citations back to exact
file and line ranges.

This document is the full reference: what it does, how it is built, what is measured, what
works today and what does not. Companion documents: [SPEC.md](SPEC.md) is the plan of record
for in-progress work; [CLAUDE.md](CLAUDE.md) is the working guide for AI agents.

Every number below was measured on 2026-08-30, not estimated.

---

## 1. Status at a glance

| | |
|---|---|
| **Runs** | Locally only. The Zerops deployment is dead (credits expired). |
| **Database** | Postgres 16.14 + pgvector 0.8.6, via Docker |
| **Indexed** | 9 repos, 922 chunks, 294 stored files |
| **Embeddings** | Fireworks `nomic-ai/nomic-embed-text-v1.5`, 768-dim — **working** |
| **LLM** | `gemini-2.5-flash` via fallback — **working** |
| **Anthropic** | Key is identity-linked; its workspace ID is invalid. Falls back to Gemini. |
| **Tests** | 114 test cases, all passing |
| **Code** | ~2,690 lines of Python (~2,000 source, ~690 tests) |
| **Git** | `feat/retrieval-ladder`, 11 commits ahead of `main`, 10 pushed |

**What works end to end:** index a repo, browse its file tree, click into any file, ask a
question, get a cited answer.

**What does not:** the ladder rows past the baseline (AST chunking, hybrid search,
reranking, query expansion) are specified and seamed in but not yet implemented.

---

## 2. Running it

```bash
docker compose up -d                                   # Postgres + pgvector on :5432
uv run python3 db/migrate.py                           # additive; safe on live data
uv run python3 preflight.py                            # verify every dependency
uv run uvicorn api.main:app --reload --port 8000       # app at http://localhost:8000
```

`preflight.py` is the one to run when something is wrong. It checks Postgres, pgvector, the
migrated schema, the 768-dimension embedding contract, and LLM reachability, and prints a
single pass/fail. It degrades honestly: an unreachable LLM still leaves retrieval-only work
runnable, and it says so.

### Secrets

`.env`, loaded by `python-dotenv` in [db/client.py](db/client.py), which every entry point
imports.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | no | defaults to the local Docker Postgres |
| `FIREWORKS_API_KEY` | **yes** | embeddings; nothing works without it |
| `ANTHROPIC_API_KEY` | one of | answering questions, repo overviews |
| `ANTHROPIC_WORKSPACE_ID` | conditional | required if the Anthropic key is identity-linked |
| `GEMINI_API_KEY` | one of | fallback LLM |
| `LLM_PROVIDER` | no | `auto` (default), `anthropic`, or `gemini` |

---

## 3. Architecture

Three processes, one database.

```
Browser ──► FastAPI (api/) ──► Postgres + pgvector
                │                     ▲
                │ POST /index         │
                ▼                     │
          Ingester subprocess ────────┘
          (clone → chunk → embed → store)
                │
                ├──► Fireworks (embeddings)
                └──► Anthropic / Gemini (overview, answers)
```

**API** — [api/main.py](api/main.py). FastAPI, and it also mounts `static/` at `/`, so the
whole app is a single service locally.

**Ingester** — [ingester/run.py](ingester/run.py). A *detached subprocess*, not a task queue.
`POST /index` inserts a `repos` row as `pending`, then `subprocess.Popen`s the ingester with
`start_new_session=True`, logging to `/tmp/{repo_id}_ingest.log`. The API never waits; the
frontend polls `GET /overview/{repo_id}` every 2 seconds until `status` is `ready` or
`failed`. **If the process dies, status stays `pending` forever and the frontend polls
indefinitely.** There is no heartbeat, no retry, no recovery.

**Postgres + pgvector** — the only persistent state.

### Ingestion pipeline

Split into two stages so one clone can be chunked several ways:

```
clone (shallow, optionally pinned to a tag)
  └─ store files          ← once per repo
  └─ chunk → embed → store ← repeatable, once per chunk_label
  └─ generate overview (LLM)
  └─ status = 'ready'
```

The clone directory `/tmp/{repo_id}` is always deleted in a `finally` block.

```bash
uv run python3 ingester/run.py <repo_id> <github_url> [--ref TAG] [--label LABEL] [--skip-metadata]
```

Driving it directly is the right way to build an evaluation corpus — `POST /index` spawns
the unsupervised subprocess and generates a new `repos` row each time.

---

## 4. Data model

### `repos`
`id` (UUID PK) · `url` · `status` (`pending|indexing|ready|failed`) · `error` ·
`metadata` (JSONB) · `indexed_at`

`metadata` holds `folder_tree`, `language_counts`, `entry_points`, `overview`,
`overview_model`, and `overview_error`.

### `chunks`
`id` · `repo_id` (FK, cascade) · `file_path` · `start_line` · `end_line` ·
`chunk_type` (`code|doc|config`) · `raw_text` · `embedding VECTOR(768)` ·
`chunk_label` · `tsv`

- **`chunk_label`** lets one repo hold several chunkings side by side (`line100`, `ast`), so
  retrieval strategies can be compared without re-cloning or re-storing files.
- **`tsv`** is `GENERATED ALWAYS AS (to_tsvector('simple', raw_text)) STORED`, with a GIN
  index. It backfills itself, so no migration script was needed for existing rows.

### `files`
`repo_id` + `file_path` (composite PK) · `content` · `sha`

Full file content, stored once at ingest. Before this table, `chunks` was the only record of
file content and `/file` rebuilt files by stitching chunks and trimming a fixed 10-line
overlap. Function-level chunks leave gaps between functions and have no uniform overlap, so
that logic would have silently dropped lines. Content is now returned verbatim — verified
byte-identical to upstream at a pinned commit.

### Migrations

[db/migrate.py](db/migrate.py) is **additive and idempotent** — safe against live data, safe
to run twice.

[db/schema.sql](db/schema.sql) starts with `DROP TABLE ... CASCADE` and **destroys
everything**. `db/client.py` runs it, and `zerops.yml` calls that on deploy. Both files are
kept in step with `migrate.py` so a fresh bootstrap and a migrated database produce identical
shapes — verified in a throwaway database — but `client.py` should not be run against data
you want to keep.

---

## 5. HTTP API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | serves the frontend |
| `POST` | `/index` | `{github_url}` → `{repo_id, status}`; spawns the ingester |
| `POST` | `/ask` | `{repo_id, question, config?}` → `{answer, citations[], model}` |
| `GET` | `/overview/{repo_id}` | status + metadata; the polling endpoint |
| `GET` | `/snippet/{repo_id}?file_path=` | first chunk of a file |
| `GET` | `/file/{repo_id}?file_path=` | full file content |

`/ask` accepts an optional `config` naming a ladder row and returns 400 on an unknown one.
It returns `model` — the model that produced the answer — because an answer whose provider
silently changed would be a measurement with no provenance.

---

## 6. Retrieval

Retrieval is driven by a `RetrievalConfig` ([config/retrieval.py](config/retrieval.py)). A
strategy is a *config*, not a branch in the retrieval code, and `/ask` and the eval harness
call the same entry point so the shipped system and the measured system cannot drift.

```
expansion (LLM → identifiers, filtered against corpus vocabulary)
   │
   ├── dense arm    — pgvector cosine over chunks.embedding
   └── lexical arm  — ts_rank over chunks.tsv
   │
RRF fusion (k=60)
   │
cross-encoder rerank (top 50 → top N)
   │
abstain if top rerank score < threshold
   │
select by line budget (~500 lines) → context → LLM
```

### The ladder

| Config | chunk_label | lexical | rerank | expansion | Built? |
|---|---|---|---|---|---|
| `0-baseline` | line100 | – | – | – | **yes** |
| `1-ast` | ast | – | – | – | no |
| `2-hybrid` | ast | yes | – | – | partly |
| `3-rerank` | ast | yes | yes | – | no |
| `4-expansion` | ast | yes | yes | yes | no |

Defaults: `LINE_BUDGET=500`, `TOP_K=5`, `candidate_pool=50`, `rrf_k=60`,
`DEFAULT_CONFIG=0-baseline`.

`api/lexical.py` and `api/fusion.py` are implemented and tested; the `ast` chunker they
depend on is not, so rows 1–4 cannot run yet. **The harness refuses to run them rather than
reporting a fabricated zero** — see §8.

### Why a line budget rather than `recall@k`

Baseline chunks are 100 lines; AST function chunks are roughly 20. At a fixed `k`, the
baseline receives about five times more context, biasing the comparison toward the very
configuration the AST arm is meant to beat. Selecting by line budget gives both the same
amount of material.

### Chunking

`CHUNK_SIZE=100` lines, `OVERLAP=10`, `MAX_FILE_SIZE=500KB`.
`IGNORE_DIRS = {.git, node_modules, dist, build, .venv}`.

`ALLOW_EXTENSIONS` is a whitelist — **anything not on it is invisible to the entire
application.** It includes `.py .js .ts .go .java .rb .md .rst .txt .yaml .json .toml .sql
.html .css`.

`.rst` matters more than it looks. Most Python projects write their manual in it. Before it
was added, asking flask *"how do I upload and handle files in a form?"* returned `send_file()`
— sending a file **to** a user, the opposite operation — because the real answer in
`docs/patterns/fileuploads.rst` was not indexed. Adding it took the flask corpus from 307 to
514 chunks and made that document the top hit.

### Embeddings

Fireworks `nomic-ai/nomic-embed-text-v1.5`, 768 dimensions, batches of 50, 5 retries at a
flat 15-second sleep. The model and dimension live in
[config/embedding.py](config/embedding.py); **768 must equal `VECTOR(768)` in the schema**, so
changing the model means changing that module, the schema, and re-indexing everything.

There is **no ANN index** on `embedding`. Every vector search is an exact scan. At this corpus
size that is a few milliseconds and entirely fine; it would not be at 100× the size.

---

## 7. LLM providers

Every LLM call goes through [api/llm.py](api/llm.py), which fronts two providers.

- `LLM_PROVIDER=auto` (default) tries Anthropic, falls back to Gemini, and remembers which
  worked rather than retrying a broken provider on every request.
- `LLM_PROVIDER=anthropic|gemini` pins one and does **not** fall back — a run whose model
  changed partway would be unattributable.
- Both run at **`temperature=0`**. The Anthropic default is 1.0; without this every metric
  would be a single draw from an uncharacterised distribution.
- Every response reports its model.

Gemini is a thinking model, so its output budget is the caller's `max_tokens` plus 4,096 of
headroom — otherwise it can spend the entire budget reasoning and return no text. That case
raises a clear error instead of an empty string.

### The citation contract

Three files must agree, and nothing enforces it but tests:

1. [api/prompt.py](api/prompt.py) instructs the model to emit `[file_path:start-end]`
2. [api/retrieval.py](api/retrieval.py) builds context blocks in exactly that format
3. [api/routes_ask.py](api/routes_ask.py) regex-scrapes the answer for it

Editing the prompt's citation format silently empties the `citations` array and breaks the
frontend's clickable links. The contract survived the Anthropic→Gemini swap intact — verified
with a live query returning 15 correctly-parsed citations.

---

## 8. Evaluation

Retrieval quality is measured, not asserted. **Metrics require no LLM at all** — they are
pure vector and SQL maths against gold line spans, which is what keeps the sweep cheap and
reproducible by anyone with an embedding key.

### Metrics ([eval/metrics.py](eval/metrics.py))

- **recall at a fixed line budget** — primary
- **`recall@5`** — secondary, for readers who expect the standard number
- **MRR** — reciprocal rank of the first chunk hitting any gold span
- **coverage** — fraction of gold *lines* inside the union of retrieved chunks
- **paired diff** — improved / unchanged / regressed counts between two configs

A retrieved chunk **hits** a gold span when they name the same file and their inclusive line
ranges overlap. Deliberately chunker-independent, so the same golden set scores every config
without re-labelling.

Paired reporting exists because with 20 answerable questions one question is worth 5 recall
points, and realistic per-feature gains are 2–8 points. *"Hybrid fixed 6 and broke 2"* is both
more honest and more useful than *"+4.2 points"*.

### Golden set ([eval/golden_set.py](eval/golden_set.py))

Planned: 30 hand-written questions — 20 answerable with gold spans, 10 unanswerable for
measuring refusal. **Not yet written; this is the critical path.**

Gold is stored as line spans, never chunk ids. Answerable questions must carry gold;
unanswerable ones must not. `save()` validates before writing, so a corrupt set never reaches
disk.

### Authoring ([eval/author.py](eval/author.py))

```bash
uv run python3 eval/author.py            # add questions
uv run python3 eval/author.py --list     # show the set
uv run python3 eval/author.py --check    # re-validate every span
```

Every gold span is checked against the live index **before** it is written. A span pointing
at an unindexed file, or past the end of a file, scores zero forever and looks identical to a
retrieval failure. Recording one is made impossible rather than merely discouraged; it also
suggests the right path when you type a bare basename.

### Harness ([eval/run.py](eval/run.py))

```bash
uv run python3 eval/run.py                       # every runnable ladder row
uv run python3 eval/run.py --config 2-hybrid
uv run python3 eval/run.py --save
```

[eval/runnable.py](eval/runnable.py) exists because of a specific failure: running the `ast`
row before ingesting any `ast` chunks **did not error**. The retriever returned nothing and
the harness printed `recall=0.000` as though it were a measurement. A config whose index or
modules are missing is now skipped with every reason stated, and the harness exits rather
than print a table with no measurements in it.

### Baseline measured so far

On flask, with gold spans at the real definitions of `url_for`, `send_file` and
`from_pyfile`: **recall@budget 0.333, MRR 0.184, p50 latency 586 ms.** Three questions only —
a plumbing check, not a result.

---

## 9. Corpus

**flask**, pinned at tag `3.1.3` (commit `22d92470`) — 514 chunks across 215 files. It carries
every published number.

This repo itself is demo-only at 39 chunks. At that size a top-50 rerank pool is the entire
database, so reranking is undefined and hybrid search has nothing to discriminate.

Eight other repos are indexed from ad-hoc use and are not part of any measurement.

---

## 10. Testing

```bash
uv run python3 -m pytest              # 114 cases from 104 test functions
uv run python3 -m pytest tests/test_metrics.py -v
```

| File | Tests | Covers |
|---|---|---|
| `test_metrics.py` | 27 | recall, MRR, coverage, budget selection, paired diffs |
| `test_golden_set.py` | 17 | schema validation, round-trip, id allocation |
| `test_lexical.py` | 17 | tokenisation, tsquery construction, injection safety |
| `test_llm.py` | 13 | provider selection, Gemini response parsing |
| `test_fusion.py` | 9 | RRF ranking, dedup, k sensitivity |
| `test_runnable.py` | 8 | the guard against fabricated zeros |
| `test_chunk_types.py` | 5 | extension whitelist, doc/code/config classification |
| `test_metadata_errors.py` | 5 | error classification never leaks raw exceptions |
| `test_lexical_pg.py` | 13 | **live Postgres** cross-check (3 functions, parametrized) |

`test_lexical_pg.py` skips when Postgres is unavailable, so the rest of the suite runs
offline. It earns its place: it caught a real bug where Postgres lexes `app.route` as a single
token while the tokenizer split it into `app` and `route` — meaning a query for `@app.route`,
one of the most distinctive identifiers in flask, could never have matched.

There is no linter, formatter or typechecker. The root-level `test_anthropic.py` and
`test_fireworks.py` are throwaway provider probes, not tests.

---

## 11. Measured facts worth knowing

Verified against Postgres 16.14, not assumed:

```
to_tsvector('simple','send_file')  → 'file':2 'send':1     snake_case splits FREE
to_tsvector('simple','url_for')    → 'for':2 'url':1
to_tsvector('simple','BuildError') → 'builderror':1        camelCase does NOT split
to_tsvector('simple','app.route')  → 'app.route':1         dotted names stay WHOLE
to_tsvector('english','how do I return a response if not authenticated')
                                   → 'authent' 'respons' 'return'
```

Three consequences:

1. **`simple` is mandatory.** The `english` config strips stopwords, and `is`, `not`, `in`,
   `and`, `or`, `if`, `do` are Python keywords. A code question loses most of its terms.
2. **No identifier-splitting column is needed** for snake_case, which is most of Python.
   camelCase class names are the only identifiers query expansion has to bridge.
3. **Query terms are OR-ed, not AND-ed.** `plainto_tsquery` ANDs, which would require a chunk
   to contain every word of a natural-language question and match essentially nothing.

---

## 12. Known problems

**Ingestion has no supervision.** A detached `Popen` with logs in `/tmp`. If it dies, status
stays `pending` and the frontend polls forever. No heartbeat, no retry, no dead-job sweep, and
nothing stops a second `/index` for a repo already in flight.

**Embedding retries hold a database connection.** Five attempts at a flat 15-second sleep, all
inside one open connection — up to 75 seconds of a held connection per failed batch. On a
large repo that is a long time to hold one.

**`/index` is unguarded.** Anyone who can reach it can make the server shallow-clone an
arbitrary repository. No size cap, clone timeout, rate limit, or concurrency limit.

**No ANN index.** Fine at this scale, not at 100×.

**`db/client.py` destroys the database** and `zerops.yml` runs it on deploy.

**Row 4 currently runs on Gemini, not Claude.** Any published number must name the model that
produced it. If the Anthropic workspace is fixed later, re-run row 4 rather than mixing models
across one table.

**The Anthropic key is identity-linked** and its `ANTHROPIC_WORKSPACE_ID` names a workspace
outside the key's organisation. Probing confirmed it behaves identically to a workspace ID
invented at random: a well-formed ID that decodes and then 404s.

---

## 13. What is built, and what is not

**Built and verified**

- Additive migration; bootstrap and migrated schemas verified identical
- `files` table; `/file` returns byte-exact content
- Two-stage ingest, tag pinning, chunk labels
- `RetrievalConfig` seam shared by `/ask` and the harness
- Lexical tokenizer and RRF fusion (tested, awaiting the `ast` corpus)
- Full eval harness: metrics, runnability guard, authoring CLI, golden-set schema
- Dual-provider LLM with fallback, `temperature=0`, model reporting
- `preflight.py`

**Specified but not built**

- `ingester/chunk_ast.py` — tree-sitter, one chunk per function
- `api/rerank.py` — `ms-marco-MiniLM-L-6-v2` cross-encoder
- `api/expand.py` — query expansion filtered against corpus vocabulary
- Abstention threshold and its calibration sweep
- The 30-question golden set — **the critical path**
- `RESULTS.md` and the README rewrite

**Deliberately out of scope** — job state machine, connection-handling fixes, `/index`
guards, and a CI regression gate.

---

## 14. Deployment

[zerops.yml](zerops.yml) defines two services: `app` (Python) and `frontend` (static).
`db/setup_extension.py` runs first and needs the superuser variables Zerops injects, because
`CREATE EXTENSION vector` requires superuser and the app's normal `DATABASE_URL` user cannot
do it. Missing superuser variables is a soft skip, not an error.

**The deployment is currently inactive** — the Zerops credits expired. The configuration is
kept because it works and because the pgvector superuser bootstrap is a non-trivial thing to
have solved, but nothing is running behind it.

When the frontend is served from the static service rather than FastAPI, it needs
`window.API_BASE` set to the API host; [static/app.js](static/app.js) defaults it to
same-origin.
