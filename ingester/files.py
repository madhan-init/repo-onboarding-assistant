"""Store full file content at ingest time.

`chunks` used to be the only record of file content, so /file rebuilt a file by
ordering chunks on start_line and trimming a fixed 10-line overlap. Function-level
AST chunks leave gaps between functions and have no uniform overlap, so that logic
would silently drop lines -- and the demo clicks straight into that view.

Storing content once decouples file viewing from chunk shape permanently, and lets
the same clone be re-chunked under several labels without re-cloning.
"""
import hashlib
import logging
import os
from ingester.chunk import ALLOW_EXTENSIONS, IGNORE_DIRS, MAX_FILE_SIZE

logger = logging.getLogger(__name__)


def store_files(repo_id: str, target_dir: str, get_connection) -> int:
    """Write every indexable file's full content. Idempotent per (repo_id, path)."""
    stored = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for root, dirs, filenames in os.walk(target_dir):
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                for filename in filenames:
                    path = os.path.join(root, filename)
                    rel = os.path.relpath(path, target_dir)
                    if os.path.splitext(filename)[1].lower() not in ALLOW_EXTENSIONS:
                        continue
                    try:
                        if os.path.getsize(path) > MAX_FILE_SIZE:
                            continue
                        with open(path, "r", encoding="utf-8") as handle:
                            content = handle.read()
                    except Exception as exc:
                        logger.warning(f"skipping {rel}: {exc}")
                        continue
                    cur.execute(
                        """
                        INSERT INTO files (repo_id, file_path, content, sha)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (repo_id, file_path)
                        DO UPDATE SET content = EXCLUDED.content, sha = EXCLUDED.sha
                        """,
                        (repo_id, rel, content,
                         hashlib.sha256(content.encode("utf-8")).hexdigest()),
                    )
                    stored += 1
    return stored
