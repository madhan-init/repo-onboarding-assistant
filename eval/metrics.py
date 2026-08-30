"""Deterministic retrieval metrics.

Everything here is pure: no database, no API calls, no LLM. That is what makes
rows 0-3 of the ladder runnable with no credentials and reproducible by anyone.

Chunks and gold spans are both dicts with `file_path`, `start_line`, `end_line`.
A chunk *hits* a gold span when they name the same file and their inclusive line
ranges overlap -- deliberately chunker-independent, so the same golden set scores
line-based and AST configurations without re-labelling.
"""
from typing import Dict, List


def chunk_lines(chunk: Dict) -> int:
    """Line count of a chunk. Ranges are inclusive on both ends."""
    return chunk["end_line"] - chunk["start_line"] + 1


def spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


def is_hit(chunk: Dict, gold: Dict) -> bool:
    return chunk["file_path"] == gold["file_path"] and spans_overlap(
        chunk["start_line"], chunk["end_line"], gold["start_line"], gold["end_line"]
    )


def select_by_line_budget(chunks: List[Dict], budget: int) -> List[Dict]:
    """Take ranked chunks until one more would exceed `budget` lines.

    This is the primary selection rule. Selecting a fixed `k` would hand the
    100-line baseline roughly 5x more context than ~20-line AST chunks and bias
    the comparison toward the configuration we are trying to beat.

    Always returns at least one chunk: a single chunk larger than the entire
    budget would otherwise score as retrieving nothing.
    """
    selected, used = [], 0
    for chunk in chunks:
        size = chunk_lines(chunk)
        if used + size > budget:
            break
        selected.append(chunk)
        used += size
    if not selected and chunks:
        selected = [chunks[0]]
    return selected


def select_top_k(chunks: List[Dict], k: int) -> List[Dict]:
    """Secondary selection rule, reported alongside the budget metric."""
    return chunks[:k]


def recall(retrieved: List[Dict], gold: List[Dict]) -> float:
    """Fraction of gold spans hit by at least one retrieved chunk."""
    if not gold:
        raise ValueError(
            "recall() called with no gold spans -- unanswerable questions are "
            "scored on abstention, not recall"
        )
    hit = sum(1 for g in gold if any(is_hit(c, g) for c in retrieved))
    return hit / len(gold)


def mrr(retrieved: List[Dict], gold: List[Dict]) -> float:
    """Reciprocal rank (1-indexed) of the first chunk hitting any gold span."""
    for rank, chunk in enumerate(retrieved, start=1):
        if any(is_hit(chunk, g) for g in gold):
            return 1.0 / rank
    return 0.0


def _line_set(spans: List[Dict]) -> set:
    return {(s["file_path"], n) for s in spans for n in range(s["start_line"], s["end_line"] + 1)}


def coverage(retrieved: List[Dict], gold: List[Dict]) -> float:
    """Fraction of gold *lines* contained in the union of retrieved chunks.

    Stricter than recall: a chunk clipping one line of a 40-line function counts
    as a full hit for recall but scores 0.025 here.
    """
    gold_lines = _line_set(gold)
    if not gold_lines:
        raise ValueError("coverage() called with no gold spans")
    return len(gold_lines & _line_set(retrieved)) / len(gold_lines)


def paired_diff(before: Dict[str, float], after: Dict[str, float]) -> Dict:
    """Per-question comparison between two configurations.

    With 20 answerable questions one question is worth 5 recall points, so an
    aggregate delta of a few points is indistinguishable from noise. Paired
    counts say something true at that sample size -- and surface regressions
    that an improved aggregate would hide.
    """
    if set(before) != set(after):
        raise ValueError("paired_diff() requires both runs to cover the same questions")
    improved = sorted(q for q in before if after[q] > before[q])
    regressed = sorted(q for q in before if after[q] < before[q])
    unchanged = sorted(q for q in before if after[q] == before[q])
    return {
        "improved": len(improved),
        "regressed": len(regressed),
        "unchanged": len(unchanged),
        "improved_ids": improved,
        "regressed_ids": regressed,
        "unchanged_ids": unchanged,
    }
