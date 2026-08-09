# plan.md — RepoGuide

RAG-based repo Q&A tool. 3 Zerops services: Postgres (pgvector), API (FastAPI, includes ingestion as background task), frontend (optional, build last).

Build order: **DB schema → ingester → /ask endpoint → /index + /overview → deploy → frontend (if time left)**

Get something answering questions end-to-end on a real repo before polishing anything.

---

## Decisions (locked, don't re-litigate mid-build)

- **Embeddings:** OpenAI `text-embedding-3-small` (1536 dim) or Voyage AI — pick whichever key you set up first, don't burn time comparing.
- **Chunking:** fixed-size ~100 lines, 10-line overlap, tagged with file path + line range. No AST parsing. Not up for debate.
- **Ingester placement:** runs as a `BackgroundTasks` job inside the API service (Service 3), not a separate service. Only split it out if live-demo indexing visibly blocks the API — unlikely for a small demo repo.
- **Vector DB:** Postgres + pgvector extension, not a separate vector DB service. One less thing to wire on Zerops.
- **Frontend:** curl/Postman is an acceptable demo fallback. Build UI last, only if the pipeline is solid first.

---

## Stack

Python 3.11, FastAPI, PostgreSQL + pgvector, GitPython, Claude API (`claude-sonnet-4-6`), embeddings provider per decision above.

## Structure

```
repoguide/
  ingester/
    clone.py        # shallow git clone to /tmp/{repo_id}
    chunk.py         # fixed-size chunking with overlap
    embed.py         # batch embed + insert
    metadata.py      # entry point detection, language %, folder tree
    run.py            # orchestrates clone -> chunk -> embed -> metadata -> status update
  api/
    main.py
    routes_index.py    # POST /index, GET /index/{id}/status
    routes_ask.py       # POST /ask
    routes_overview.py  # GET /overview/{id}
    retrieval.py         # embed query, top-k cosine search, build context block
    prompt.py             # grounding prompt template
  db/
    schema.sql
    client.py
  requirements.txt
  .env.example
```

## DB schema (schema.sql)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE repos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url TEXT NOT NULL,
  status TEXT DEFAULT 'pending', -- pending|indexing|ready|failed
  error TEXT,
  metadata JSONB,
  indexed_at TIMESTAMPTZ
);

CREATE TABLE chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  repo_id UUID REFERENCES repos(id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  start_line INT,
  end_line INT,
  chunk_type TEXT,   -- code|doc|config
  raw_text TEXT,
  embedding VECTOR(1536)
);

CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops);
```

## Ingester logic

1. `git clone --depth 1 <url> /tmp/{repo_id}` — wrap in try/except, on failure set `status='failed'`, `error=<message>`, return early. Never let a bad URL hang the job silently.
2. Walk tree. Skip: `.git`, `node_modules`, `dist`, `build`, `.venv`, binaries (check extension allowlist: `.py .js .ts .go .java .rb .md .txt .yaml .json .toml` etc.), files >500KB.
3. Chunk per file: ~100 lines, 10-line overlap, tag `{file_path, start_line, end_line, chunk_type}`. `chunk_type` = `doc` if `.md`/`.txt`, `config` if `.json`/`.yaml`/`.toml`, else `code`.
4. Batch-embed chunks (batch size ~50–100 to avoid rate limits), bulk insert.
5. Extract metadata: folder tree (2 levels deep), entry point via pattern match (`main.py`, `app.py`, `index.js`, `server.js`, `main.go`, etc. — check root and common subfolders), language % by file extension count.
6. One Claude call: turn metadata into a short human-readable overview ("this is a FastAPI service, entry point is app/main.py, key folders are..."). Cache in `repos.metadata.overview`.
7. Set `status='ready'`, `indexed_at=now()`.

## API endpoints

- `POST /index {url}` → insert repo row (`status=pending`), kick off `run.py` as `BackgroundTasks`, return `{repo_id}` immediately.
- `GET /index/{repo_id}/status` → `{status, error?}` for polling.
- `GET /overview/{repo_id}` → cached overview from `repos.metadata`. 404 if not ready.
- `POST /ask {repo_id, question}` →
  - 400 if `repo.status != 'ready'`
  - embed question → cosine similarity search, top-k=8 chunks
  - build context block, each chunk labeled `[file_path:start_line-end_line]`
  - send to Claude with grounding prompt (below)
  - return `{answer, citations: [{file_path, start_line, end_line}]}`

## Grounding prompt (non-negotiable, this is the whole point of the project)

System instruction: answer **only** from the provided context chunks. Every claim must cite `file_path:start_line-end_line`. If the answer isn't in the retrieved context, say so explicitly — do not guess, do not fill gaps from general programming knowledge.

## Error handling minimums (don't skip — this is what "production-grade" means for judges)

- Bad/unreachable repo URL → clean `failed` status, not a crash
- `/ask` before indexing complete → clear 400, not a hang
- Embedding API failure mid-batch → retry once, then fail the repo cleanly with an error message
- Empty retrieval (no relevant chunks found) → Claude should say "not found in this repo" rather than hallucinate

## Cut list — do not build these

- Auth / private repos
- Multi-repo cross-referencing
- Re-indexing on new commits
- AST-aware chunking
- Anything beyond a minimal chat UI

## Deploy to Zerops

Order: Postgres service (enable pgvector) → API service (env: `DATABASE_URL`, `ANTHROPIC_API_KEY`, `EMBEDDING_API_KEY`) → frontend if built. Deploy a bare-bones version of the API on day 1 before all endpoints are finished, to surface Zerops config issues early.

## Demo script

1. `POST /index` with a repo the judges name live
2. Poll `/index/{id}/status` until `ready`
3. `POST /ask` with a real question about that repo
4. Show the answer with `file_path:line` citations on screen — this is the moment that proves it's not hallucinating
