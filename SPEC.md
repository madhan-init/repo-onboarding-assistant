# Retrieval Improvements — Implementation Spec

Five retrieval features, measured against a hand-built test set, reported as a cumulative
ladder in the README. This document is the plan of record; every decision below was settled
deliberately and the reasoning is kept so it can be re-argued rather than re-derived.

---

## 0. Verified environment

Checked on 2026-08-30, not assumed:

| Thing | State |
|---|---|
| Postgres | 16.14, **pgvector 0.8.6**, via `docker compose up -d` |
| Existing data | `repos=4, chunks=232` — **`db/client.py` must never be run**, it drops both tables |
| Embeddings | Fireworks `nomic-ai/nomic-embed-text-v1.5` → **768 dims**, matches `VECTOR(768)` |
| Anthropic | ⚠️ **BLOCKED** — identity-linked key needs `ANTHROPIC_WORKSPACE_ID` in `.env` |
| Gemini | works (unused; fallback only) |
| Machine | Apple M2, 16GB, py3.11 arm64, MPS available |
| Deps resolve | `tree-sitter 0.26.0`, `tree-sitter-python 0.25.0`, `sentence-transformers 6.0.0`, `torch 2.13.0` |

**tsvector behaviour (measured, not assumed):**

```
to_tsvector('simple','send_file')      -> 'file':2 'send':1     <- snake_case splits FREE
to_tsvector('simple','url_for')        -> 'for':2 'url':1
to_tsvector('simple','BuildError')     -> 'builderror':1        <- camelCase does NOT split
to_tsvector('english','how do I return a response if not authenticated')
                                       -> 'authent' 'respons' 'return'   <- keywords destroyed
```

Consequences: `simple` is mandatory (`english` deletes Python keywords), no
identifier-splitting column is needed for snake_case, and camelCase class names
(`BuildError`, `MethodNotAllowed`) are the only identifiers query expansion must bridge.

---

## 1. Corpus

- **flask** — pinned at tag **3.1.3** (commit `22d92470`). **514 chunks / 215 files.**
  Carries every published number.

  `.rst` is indexed. flask writes its entire 104-file manual in reStructuredText, and excluding it
  left the tool unable to answer any prose question: "how do I upload and handle files in a form"
  returned `send_file()` — sending a file *to* a user — because the actual answer in
  `docs/patterns/fileuploads.rst` was invisible. With docs indexed that file is now the top hit.
  Cost: the AST chunker cannot parse `.rst`, so ~40% of the corpus is identical between the AST and
  baseline arms, diluting that row. Offset by the Python-only cut in section 6.
- **this repo** — 39 chunks. Demo only, never scored. At 39 chunks a top-50 rerank pool
  is the entire database, so features 1–3 are undefined here.

---

## 2. The ladder

Five rows, each adding one feature to the row above. Order is fixed: the index-time change
lands first, then retrieval-time changes in the order they execute at query time.

| # | Row | Change | Needs LLM |
|---|---|---|---|
| 0 | baseline | current system, 100-line chunks, `top_k` by budget | no |
| 1 | +AST chunking | tree-sitter, one chunk per function | no |
| 2 | +hybrid | `simple` tsvector + RRF k=60 | no |
| 3 | +rerank | pool 50 → MiniLM cross-encoder → top 5 | no |
| 4 | +expansion | LLM emits identifiers, filtered against corpus vocab | **yes** |

Expansion must come after hybrid — it feeds the lexical arm, so placed earlier it is a
structural no-op. Rows 0–3 need no API key beyond Fireworks; only row 4 is blocked on
`ANTHROPIC_WORKSPACE_ID`.

**Abstention (feature 4) is not a ladder row.** Refusing correctly means retrieving nothing,
so a recall metric scores correct refusals as failures. It gets its own table.

---

## 3. Metrics

**Primary — recall at a fixed line budget.** Retrieve ranked chunks until cumulative lines
would exceed ~500, then score. Baseline chunks are 100 lines and AST chunks ~20, so at fixed
`k` the baseline would receive ~5× more context and the metric would be biased toward the
config we are trying to beat. A line budget removes that.

**Secondary — `recall@5`**, reported alongside for readers who expect the standard number.

Definitions, for a question with gold spans `G`:
- A retrieved chunk **hits** a gold span if their `[start_line, end_line]` ranges overlap.
- `recall` = fraction of `G` hit by at least one retrieved chunk; aggregate = mean over questions.
- `MRR` = reciprocal rank of the first chunk hitting any gold span.
- `coverage` = fraction of gold lines contained in the union of retrieved chunks.

**Reporting — paired, not just aggregate.** With 20 answerable questions one question is worth
5 recall points, and per-feature marginals are realistically 2–8 points. Every ladder step
reports **improved / unchanged / regressed** counts across the 20, alongside the aggregate.
"Hybrid fixed 6 and broke 2" is both more honest and more useful than "+4.2 points".

Expect several rows to land inside the noise. The honest table says so.

---

## 4. Test set

30 questions, **written by hand**, stored at `eval/golden/v1.json`.

- **20 answerable**, each with gold `(file_path, start_line, end_line)` spans.
- **10 unanswerable**, for abstention. Three sources: Werkzeug/Jinja2 internals (real flask
  dependencies, genuinely absent from the repo), features flask does not have, and
  false-premise questions.

At n=10 each unanswerable question moves the refusal rate by 10 points. Accepted.

`eval/author.py` prompts for question → file → line range and **validates the span against
the live index before writing**. A span no chunk covers scores zero forever and looks
identical to a retrieval failure; this makes that unrecordable.

---

## 5. Schema changes — all non-destructive

`repos` and `chunks` hold live data. Changes go in `db/migrate.py`, which is additive and
idempotent. `db/schema.sql` and `db/client.py` keep their existing destructive behaviour and
are simply not run.

```sql
CREATE TABLE IF NOT EXISTS files (
  repo_id   UUID REFERENCES repos(id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  content   TEXT NOT NULL,
  sha       TEXT,
  PRIMARY KEY (repo_id, file_path)
);

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS chunk_label TEXT NOT NULL DEFAULT 'line100';

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', raw_text)) STORED;

CREATE INDEX IF NOT EXISTS chunks_tsv_idx   ON chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS chunks_label_idx ON chunks (repo_id, chunk_label);
```

The generated column backfills itself — no migration script for existing rows.

**Why the `files` table.** `/file/{repo_id}` currently rebuilds a file by ordering chunks on
`start_line` and trimming a fixed 10-line overlap. AST chunks leave gaps between functions and
have no uniform overlap, so that logic would silently drop lines — and the demo GIF clicks
straight into that view. Storing content once decouples file viewing from chunk shape
permanently, and the stitching code gets deleted.

---

## 6. Components

```
config/retrieval.py     RetrievalConfig — one object drives all five rows
db/migrate.py           additive migration (above)
ingester/chunk_ast.py   tree-sitter chunker
ingester/run.py         restructured: clone+files stage, then repeatable chunk+embed stage
api/rerank.py           MiniLM cross-encoder, lazy-loaded, MPS
api/expand.py           query expansion + corpus-vocabulary filter
api/retrieval.py        config-driven: dense / lexical / RRF / rerank / threshold
eval/author.py          question authoring CLI
eval/metrics.py         recall@budget, recall@5, MRR, coverage, paired diffs
eval/run.py             runs one config over the golden set, writes results
preflight.py            every check from section 0, as a single pass/fail
```

### `RetrievalConfig`

One code path serves every ladder row; a row is a config, not a branch.

```python
RetrievalConfig(
    chunk_label   = "line100" | "ast",
    use_lexical   = bool,     # row 2+
    use_rerank    = bool,     # row 3+
    use_expansion = bool,     # row 4+
    line_budget   = 500,
    rrf_k         = 60,
    rerank_pool   = 50,
    abstain_below = float | None,
)
```

`/ask` currently hardcodes `top_k=8` and exposes no retrieval configuration. It takes an
optional config so the app and the harness exercise the same code.

### AST chunker

One chunk per function/method. Decisions worth flagging because they are mine, not yours:

- **Embedded text** = module imports + enclosing class signature + function source.
  **Stored `raw_text`** = function source only. **`start_line`/`end_line`** = the real function
  span, so gold-span overlap scoring stays honest.
- **Module-level code** (constants, module docstring, top-level statements) becomes one
  "preamble" chunk per file. Without this, AST chunking silently loses coverage and would post
  a recall drop unrelated to function chunking.
- **Non-Python files** (flask has 54 of 134) fall back to the line-based chunker.

### Reranker

`cross-encoder/ms-marco-MiniLM-L-6-v2`, ~90MB, loaded once, MPS on M2. It was trained on web
prose, not code — **if row 3 comes back flat, that result is ambiguous** between "reranking
doesn't help code retrieval" and "wrong reranker." Say so in the README rather than claiming
the first.

### Query expansion

LLM emits candidate identifiers (snake_case / CamelCase), which are then **filtered against the
distinct token vocabulary actually present in the indexed chunks** — one SQL query over
`chunks.tsv`. Surviving terms join the lexical query; the original question goes to the dense
query unchanged. Filtering stops the expansion injecting terms that match nothing, or worse,
match something unrelated.

Because `simple` already splits snake_case, expansion's real job is narrower than first
assumed: bridging natural language to **camelCase** identifiers, and to domain vocabulary
absent from the question.

### Abstention

Threshold reads the **cross-encoder score** — the only calibrated relevance signal in the
pipeline. Cosine similarity is uncalibrated and repo-dependent; RRF scores are `1/(k+rank)`
and depend only on rank, so the top hit scores identically whether it is perfect or useless.

Calibration: sweep thresholds, pick the highest refusal rate on the 10 unanswerable questions
subject to refusing **≤10%** of the 20 answerable. Wrongly refusing an answerable question
makes the tool feel broken; a hedged answer merely disappoints. Publish the sweep curve
alongside the chosen point, and state that a cutoff fit on 30 questions is fit to those 30.

Note `api/prompt.py` already instructs abstention, and `routes_ask.py`'s `"not found"` branch
only fires when retrieval returns zero chunks — which never happens. What is new is refusing
*before* spending the LLM call.

---

## 7. Sequence

**Stage A — foundations** (no keys beyond Fireworks)
`db/migrate.py`, `files` table + `/file` rewrite, `RetrievalConfig`, `/ask` unpinned from
`top_k=8`, `preflight.py`.

**Stage B — harness** (no LLM)
`eval/metrics.py`, `eval/run.py`, `eval/author.py`. Testable against the 232 chunks already
in the database.

**Stage C — you write the 30 questions.** Runs in parallel with A and B; the authoring CLI is
ready before you need it. This is the critical path and the likeliest place to stall.

**Stage D — ingest flask and measure rows 0–3.** Two ingests (`line100`, `ast`), one `files`
population, five eval runs. No LLM calls at all.

**Stage E — row 4 + abstention + README.** Blocked on `ANTHROPIC_WORKSPACE_ID`. Then the
threshold sweep, README restructure, demo GIF.

---

## 8. README

Restructured around the retrieval work. Zerops moves to a deployment footnote near the bottom —
the config is real evidence of shipping a multi-service app with a database extension, but
there is no live link behind it now, so it stops being the opening paragraph.

Contents: the ladder table, the abstention table, the demo GIF, a one-command reproduce path,
and a limitations section stating n=20, the out-of-domain reranker, single-corpus results, and
the threshold's fit to 30 questions. Disclosed limitations read as rigour; discovered ones
read as oversight.

---

## 9. Known risks

- **n=20 is thin.** Paired reporting extracts real signal but cannot manufacture it. Several
  rows will be inside the noise.
- **MiniLM is out of domain** for code. A flat row 3 is uninterpretable, not negative.
- **Row 4 is blocked** until `ANTHROPIC_WORKSPACE_ID` is set.
- **`db/client.py` destroys the database.** It is not part of any workflow here.
- **The threshold does not transfer** to another repo.
