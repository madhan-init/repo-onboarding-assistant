"""Ingestion pipeline.

Split into two stages so one clone can be chunked several ways:

    clone -> store files      (once per repo)
    chunk -> embed -> store   (repeatable, once per chunk_label)

That is what makes the AST-vs-line-based comparison cheap: same corpus, same
file content, two chunk labels living side by side in `chunks`.

    uv run python3 ingester/run.py <repo_id> <github_url> [--ref v3.0.0]
                                  [--label ast] [--skip-metadata]
"""
import argparse
import json
import logging
import os
import shutil
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.client import get_connection
from ingester.chunk import chunk_repo
from ingester.clone import clone_repo
from ingester.embed import embed_and_store_chunks
from ingester.files import store_files
from ingester.metadata import generate_metadata

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ensure_repo_row(repo_id: str, url: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO repos (id, url, status) VALUES (%s, %s, 'pending') "
                "ON CONFLICT (id) DO NOTHING",
                (repo_id, url),
            )


def update_repo_status(repo_id: str, status: str, error: str = None, metadata: dict = None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            if metadata:
                cur.execute(
                    "UPDATE repos SET status = %s, error = %s, metadata = %s, "
                    "indexed_at = now() WHERE id = %s",
                    (status, error, json.dumps(metadata), repo_id),
                )
            else:
                cur.execute(
                    "UPDATE repos SET status = %s, error = %s WHERE id = %s",
                    (status, error, repo_id),
                )


def clear_label(repo_id: str, chunk_label: str) -> int:
    """Drop only this label's chunks, so re-ingesting one arm cannot duplicate rows."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM chunks WHERE repo_id = %s AND chunk_label = %s",
                (repo_id, chunk_label),
            )
            return cur.rowcount


def run_ingestion(repo_id: str, url: str, ref: str = None, chunk_label: str = "line100",
                  skip_metadata: bool = False):
    target_dir = None
    try:
        ensure_repo_row(repo_id, url)
        update_repo_status(repo_id, "indexing")

        target_dir = clone_repo(url, repo_id, ref=ref)

        stored = store_files(repo_id, target_dir, get_connection)
        logger.info(f"Stored {stored} files")

        removed = clear_label(repo_id, chunk_label)
        if removed:
            logger.info(f"Cleared {removed} existing '{chunk_label}' chunks")

        if chunk_label == "ast":
            from ingester.chunk_ast import chunk_repo_ast
            chunks = chunk_repo_ast(target_dir)
        else:
            chunks = chunk_repo(target_dir)
        logger.info(f"Generated {len(chunks)} chunks for label '{chunk_label}'")

        embed_and_store_chunks(repo_id, chunks, get_connection, chunk_label=chunk_label)
        logger.info("Stored chunks with embeddings")

        metadata = None
        if not skip_metadata:
            # Failures here are swallowed into metadata['overview'], so skip it
            # rather than write an API error string into user-facing text.
            metadata = generate_metadata(target_dir)

        update_repo_status(repo_id, "ready", metadata=metadata)
        logger.info(f"Ingestion complete for {repo_id} ({chunk_label})")

    except Exception as exc:
        logger.error(f"Ingestion failed: {exc}")
        update_repo_status(repo_id, "failed", error=str(exc))
        raise
    finally:
        if target_dir and os.path.exists(target_dir):
            shutil.rmtree(target_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_id")
    parser.add_argument("url")
    parser.add_argument("--ref", default=None, help="tag or branch to pin the clone to")
    parser.add_argument("--label", default="line100", help="chunk_label to store under")
    parser.add_argument("--skip-metadata", action="store_true")
    args = parser.parse_args()
    run_ingestion(args.repo_id, args.url, ref=args.ref,
                  chunk_label=args.label, skip_metadata=args.skip_metadata)
