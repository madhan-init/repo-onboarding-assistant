"""Additive, idempotent schema migration.

Unlike db/client.py -- which DROPs and recreates both tables -- this only ever adds.
It is safe to run against a database holding indexed repos, and safe to run twice.

    uv run python3 db/migrate.py
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.client import get_connection

MIGRATIONS = [
    (
        "files table",
        """
        CREATE TABLE IF NOT EXISTS files (
          repo_id   UUID REFERENCES repos(id) ON DELETE CASCADE,
          file_path TEXT NOT NULL,
          content   TEXT NOT NULL,
          sha       TEXT,
          PRIMARY KEY (repo_id, file_path)
        );
        """,
    ),
    (
        "chunks.chunk_label",
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS chunk_label TEXT NOT NULL DEFAULT 'line100';",
    ),
    (
        "chunks.tsv (generated, backfills itself)",
        """
        ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector
          GENERATED ALWAYS AS (to_tsvector('simple', raw_text)) STORED;
        """,
    ),
    (
        "chunks_tsv_idx (GIN)",
        "CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING GIN (tsv);",
    ),
    (
        "chunks_label_idx",
        "CREATE INDEX IF NOT EXISTS chunks_label_idx ON chunks (repo_id, chunk_label);",
    ),
]


def migrate():
    with get_connection(register=False) as conn:
        with conn.cursor() as cur:
            for name, sql in MIGRATIONS:
                cur.execute(sql)
                print(f"  ok  {name}")

            cur.execute("SELECT count(*) FROM repos")
            repos = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM chunks")
            chunks = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM files")
            files = cur.fetchone()[0]
    print(f"\nrepos={repos} chunks={chunks} files={files}")


if __name__ == "__main__":
    migrate()
