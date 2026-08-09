import sys
import os
import logging
import json

# Add parent dir to path so we can import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.client import get_connection
from ingester.clone import clone_repo
from ingester.chunk import chunk_repo
from ingester.embed import embed_and_store_chunks
from ingester.metadata import generate_metadata

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_repo_status(repo_id: str, status: str, error: str = None, metadata: dict = None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            if metadata:
                cur.execute(
                    "UPDATE repos SET status = %s, error = %s, metadata = %s, indexed_at = now() WHERE id = %s",
                    (status, error, json.dumps(metadata), repo_id)
                )
            else:
                cur.execute(
                    "UPDATE repos SET status = %s, error = %s WHERE id = %s",
                    (status, error, repo_id)
                )

def run_ingestion(repo_id: str, url: str):
    target_dir = None
    try:
        update_repo_status(repo_id, 'indexing')
        
        target_dir = clone_repo(url, repo_id)
        
        chunks = chunk_repo(target_dir)
        logger.info(f"Generated {len(chunks)} chunks")
        
        embed_and_store_chunks(repo_id, chunks, get_connection)
        logger.info(f"Stored chunks with embeddings")
        
        metadata = generate_metadata(target_dir)
        logger.info(f"Generated metadata")
        
        update_repo_status(repo_id, 'ready', metadata=metadata)
        logger.info(f"Ingestion complete for {repo_id}")
        
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        update_repo_status(repo_id, 'failed', error=str(e))
    finally:
        if target_dir and os.path.exists(target_dir):
            import shutil
            shutil.rmtree(target_dir)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python run.py <repo_id> <url>")
        sys.exit(1)
    
    run_ingestion(sys.argv[1], sys.argv[2])
