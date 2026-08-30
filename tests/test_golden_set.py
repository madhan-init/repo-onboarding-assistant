import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from eval.golden_set import (
    validate_question, validate_set, next_id, answerable, unanswerable,
    load, save, EMPTY_SET,
)


def q(qid="q01", answerable=True, gold=None, text="how does routing work"):
    item = {"id": qid, "question": text, "answerable": answerable}
    item["gold"] = gold if gold is not None else (
        [{"file_path": "src/flask/app.py", "start_line": 10, "end_line": 40}] if answerable else []
    )
    return item


# --- per-question validation -----------------------------------------------

def test_valid_answerable_question():
    validate_question(q())

def test_valid_unanswerable_question():
    validate_question(q(answerable=False))

def test_answerable_requires_gold():
    """An answerable question with no gold span would score 0 forever and look
    identical to a retrieval failure."""
    with pytest.raises(ValueError, match="gold"):
        validate_question(q(gold=[]))

def test_unanswerable_must_not_have_gold():
    with pytest.raises(ValueError, match="gold"):
        validate_question(q(answerable=False, gold=[{"file_path": "a.py", "start_line": 1, "end_line": 2}]))

def test_rejects_empty_question_text():
    with pytest.raises(ValueError, match="question"):
        validate_question(q(text="   "))

def test_rejects_inverted_line_range():
    with pytest.raises(ValueError, match="line"):
        validate_question(q(gold=[{"file_path": "a.py", "start_line": 40, "end_line": 10}]))

def test_rejects_zero_or_negative_start_line():
    with pytest.raises(ValueError, match="line"):
        validate_question(q(gold=[{"file_path": "a.py", "start_line": 0, "end_line": 10}]))

def test_rejects_missing_file_path():
    with pytest.raises(ValueError, match="file_path"):
        validate_question(q(gold=[{"start_line": 1, "end_line": 10}]))


# --- set-level validation ---------------------------------------------------

def test_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="duplicate"):
        validate_set({"version": "1.0.0", "questions": [q("q01"), q("q01")]})

def test_validates_every_question():
    with pytest.raises(ValueError):
        validate_set({"version": "1.0.0", "questions": [q("q01"), q("q02", gold=[])]})

def test_empty_set_is_valid():
    validate_set(EMPTY_SET)


# --- helpers ----------------------------------------------------------------

def test_next_id_starts_at_one():
    assert next_id([]) == "q01"

def test_next_id_increments_past_highest():
    assert next_id([q("q01"), q("q09")]) == "q10"

def test_next_id_ignores_gaps():
    assert next_id([q("q01"), q("q05")]) == "q06"

def test_partitions_by_answerable():
    items = [q("q01"), q("q02", answerable=False), q("q03")]
    assert [i["id"] for i in answerable(items)] == ["q01", "q03"]
    assert [i["id"] for i in unanswerable(items)] == ["q02"]


# --- round trip -------------------------------------------------------------

def test_save_then_load_round_trips():
    data = {"version": "1.0.0", "corpus": {"ref": "3.1.3"}, "questions": [q()]}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "v1.json")
        save(path, data)
        assert load(path) == data

def test_save_validates_before_writing():
    """A corrupt set must never reach disk and silently poison later runs."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "v1.json")
        with pytest.raises(ValueError):
            save(path, {"version": "1.0.0", "questions": [q(gold=[])]})
        assert not os.path.exists(path)
