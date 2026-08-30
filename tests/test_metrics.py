"""Tests for eval/metrics.py.

These matter more than the rest of the suite: a bug here silently corrupts every
number in the README, and no other check would catch it.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from eval.metrics import (
    spans_overlap, is_hit, select_by_line_budget, select_top_k,
    recall, mrr, coverage, paired_diff, chunk_lines,
)


def c(path, start, end):
    return {"file_path": path, "start_line": start, "end_line": end}


# --- span overlap -----------------------------------------------------------

def test_overlap_identical():
    assert spans_overlap(10, 20, 10, 20)

def test_overlap_contained():
    assert spans_overlap(1, 100, 40, 50)
    assert spans_overlap(40, 50, 1, 100)

def test_overlap_partial():
    assert spans_overlap(10, 20, 20, 30)   # share exactly line 20
    assert spans_overlap(10, 20, 5, 10)    # share exactly line 10

def test_no_overlap_adjacent():
    assert not spans_overlap(10, 20, 21, 30)
    assert not spans_overlap(21, 30, 10, 20)

def test_no_overlap_disjoint():
    assert not spans_overlap(1, 5, 100, 200)


# --- hits require the same file --------------------------------------------

def test_hit_same_file_overlapping():
    assert is_hit(c("app.py", 1, 100), c("app.py", 40, 50))

def test_miss_different_file_same_lines():
    assert not is_hit(c("app.py", 1, 100), c("other.py", 40, 50))


# --- budget selection -------------------------------------------------------

def test_chunk_lines_is_inclusive():
    assert chunk_lines(c("a.py", 10, 10)) == 1
    assert chunk_lines(c("a.py", 1, 100)) == 100

def test_budget_stops_before_exceeding():
    chunks = [c("a.py", 1, 100), c("b.py", 1, 100), c("d.py", 1, 100)]
    assert len(select_by_line_budget(chunks, 250)) == 2

def test_budget_exact_fit_includes_chunk():
    chunks = [c("a.py", 1, 100), c("b.py", 1, 100)]
    assert len(select_by_line_budget(chunks, 200)) == 2

def test_budget_always_returns_at_least_one():
    """A single chunk larger than the whole budget must still be returned --
    otherwise an oversized chunk silently scores as retrieving nothing."""
    chunks = [c("a.py", 1, 500)]
    assert len(select_by_line_budget(chunks, 100)) == 1

def test_budget_gives_small_chunks_more_slots():
    """The whole point of a line budget: AST-sized chunks get more of them."""
    big = [c(f"{i}.py", 1, 100) for i in range(10)]
    small = [c(f"{i}.py", 1, 20) for i in range(10)]
    assert len(select_by_line_budget(big, 500)) == 5
    assert len(select_by_line_budget(small, 500)) == 10

def test_select_top_k():
    chunks = [c(f"{i}.py", 1, 10) for i in range(10)]
    assert len(select_top_k(chunks, 5)) == 5
    assert len(select_top_k(chunks, 50)) == 10


# --- recall -----------------------------------------------------------------

def test_recall_all_gold_hit():
    gold = [c("a.py", 10, 20), c("b.py", 5, 8)]
    retrieved = [c("a.py", 1, 100), c("b.py", 1, 50)]
    assert recall(retrieved, gold) == 1.0

def test_recall_partial():
    gold = [c("a.py", 10, 20), c("b.py", 5, 8)]
    retrieved = [c("a.py", 1, 100)]
    assert recall(retrieved, gold) == 0.5

def test_recall_none():
    gold = [c("a.py", 10, 20)]
    retrieved = [c("z.py", 1, 100)]
    assert recall(retrieved, gold) == 0.0

def test_recall_one_chunk_can_satisfy_two_gold_spans():
    gold = [c("a.py", 10, 20), c("a.py", 60, 70)]
    assert recall([c("a.py", 1, 100)], gold) == 1.0

def test_recall_empty_gold_raises():
    """Unanswerable questions have no gold spans and must never reach recall."""
    with pytest.raises(ValueError):
        recall([c("a.py", 1, 10)], [])


# --- MRR --------------------------------------------------------------------

def test_mrr_first_position():
    assert mrr([c("a.py", 1, 100)], [c("a.py", 10, 20)]) == 1.0

def test_mrr_third_position():
    retrieved = [c("x.py", 1, 10), c("y.py", 1, 10), c("a.py", 1, 100)]
    assert mrr(retrieved, [c("a.py", 10, 20)]) == pytest.approx(1 / 3)

def test_mrr_no_hit_is_zero():
    assert mrr([c("x.py", 1, 10)], [c("a.py", 10, 20)]) == 0.0


# --- coverage ---------------------------------------------------------------

def test_coverage_full():
    assert coverage([c("a.py", 1, 100)], [c("a.py", 10, 20)]) == 1.0

def test_coverage_half():
    # gold is lines 10-19 (10 lines); retrieved covers 10-14 (5 lines)
    assert coverage([c("a.py", 10, 14)], [c("a.py", 10, 19)]) == 0.5

def test_coverage_counts_union_not_double():
    retrieved = [c("a.py", 10, 14), c("a.py", 12, 19)]
    assert coverage(retrieved, [c("a.py", 10, 19)]) == 1.0


# --- paired diff ------------------------------------------------------------

def test_paired_diff_counts():
    before = {"q1": 0.0, "q2": 1.0, "q3": 0.5}
    after  = {"q1": 1.0, "q2": 0.0, "q3": 0.5}
    d = paired_diff(before, after)
    assert (d["improved"], d["regressed"], d["unchanged"]) == (1, 1, 1)

def test_paired_diff_lists_the_questions():
    before = {"q1": 0.0, "q2": 1.0}
    after  = {"q1": 1.0, "q2": 0.0}
    d = paired_diff(before, after)
    assert d["improved_ids"] == ["q1"]
    assert d["regressed_ids"] == ["q2"]

def test_paired_diff_requires_same_questions():
    with pytest.raises(ValueError):
        paired_diff({"q1": 1.0}, {"q2": 1.0})
