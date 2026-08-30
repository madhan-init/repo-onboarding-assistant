"""Retrieval configuration.

Every row of the ladder is a *config*, not a branch in retrieval.py. Adding a
feature means adding a flag and one code path, and the eval harness sweeps rows
by iterating LADDER.
"""
from dataclasses import dataclass
from typing import List, Optional

LINE_BUDGET = 500   # primary selection rule; see eval/metrics.select_by_line_budget
TOP_K = 5           # secondary, reported alongside


@dataclass(frozen=True)
class RetrievalConfig:
    name: str
    chunk_label: str = "line100"
    use_lexical: bool = False
    use_rerank: bool = False
    use_expansion: bool = False
    line_budget: int = LINE_BUDGET
    top_k: int = TOP_K
    rrf_k: int = 60
    candidate_pool: int = 50   # pulled from each arm before fusion
    rerank_pool: int = 50      # handed to the cross-encoder
    abstain_below: Optional[float] = None

    @property
    def needs_llm(self) -> bool:
        return self.use_expansion


# The ladder. Order is fixed: the index-time change lands first, then
# retrieval-time changes in the order they execute at query time.
#
# Expansion must come after hybrid -- it feeds the lexical arm, so placed any
# earlier it is a structural no-op.
LADDER: List[RetrievalConfig] = [
    RetrievalConfig(name="0-baseline", chunk_label="line100"),
    RetrievalConfig(name="1-ast", chunk_label="ast"),
    RetrievalConfig(name="2-hybrid", chunk_label="ast", use_lexical=True),
    RetrievalConfig(name="3-rerank", chunk_label="ast", use_lexical=True, use_rerank=True),
    RetrievalConfig(name="4-expansion", chunk_label="ast", use_lexical=True,
                    use_rerank=True, use_expansion=True),
]

BY_NAME = {c.name: c for c in LADDER}

# What /ask serves. Bump this as ladder rows land and are measured -- it is the
# only place the shipped default lives.
DEFAULT_CONFIG = "0-baseline"


def get(name: str) -> RetrievalConfig:
    if name not in BY_NAME:
        raise KeyError(f"unknown config {name!r}; known: {', '.join(BY_NAME)}")
    return BY_NAME[name]
