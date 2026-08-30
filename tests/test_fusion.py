import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from api.fusion import reciprocal_rank_fusion


def d(i):
    return {"id": i, "file_path": f"{i}.py", "start_line": 1, "end_line": 10}


def ids(results):
    return [r["id"] for r in results]


def test_single_list_preserves_order():
    assert ids(reciprocal_rank_fusion([[d(1), d(2), d(3)]])) == [1, 2, 3]

def test_agreed_top_beats_split_top():
    """A chunk ranked first by both retrievers outranks one ranked first by only one."""
    dense   = [d(1), d(2)]
    lexical = [d(1), d(3)]
    assert ids(reciprocal_rank_fusion([dense, lexical]))[0] == 1

def test_deduplicates_by_id():
    dense   = [d(1), d(2)]
    lexical = [d(2), d(1)]
    out = reciprocal_rank_fusion([dense, lexical])
    assert sorted(ids(out)) == [1, 2]
    assert len(out) == 2

def test_chunk_in_both_lists_beats_chunk_in_one():
    dense   = [d(9), d(1)]
    lexical = [d(8), d(1)]
    # 1 is rank 2 in both; 9 and 8 are rank 1 in one list each.
    # With k=60: score(1) = 2/62 = 0.0323, score(9) = 1/61 = 0.0164
    assert ids(reciprocal_rank_fusion([dense, lexical]))[0] == 1

def test_k_is_configurable_and_changes_ranking():
    dense   = [d(9), d(1)]
    lexical = [d(8), d(1)]
    # At very small k the rank-1 advantage dominates the appears-twice advantage:
    # k=0 -> score(9)=1/1=1.0, score(1)=1/2+1/2=1.0 -> tie broken by input order
    assert ids(reciprocal_rank_fusion([dense, lexical], k=60))[0] == 1
    assert ids(reciprocal_rank_fusion([dense, lexical], k=0))[0] == 9

def test_empty_lists_are_ignored():
    assert ids(reciprocal_rank_fusion([[], [d(1)], []])) == [1]

def test_all_empty_returns_empty():
    assert reciprocal_rank_fusion([[], []]) == []

def test_attaches_fusion_score():
    out = reciprocal_rank_fusion([[d(1)]], k=60)
    assert out[0]["rrf_score"] == pytest.approx(1 / 61)

def test_does_not_mutate_input():
    original = d(1)
    reciprocal_rank_fusion([[original]])
    assert "rrf_score" not in original
