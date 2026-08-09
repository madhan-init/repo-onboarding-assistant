import os
import logging
import time
from typing import List, Dict
import voyageai

logger = logging.getLogger(__name__)

BATCH_SIZE = 100

def get_embeddings(texts: List[str]) -> List[List[float]]:
    vo = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY", os.environ.get("EMBEDDING_API_KEY")))
    
    try:
        response = vo.embed(texts, model="voyage-3", input_type="document")
        return response.embeddings
    except Exception as e:
        logger.warning(f"Embedding failed for a chunk, retrying once. Error: {e}")
        time.sleep(2)
        response = vo.embed(texts, model="voyage-3", input_type="document")
        return response.embeddings

def embed_and_store_chunks(repo_id: str, chunks: List[Dict], get_connection):
    # Process in batches
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
