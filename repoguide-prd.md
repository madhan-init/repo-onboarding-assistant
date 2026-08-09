# PRD: RepoGuide — AI-Powered Repo Onboarding Assistant

**Author:** Madhan
**Event:** WeMakeDevs Zerops Challenge, Aug 8–9, 2026
**Status:** Draft for build

---

## 1. Problem

Joining an unfamiliar codebase is one of the biggest time sinks in software work. READMEs go stale, docs lag behind the code, and the actual source of truth — the code itself — takes hours to piece together just to answer basic questions like "where does auth happen?" or "what's the entry point?" This hits new hires, open-source contributors, and even experienced devs jumping into a teammate's repo.

**Core gap:** there's no fast, trustworthy way to ask a codebase questions and get grounded answers instead of guessing from stale docs or grepping blind.

## 2. Goal

Point RepoGuide at any GitHub repo URL and get a chat interface that answers natural-language questions about the codebase, with every answer grounded in and citing actual file paths and line ranges — not hallucinated APIs or invented structure.

## 3. Non-Goals (for this build)

- Not a general coding assistant (no code generation/editing of the target repo).
- Not handling private repos requiring auth (public repos only, for scope and time).
- Not a full semantic code-search replacement for large monorepos — optimized for small-to-medium repos in a hackathon timeframe.
- Not guaranteeing 100% accuracy — grounded-but-imperfect is acceptable; the priority is "never confidently invent," not "never be wrong."

## 4. Users

- **Primary:** a new contributor or new hire trying to understand an unfamiliar repo quickly.
- **Secondary:** a maintainer wanting a fast way to answer common "where is X handled?" questions without repeating themselves in issues/Discord.

## 5. Data Source

**GitHub public repos**, accessed via:
- `git clone` (shallow clone, e.g. `--depth 1`) for full file contents
- GitHub REST API for metadata (repo description, language breakdown, default branch, latest commit) — no auth needed for public repo reads at reasonable rate limits, but confirm rate-limit ceiling early since unauthenticated GitHub API calls are capped fairly low (60/hr) — a personal access token raises this substantially and is trivial to set up.

**Action item, do first:** confirm which chunking granularity is practical in the time available (function/class-aware chunking is ideal but harder to build fast; naive fixed-size line chunking with file-path tagging is an acceptable fallback if time is tight).

## 6. Architecture — 3 Services (Zerops)

**Service 1 — Ingester (worker)**
- Accepts a repo URL, shallow-clones it
- Walks the file tree, filters to relevant files (skip binaries, node_modules, build artifacts, lockfiles)
- Chunks source files and docs, tagged with `{file_path, start_line, end_line, chunk_type}`
- Generates embeddings per chunk
- Extracts lightweight repo metadata: language breakdown, likely entry point(s), dependency manifest, top-level folder structure — feeds the auto-generated overview
- Writes embeddings + metadata to Service 2

**Service 2 — Vector DB (Postgres + pgvector, or Qdrant)**
- `repos` — id, url, indexed_at, status, metadata (entry point, languages, folder structure summary)
- `chunks` — repo_id, file_path, start_line, end_line, chunk_type, embedding, raw_text

**Service 3 — Chat API (FastAPI)**
- `POST /index` — kicks off ingestion for a new repo URL, returns status (indexing may take a bit for larger repos — return immediately, poll for completion)
- `GET /overview?repo_id=` — auto-generated "start here" summary (entry point, structure, how to run it), generated once at index time
- `POST /ask` — embeds the question, retrieves top-k relevant chunks, sends to Claude with strict grounding instructions: answer only from retrieved context, cite `file:line` for every claim, explicitly say "not found in indexed context" rather than guessing

## 7. MVP Scope for the 48-Hour Build

**Must-have (demo-critical):**
- Ingester that clones + chunks + embeds a real repo end-to-end
- Vector DB live on Zerops with working similarity search
- `/ask` endpoint returning grounded answers with file:line citations
- One clean live demo: index a fresh repo in front of judges, ask a real question, show the cited answer

**Nice-to-have (if time remains):**
- Auto-generated repo overview at index time
- Simple chat UI + file-tree sidebar
- "Suggested first questions" based on detected repo type

**Explicitly cut for this build:**
- Private repo support / GitHub auth flow
- Multi-repo cross-referencing
- Diff-aware re-indexing on new commits

## 8. Success Criteria for Judging

- Live on Zerops, not localhost — reachable and functional through judging window
- Live indexing of a repo the judges pick, not a pre-baked demo repo only
- Every answer traceable to a real file:line — the visceral "it's not hallucinating" moment
- Can explain the RAG pipeline, chunking strategy, and every AI-assisted piece of code

## 9. Key Risks

| Risk | Mitigation |
|---|---|
| GitHub API rate limits during live demo indexing | Use a personal access token (raises limit substantially), pre-warm/cache a fallback repo just in case |
| Large repos take too long to index live | Cap file count/size for the demo; pick a small-to-medium repo for the live show |
| Naive chunking hurts answer quality | Fall back to file-path-tagged fixed-size chunks if function-aware chunking isn't feasible in time; still enforces citation grounding |
| Claude answers without real grounding (hallucination) | Strict prompt: only answer from retrieved chunks, explicitly refuse/flag when context is insufficient |

## 10. Tech Stack

- Python + FastAPI (ingester + chat API)
- PostgreSQL + pgvector (or Qdrant) on Zerops
- Claude API for grounded Q&A and repo overview generation
- GitPython or plain `git` CLI for cloning
- Frontend: chat UI + file-tree sidebar (Next.js or HTML + htmx)

## 11. Immediate Next Step

Confirm chunking approach (function-aware vs. fixed-size) and GitHub API rate-limit handling before building the ingester — these two decisions shape everything downstream.
