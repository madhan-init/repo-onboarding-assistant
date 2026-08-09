import os
import logging
import time
from typing import List, Dict
import voyageai

logger = logging.getLogger(__name__)

# Voyage AI Free Tier: 3 RPM (Requests Per Minute) and 10K TPM (Tokens Per Minute).
# BATCH_SIZE = 2 ensures single requests stay well under 10K tokens.
BATCH_SIZE = 2

def get_embeddings(texts: List[str]) -> List[List[float]]:
    vo = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY", os.environ.get("EMBEDDING_API_KEY")))
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = vo.embed(texts, model="voyage-3", input_type="document")
            return response.embeddings
        except Exception as e:
            err_str = str(e)
            if attempt < max_retries - 1:
                wait_time = 65  # Full minute reset for rate limit window
                logger.warning(f"Embedding attempt {attempt + 1} failed: {err_str}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Embedding failed after {max_retries} attempts: {err_str}")
                raise e

def embed_and_store_chunks(repo_id: str, chunks: List[Dict], get_connection):
    with get_connection() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(chunks), BATCH_SIZE):
                batch = chunks[i:i+BATCH_SIZE]
                texts = [c['raw_text'] for c in batch]
                
                try:
                    embeddings = get_embeddings(texts)
                except Exception as e:
                    logger.error(f"Failed to embed batch: {e}")
                    raise e
                
                for j, chunk in enumerate(batch):
                    cur.execute(
                        """
                        INSERT INTO chunks (repo_id, file_path, start_line, end_line, chunk_type, raw_text, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (repo_id, chunk['file_path'], chunk['start_line'], chunk['end_line'], chunk['chunk_type'], chunk['raw_text'], embeddings[j])
                    )
                
                # Pause 21 seconds between batches to respect the 3 Requests Per Minute (3 RPM) free-tier limit
                if i + BATCH_SIZE < len(chunks):
                    time.sleep(21)


