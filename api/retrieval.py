import os
import logging
from typing import List, Dict
import requests
from db.client import get_connection

logger = logging.getLogger(__name__)

def embed_query(query: str) -> List[float]:
    url = "https://api.fireworks.ai/inference/v1/embeddings"
    api_key = os.environ.get("FIREWORKS_API_KEY", os.environ.get("VOYAGE_API_KEY"))
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "nomic-ai/nomic-embed-text-v1.5",
        "input": [query]
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    result = response.json()
    return result['data'][0]['embedding']

def search_chunks(repo_id: str, query: str, top_k: int = 8) -> List[Dict]:
    query_embedding = embed_query(query)
    
    chunks = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT file_path, start_line, end_line, raw_text, 1 - (embedding <=> %s::vector) AS similarity
                FROM chunks
                WHERE repo_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (query_embedding, repo_id, query_embedding, top_k))
            
            rows = cur.fetchall()
            for row in rows:
                chunks.append({
                    'file_path': row[0],
                    'start_line': row[1],
                    'end_line': row[2],
                    'raw_text': row[3],
                    'similarity': row[4]
                })
    return chunks

def build_context_block(chunks: List[Dict]) -> str:
    blocks = []
    for c in chunks:
        blocks.append(f"[{c['file_path']}:{c['start_line']}-{c['end_line']}]\n{c['raw_text']}")
    return "\n\n".join(blocks)
