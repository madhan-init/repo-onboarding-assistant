"""Reciprocal Rank Fusion.

Merges the dense and lexical result lists for the hybrid row. RRF is scale-free --
it needs no normalisation between cosine distance and ts_rank, which live on
incompatible scales -- and has no weight to tune, which matters at n=20 where any
tuned weight would be fitting noise.

Note the consequence for abstention: an RRF score is 1/(k+rank) summed over lists,
so it depends only on *rank*, never on relevance. The top hit scores identically
whether it is perfect or useless. Thresholding therefore reads the cross-encoder
score (see api/rerank.py), never this one.
"""
from typing import Dict, List

DEFAULT_K = 60


def reciprocal_rank_fusion(result_lists: List[List[Dict]], k: int = DEFAULT_K) -> List[Dict]:
    """Fuse ranked lists of chunks, deduplicating by chunk id.

    Returns copies with an `rrf_score` attached, ordered best-first. Input dicts
    are never mutated.
    """
    scores: Dict[object, float] = {}
    chunks: Dict[object, Dict] = {}
    order: List[object] = []

    for results in result_lists:
        for rank, chunk in enumerate(results, start=1):
            cid = chunk["id"]
            if cid not in chunks:
                chunks[cid] = dict(chunk)
                order.append(cid)
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)

    for cid in order:
        chunks[cid]["rrf_score"] = scores[cid]

    # Ties break on first-appearance order, which keeps single-list fusion stable.
    return sorted(
        (chunks[cid] for cid in order),
        key=lambda c: (-c["rrf_score"], order.index(c["id"])),
    )
