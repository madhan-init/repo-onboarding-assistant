import sys
import uuid
import logging
from db.client import get_connection
from ingester.run import run_ingestion

logging.basicConfig(level=logging.INFO)

def main(url):
    repo_id = str(uuid.uuid4())
    print(f"Testing ingestion for {url} with ID {repo_id}")
    
    # Insert dummy repo row
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO repos (id, url, status) VALUES (%s, %s, %s)",
                (repo_id, url, 'pending')
            )
            
    print("Inserted repo row, running ingestion...")
    run_ingestion(repo_id, url)
    
    # Check if chunks are populated
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM chunks WHERE repo_id = %s", (repo_id,))
            chunk_count = cur.fetchone()[0]
            
            cur.execute("SELECT status, metadata FROM repos WHERE id = %s", (repo_id,))
            status, metadata = cur.fetchone()
            
    print(f"Ingestion complete. Status: {status}")
    print(f"Chunks populated: {chunk_count}")
    print(f"Metadata: {metadata}")

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/octocat/Hello-World"
    main(url)
