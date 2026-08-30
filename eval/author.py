"""Interactive authoring for the golden set.

You write every question; this only stops you recording one that cannot be scored.
A gold span pointing at a file that isn't indexed, or at lines past the end of the
file, scores zero forever and is indistinguishable from a retrieval failure -- so
every span is checked against the live index before it is written.

    uv run python3 eval/author.py                 # add questions
    uv run python3 eval/author.py --list          # show the set
    uv run python3 eval/author.py --check         # re-validate every span
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.client import get_connection
from eval.golden_set import (
    EMPTY_SET, answerable, load, next_id, save, unanswerable, validate_question,
)

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "v1.json")


def corpus_files(repo_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT file_path, length(content) - length(replace(content, chr(10), '')) + 1 "
                "FROM files WHERE repo_id = %s ORDER BY file_path",
                (repo_id,),
            )
            return dict(cur.fetchall())


def chunks_covering(repo_id, file_path, start, end):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_label, count(*) FROM chunks
                WHERE repo_id = %s AND file_path = %s
                  AND start_line <= %s AND end_line >= %s
                GROUP BY chunk_label
                """,
                (repo_id, file_path, end, start),
            )
            return dict(cur.fetchall())


def pick_corpus(data):
    if data.get("corpus", {}).get("repo_id"):
        return data["corpus"]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT r.id, r.url, count(f.file_path) FROM repos r "
                "JOIN files f ON f.repo_id = r.id GROUP BY r.id, r.url ORDER BY 3 DESC"
            )
            rows = cur.fetchall()
    if not rows:
        sys.exit("No repo has stored files yet. Ingest one first (see SPEC.md stage D).")
    print("\nCorpora with stored files:")
    for i, (rid, url, n) in enumerate(rows, 1):
        print(f"  {i}. {url}  ({n} files)")
    choice = input(f"corpus [1-{len(rows)}]: ").strip() or "1"
    rid, url, _ = rows[int(choice) - 1]
    return {"repo_id": str(rid), "url": url}


def validate_span(repo_id, files, file_path, start, end):
    """Returns a list of problems; empty means the span is scoreable."""
    problems = []
    if file_path not in files:
        near = [f for f in files if os.path.basename(f) == os.path.basename(file_path)]
        hint = f" Did you mean: {near[0]}?" if near else ""
        problems.append(f"{file_path!r} is not in the indexed corpus.{hint}")
        return problems
    total = files[file_path]
    if end > total:
        problems.append(f"{file_path} has {total} lines; span ends at {end}.")
    covering = chunks_covering(repo_id, file_path, start, end)
    if not covering:
        problems.append(
            f"no chunk overlaps {file_path}:{start}-{end} under any label "
            f"(this span can never be retrieved)"
        )
    return problems


def add_loop(data, files):
    repo_id = data["corpus"]["repo_id"]
    print("\nBlank question to finish.\n")
    while True:
        counts = f"[{len(answerable(data['questions']))} answerable / " \
                 f"{len(unanswerable(data['questions']))} unanswerable]"
        text = input(f"{counts} question: ").strip()
        if not text:
            return
        kind = input("  answerable? [Y/n]: ").strip().lower()
        is_answerable = kind not in ("n", "no")

        gold = []
        if is_answerable:
            print("  gold spans -- blank path to finish")
            while True:
                path = input("    file: ").strip()
                if not path:
                    break
                try:
                    lines = input("    lines (e.g. 120-165): ").strip()
                    start, _, end = lines.partition("-")
                    start, end = int(start), int(end or start)
                except ValueError:
                    print("    ! could not parse a line range")
                    continue
                problems = validate_span(repo_id, files, path, start, end)
                if problems:
                    for p in problems:
                        print(f"    ! {p}")
                    print("    not recorded")
                    continue
                covering = chunks_covering(repo_id, path, start, end)
                gold.append({"file_path": path, "start_line": start, "end_line": end})
                print(f"    ok ({', '.join(f'{v} {k}' for k, v in covering.items())})")
            if not gold:
                print("  ! answerable question needs at least one gold span; discarded\n")
                continue

        item = {"id": next_id(data["questions"]), "question": text,
                "answerable": is_answerable, "gold": gold}
        try:
            validate_question(item)
        except ValueError as exc:
            print(f"  ! {exc}\n")
            continue
        data["questions"].append(item)
        save(GOLDEN, data)
        print(f"  saved {item['id']}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    data = load(GOLDEN) if os.path.exists(GOLDEN) else dict(EMPTY_SET, questions=[])

    if args.list:
        for item in data["questions"]:
            mark = "A" if item["answerable"] else "U"
            spans = ", ".join(f"{g['file_path']}:{g['start_line']}-{g['end_line']}"
                              for g in item["gold"]) or "-"
            print(f"  [{mark}] {item['id']}  {item['question']}\n         {spans}")
        print(f"\n{len(answerable(data['questions']))} answerable / "
              f"{len(unanswerable(data['questions']))} unanswerable")
        return

    data["corpus"] = pick_corpus(data)
    files = corpus_files(data["corpus"]["repo_id"])

    if args.check:
        bad = 0
        for item in data["questions"]:
            for span in item["gold"]:
                problems = validate_span(data["corpus"]["repo_id"], files,
                                         span["file_path"], span["start_line"], span["end_line"])
                for p in problems:
                    bad += 1
                    print(f"  ! {item['id']}: {p}")
        print(f"\n{bad} problem(s) across {len(data['questions'])} questions")
        sys.exit(1 if bad else 0)

    save(GOLDEN, data)
    print(f"corpus: {data['corpus']['url']}  ({len(files)} files indexed)")
    add_loop(data, files)


if __name__ == "__main__":
    main()
