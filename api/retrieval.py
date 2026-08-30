"""Config-driven retrieval.

One code path serves every ladder row; a row is a RetrievalConfig, not a branch.
The same function backs `/ask` and the eval harness, so the measured system and
the shipped system cannot drift.

Rows 0-3 make no LLM call at all -- expansion is imported lazily -- which is why
they stay runnable with only an embedding key.
"""
import logging
import os
from typing import Dict, List, Optional

import requests

from api.fusion import reciprocal_rank_fusion
from api.lexical import build_tsquery
from config.retrieval import RetrievalConfig
from db.client import get_connection

logger = logging.getLogger(__name__)

from config.embedding import EMBED_DIM, EMBED_MODEL, EMBED_URL

_SELECT = "id, file_path, start_line, end_line, raw_text"


def embed_query(query: str) -> List[float]:
    api_key = os.environ.get("FIREWORKS_API_KEY")
    response = requests.post(
        EMBED_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": EMBED_MODEL, "input": [query]},
        timeout=60,
    )
    response.raise_for_status()
    embedding = response.json()["data"][0]["embedding"]
    if len(embedding) != EMBED_DIM:
        raise ValueError(f"expected {EMBED_DIM}-dim embedding, got {len(embedding)}")
    return embedding


def _row_to_chunk(row) -> Dict:
    return {
        "id": row[0],
        "file_path": row[1],
        "start_line": row[2],
        "end_line": row[3],
        "raw_text": row[4],
    }


def dense_search(repo_id: str, question: str, chunk_label: str, limit: int) -> List[Dict]:
    embedding = embed_query(question)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT}, 1 - (embedding <=> %s::vector) AS score
                FROM chunks
                WHERE repo_id = %s AND chunk_label = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (embedding, repo_id, chunk_label, embedding, limit),
            )
            rows = cur.fetchall()
    return [{**_row_to_chunk(r), "dense_score": r[5]} for r in rows]


def lexical_search(repo_id: str, question: str, chunk_label: str, limit: int,
                   extra_terms: Optional[List[str]] = None) -> List[Dict]:
    tsquery = build_tsquery(question, extra_terms)
    if not tsquery:
        return []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT}, ts_rank(tsv, q) AS score
                FROM chunks, to_tsquery('simple', %s) q
                WHERE repo_id = %s AND chunk_label = %s AND tsv @@ q
                ORDER BY ts_rank(tsv, q) DESC
                LIMIT %s
                """,
                (tsquery, repo_id, chunk_label, limit),
            )
            rows = cur.fetchall()
    return [{**_row_to_chunk(r), "lex_score": r[5]} for r in rows]


def corpus_vocabulary(repo_id: str, chunk_label: str) -> set:
    """Distinct lexemes actually present in the indexed chunks.

    Query expansion is filtered against this so it cannot inject terms that match
    nothing, or -- worse -- terms that match something unrelated.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # ts_stat() takes a SQL *string*, which psycopg3 cannot parameterise
            # safely (%L is not a valid placeholder). Unnest the tsvectors instead.
            cur.execute(
                """
                SELECT DISTINCT t.lexeme
                FROM chunks c, unnest(c.tsv) t
                WHERE c.repo_id = %s AND c.chunk_label = %s
                """,
                (repo_id, chunk_label),
            )
            return {r[0] for r in cur.fetchall()}


def search(repo_id: str, question: str, config: RetrievalConfig) -> List[Dict]:
    """Run the full retrieval pipeline for one config. Returns ranked chunks."""
    extra_terms = None
    if config.use_expansion:
        from api.expand import expand_query  # lazy: rows 0-3 need no LLM
        extra_terms = expand_query(question, repo_id, config.chunk_label)

    dense = dense_search(repo_id, question, config.chunk_label, config.candidate_pool)

    if config.use_lexical:
        lexical = lexical_search(repo_id, question, config.chunk_label,
                                 config.candidate_pool, extra_terms)
        ranked = reciprocal_rank_fusion([dense, lexical], k=config.rrf_k)
    else:
        ranked = dense

    if config.use_rerank:
        from api.rerank import rerank  # lazy: keeps torch off the import path
        ranked = rerank(question, ranked[:config.rerank_pool])

    return ranked


def should_abstain(ranked: List[Dict], config: RetrievalConfig) -> bool:
    """Refuse before spending the LLM call.

    Reads the cross-encoder score -- the only calibrated relevance signal here.
    Cosine is uncalibrated and repo-dependent; an RRF score is 1/(k+rank) and so
    depends only on rank, scoring the top hit identically whether it is perfect
    or useless.
    """
    if config.abstain_below is None:
        return False
    if not ranked:
        return True
    top = ranked[0].get("rerank_score")
    if top is None:
        raise ValueError(
            "abstain_below is set but no rerank_score is present -- abstention "
            "requires use_rerank=True"
        )
    return top < config.abstain_below


def build_context_block(chunks: List[Dict]) -> str:
    """Citation contract: [file_path:start-end] is scraped back out of the answer."""
    return "\n\n".join(
        f"[{c['file_path']}:{c['start_line']}-{c['end_line']}]\n{c['raw_text']}"
        for c in chunks
    )
