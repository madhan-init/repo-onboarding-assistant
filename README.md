# Repo Onboarding Assistant

A codebase RAG assistant that lets developers ask natural-language questions about unfamiliar GitHub repositories and get **answers grounded in exact files and line ranges**.

## How It Works

```text
GitHub Repository
       ↓
Clone → Chunk → Embed
       ↓
PostgreSQL + pgvector
       ↓
Natural Language Query
       ↓
Vector Retrieval → Context → LLM
       ↓
Cited Answer
```

## Features

* Index GitHub repositories automatically
* Search source code and documentation using semantic retrieval
* Generate answers with exact file and line citations
* Browse indexed repository files
* PostgreSQL + pgvector based vector search
* Configurable retrieval pipeline
* Built-in retrieval evaluation and testing

## Tech Stack

**Backend:** Python, FastAPI
**Database:** PostgreSQL, pgvector
**Embeddings:** Fireworks — `nomic-ai/nomic-embed-text-v1.5`
**LLM:** Anthropic / Gemini
**Frontend:** HTML, CSS, JavaScript
**Testing:** pytest

## Quick Start

### 1. Start PostgreSQL

```bash
docker compose up -d
```

### 2. Run migrations

```bash
uv run python3 db/migrate.py
```

### 3. Configure environment

Create `.env`:

```env
FIREWORKS_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
GEMINI_API_KEY=your_key
DATABASE_URL=your_database_url
LLM_PROVIDER=auto
```

### 4. Start the application

```bash
uv run python3 preflight.py
uv run uvicorn api.main:app --reload --port 8000
```

Open `http://localhost:8000`.

## Index a Repository

```bash
uv run python3 ingester/run.py <repo_id> <github_url>
```

The repository is cloned, chunked, embedded, and stored in PostgreSQL.

## API

| Method | Endpoint              | Purpose                          |
| ------ | --------------------- | -------------------------------- |
| `POST` | `/index`              | Index a GitHub repository        |
| `POST` | `/ask`                | Ask questions about a repository |
| `GET`  | `/overview/{repo_id}` | Repository status and metadata   |
| `GET`  | `/file/{repo_id}`     | Retrieve a complete file         |

## Evaluation

```bash
uv run python3 -m pytest
uv run python3 eval/author.py
uv run python3 eval/run.py
```

The evaluation framework measures **recall, MRR, coverage, and retrieval differences** across configurations.

## Project Structure

```text
api/          FastAPI API and retrieval
config/       Embedding and retrieval configuration
db/           PostgreSQL schema and migrations
ingester/     Repository ingestion and chunking
eval/         Retrieval evaluation
tests/        Test suite
static/       Frontend
```

## Status

Currently runs locally with working:

* Repository indexing
* Semantic retrieval
* File browsing
* Citation-grounded answers
* Evaluation framework

AST chunking, reranking, query expansion, and retrieval abstention are in progress.

## License

Add your chosen license before publishing the repository.
