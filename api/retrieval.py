import os
import logging
from typing import List, Dict
import voyageai
from db.client import get_connection

logger = logging.getLogger(__name__)

def embed_query(query: str) -> List[float]:
    vo = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY", os.environ.get("EMBEDDING_API_KEY")))
    response = vo.embed([query], model="voyage-3", input_type="query")
    return response.embeddings[0]

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
