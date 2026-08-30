"""The golden set: 30 hand-written questions with gold answer locations.

Gold is stored as (file_path, start_line, end_line) *line spans*, never chunk ids.
Chunk boundaries are the thing the AST experiment changes, so chunk-id gold would
score the baseline and the AST arm against different answer keys.

Answerable questions carry gold spans and are scored on recall. Unanswerable ones
carry none and are scored on abstention -- refusing correctly means retrieving
nothing, which a recall metric would count as failure.
"""
import json
import os
import re
from typing import Dict, List

VERSION = "1.0.0"
EMPTY_SET: Dict = {"version": VERSION, "corpus": {}, "questions": []}

_ID = re.compile(r"^q(\d+)$")


def validate_question(item: Dict) -> None:
    qid = item.get("id", "<no id>")
    if not str(item.get("question", "")).strip():
        raise ValueError(f"{qid}: question text is empty")
    if "answerable" not in item:
        raise ValueError(f"{qid}: missing 'answerable'")

    gold = item.get("gold", [])
    if item["answerable"] and not gold:
        raise ValueError(
            f"{qid}: answerable question has no gold span -- it would score 0 "
            f"forever and be indistinguishable from a retrieval failure"
        )
    if not item["answerable"] and gold:
        raise ValueError(f"{qid}: unanswerable question must not carry gold spans")

    for span in gold:
        if not span.get("file_path"):
            raise ValueError(f"{qid}: gold span missing file_path")
        start, end = span.get("start_line"), span.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int):
            raise ValueError(f"{qid}: gold line numbers must be integers")
        if start < 1:
            raise ValueError(f"{qid}: gold start_line must be >= 1 (got {start})")
        if end < start:
            raise ValueError(f"{qid}: gold end_line {end} precedes start_line {start}")


def validate_set(data: Dict) -> None:
    seen = set()
    for item in data.get("questions", []):
        validate_question(item)
        if item["id"] in seen:
            raise ValueError(f"duplicate question id {item['id']!r}")
        seen.add(item["id"])


def next_id(questions: List[Dict]) -> str:
    highest = 0
    for item in questions:
        match = _ID.match(item.get("id", ""))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"q{highest + 1:02d}"


def answerable(questions: List[Dict]) -> List[Dict]:
    return [q for q in questions if q.get("answerable")]


def unanswerable(questions: List[Dict]) -> List[Dict]:
    return [q for q in questions if not q.get("answerable")]


def load(path: str) -> Dict:
    if not os.path.exists(path):
        return dict(EMPTY_SET, questions=[])
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    validate_set(data)
    return data


def save(path: str, data: Dict) -> None:
    """Validate before writing: a corrupt set must never reach disk."""
    validate_set(data)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
