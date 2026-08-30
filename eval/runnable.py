"""Decide whether a config can actually be measured.

Exists because of a specific failure: running the `1-ast` row before any AST chunks
had been ingested did not error. The retriever simply returned nothing and the
harness printed `recall=0.000` -- a fake number, indistinguishable from a genuine
retrieval failure, in a project whose entire point is honest measurement.

Facts are injected rather than looked up so this stays testable.
"""
from typing import Dict, List

from config.retrieval import RetrievalConfig


def missing_requirements(config: RetrievalConfig, chunk_counts: Dict[str, int],
                         module_available: Dict[str, bool], llm_ok: bool) -> List[str]:
    """Return every reason this config cannot be measured. Empty means runnable."""
    reasons = []

    if not chunk_counts.get(config.chunk_label):
        reasons.append(
            f"no chunks indexed under label '{config.chunk_label}' "
            f"(ingest it first, or this row would report a fake 0.000)"
        )
    if config.use_rerank and not module_available.get("api.rerank"):
        reasons.append("api.rerank is not implemented yet")
    if config.use_expansion:
        if not module_available.get("api.expand"):
            reasons.append("api.expand is not implemented yet")
        if not llm_ok:
            reasons.append("LLM unreachable (set ANTHROPIC_WORKSPACE_ID in .env)")
    return reasons
