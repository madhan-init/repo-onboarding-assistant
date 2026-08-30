"""Run the golden set through one or more retrieval configs.

Rows 0-3 make no LLM call: recall, MRR and coverage are pure vector-and-SQL math
against gold line spans. That is what keeps the sweep cheap and lets anyone with
an embedding key reproduce the numbers.

    uv run python3 eval/run.py                      # every runnable ladder row
    uv run python3 eval/run.py --config 2-hybrid
    uv run python3 eval/run.py --golden tests/fixtures/smoke_golden.json
"""
import argparse
import json
import os
import importlib.util
import statistics
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.retrieval import search
from config.retrieval import LADDER, get as get_config
from eval.golden_set import answerable, load
from eval.metrics import (
    coverage, mrr, paired_diff, recall, select_by_line_budget, select_top_k,
)
from eval.runnable import missing_requirements

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "v1.json")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def indexed_labels(repo_id):
    from db.client import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_label, count(*) FROM chunks WHERE repo_id = %s GROUP BY chunk_label",
                (repo_id,),
            )
            return dict(cur.fetchall())


def available_modules():
    return {name: importlib.util.find_spec(name) is not None
            for name in ("api.rerank", "api.expand")}


def run_config(repo_id, questions, config):
    per_question, latencies = {}, []
    for item in questions:
        started = time.perf_counter()
        ranked = search(repo_id, item["question"], config)
        latencies.append((time.perf_counter() - started) * 1000)

        budgeted = select_by_line_budget(ranked, config.line_budget)
        topk = select_top_k(ranked, config.top_k)
        per_question[item["id"]] = {
            "recall_budget": recall(budgeted, item["gold"]),
            "recall_at_k": recall(topk, item["gold"]),
            "mrr": mrr(ranked, item["gold"]),
            "coverage": coverage(budgeted, item["gold"]),
            "chunks_in_budget": len(budgeted),
        }
    return {
        "config": config.name,
        "per_question": per_question,
        "aggregate": {
            metric: statistics.mean(v[metric] for v in per_question.values())
            for metric in ("recall_budget", "recall_at_k", "mrr", "coverage", "chunks_in_budget")
        },
        "latency_ms_p50": statistics.median(latencies) if latencies else 0.0,
    }


def print_table(runs):
    header = f"{'config':<14}{'recall@budget':>15}{'recall@5':>10}{'MRR':>8}{'coverage':>10}{'chunks':>8}{'p50 ms':>9}"
    print("\n" + header)
    print("-" * len(header))
    for run in runs:
        a = run["aggregate"]
        print(f"{run['config']:<14}{a['recall_budget']:>15.3f}{a['recall_at_k']:>10.3f}"
              f"{a['mrr']:>8.3f}{a['coverage']:>10.3f}{a['chunks_in_budget']:>8.1f}"
              f"{run['latency_ms_p50']:>9.0f}")

    if len(runs) < 2:
        return
    print("\npaired, vs the row above (n={}):".format(len(runs[0]["per_question"])))
    for previous, current in zip(runs, runs[1:]):
        before = {q: v["recall_budget"] for q, v in previous["per_question"].items()}
        after = {q: v["recall_budget"] for q, v in current["per_question"].items()}
        d = paired_diff(before, after)
        print(f"  {previous['config']:<12} -> {current['config']:<14}"
              f"improved {d['improved']:>2}   regressed {d['regressed']:>2}   unchanged {d['unchanged']:>2}"
              + (f"   (broke: {', '.join(d['regressed_ids'])})" if d["regressed_ids"] else ""))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default=GOLDEN)
    parser.add_argument("--config", action="append", help="config name; repeatable")
    parser.add_argument("--save", action="store_true", help="write results JSON")
    args = parser.parse_args()

    data = load(args.golden)
    questions = answerable(data["questions"])
    if not questions:
        sys.exit("No answerable questions yet. Add some: uv run python3 eval/author.py")
    repo_id = data["corpus"]["repo_id"]

    configs = [get_config(n) for n in args.config] if args.config else list(LADDER)

    counts = indexed_labels(repo_id)
    modules = available_modules()
    llm_ok = bool(os.environ.get("ANTHROPIC_WORKSPACE_ID"))

    runs, skipped = [], []
    for config in configs:
        reasons = missing_requirements(config, counts, modules, llm_ok)
        if reasons:
            skipped.append((config.name, reasons))
            print(f"  skip  {config.name}")
            for reason in reasons:
                print(f"          {reason}")
            continue
        print(f"  run   {config.name} ...")
        runs.append(run_config(repo_id, questions, config))

    if not runs:
        sys.exit("\nNothing runnable. Refusing to report a table with no measurements.")

    print_table(runs)

    if args.save and runs:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        path = os.path.join(RESULTS_DIR, "latest.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"corpus": data["corpus"], "n_questions": len(questions),
                       "runs": runs}, handle, indent=2)
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
