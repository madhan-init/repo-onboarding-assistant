import os
import logging
import time
from typing import List, Dict
import requests

logger = logging.getLogger(__name__)

# Fireworks AI limit is much higher, we can use a larger batch size
BATCH_SIZE = 50

def get_embeddings(texts: List[str]) -> List[List[float]]:
    url = "https://api.fireworks.ai/inference/v1/embeddings"
    api_key = os.environ.get("FIREWORKS_API_KEY", os.environ.get("VOYAGE_API_KEY"))
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "nomic-ai/nomic-embed-text-v1.5",
        "input": texts
    }
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            return [item['embedding'] for item in result['data']]
        except Exception as e:
            err_str = str(e)
            if attempt < max_retries - 1:
                wait_time = 15  # wait 15 seconds before retrying
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
                
                # Small pause to avoid hammering the API
                if i + BATCH_SIZE < len(chunks):
                    time.sleep(0.5)


