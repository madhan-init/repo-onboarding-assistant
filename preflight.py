"""Verify every external dependency before an ingest or eval run.

Written because a revoked Fireworks key and an identity-linked Anthropic key both
failed silently until they were checked -- one of them mid-ingest. Run this first.

    uv run python3 preflight.py
"""
import os
import subprocess
import sys

import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, ".env"))

EMBED_DIM = 768
EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
results = []

print("preflight\n")


def check(name):
    def wrap(fn):
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {str(exc)[:160]}"
        results.append((ok, name, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name:22s} {detail}")
        return fn
    return wrap


@check("postgres + pgvector")
def _pg():
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "repoguide", "-d", "repoguide",
         "-tAc", "SELECT current_setting('server_version') || ' / pgvector ' || "
                 "(SELECT extversion FROM pg_extension WHERE extname='vector');"],
        capture_output=True, text=True, cwd=ROOT, timeout=60,
    )
    line = "\n".join(l for l in out.stdout.splitlines() if "level=warning" not in l).strip()
    return bool(line), line or "not running -- try: docker compose up -d"


@check("schema migrated")
def _schema():
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "repoguide", "-d", "repoguide",
         "-tAc", "SELECT (SELECT count(*) FROM information_schema.columns "
                 "WHERE table_name='chunks' AND column_name IN ('chunk_label','tsv')) || '/2 columns, ' || "
                 "(SELECT count(*) FROM information_schema.tables WHERE table_name='files') || '/1 files table';"],
        capture_output=True, text=True, cwd=ROOT, timeout=60,
    )
    line = "\n".join(l for l in out.stdout.splitlines() if "level=warning" not in l).strip()
    return line.startswith("2/2") and "1/1" in line, line or "run: uv run python3 db/migrate.py"


@check("fireworks embeddings")
def _fw():
    key = os.environ.get("FIREWORKS_API_KEY")
    if not key:
        return False, "FIREWORKS_API_KEY missing from .env"
    r = requests.post(
        "https://api.fireworks.ai/inference/v1/embeddings",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": EMBED_MODEL, "input": ["def send_file(path):"]}, timeout=60,
    )
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:120]}"
    dim = len(r.json()["data"][0]["embedding"])
    return dim == EMBED_DIM, f"dim={dim} (schema requires {EMBED_DIM})"


@check("anthropic (rows 0-3 ok without)")
def _anthropic():
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return False, "ANTHROPIC_API_KEY missing from .env"
    workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    headers = {"anthropic-workspace-id": workspace} if workspace else None
    client = anthropic.Anthropic(default_headers=headers)
    try:
        client.messages.create(model="claude-sonnet-4-6", max_tokens=8,
                               messages=[{"role": "user", "content": "ok"}])
    except Exception as exc:
        msg = str(exc)
        if "anthropic-workspace-id" in msg:
            return False, "identity-linked key -- set ANTHROPIC_WORKSPACE_ID in .env"
        return False, f"{type(exc).__name__}: {msg[:120]}"
    return True, "claude-sonnet-4-6 reachable" + (" (workspace header set)" if workspace else "")


if __name__ == "__main__":
    required = [r for r in results if r[1] != "anthropic (rows 0-3 ok without)"]
    failed_required = [r for r in required if not r[0]]
    llm_ok = next((r[0] for r in results if r[1].startswith("anthropic")), False)
    print()
    if failed_required:
        print(f"BLOCKED: {len(failed_required)} required check(s) failed")
        sys.exit(1)
    if not llm_ok:
        print("READY for ladder rows 0-3 (retrieval metrics need no LLM).")
        print("Row 4 (query expansion) and the demo are blocked until Anthropic works.")
    else:
        print("READY: all checks pass.")
