"""HumanEval benchmark integration for the stabilization pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from stabilization_loop.humaneval_eval import extract_completion, run_humaneval_check

HUMANEVAL_PROMPT_SUFFIX = (
    "\n\nComplete the function stub above. "
    "Return ONLY the indented function body (4 spaces). "
    "Do NOT repeat imports, def line, or docstring. Raw Python only."
)


def load_humaneval_problems(limit: int | None = None, offset: int = 0) -> dict[str, dict]:
    """Load HumanEval problems from the official human-eval package."""
    try:
        from human_eval.data import read_problems
    except ImportError as exc:
        raise ImportError(
            "HumanEval requires the human-eval package.\n"
            "Install: pip install human-eval\n"
            "See: https://github.com/openai/human-eval"
        ) from exc

    all_problems = read_problems()
    task_ids = sorted(all_problems.keys())
    if offset:
        task_ids = task_ids[offset:]
    if limit is not None:
        task_ids = task_ids[:limit]
    return {task_id: all_problems[task_id] for task_id in task_ids}


def problem_to_task_spec(task_id: str, problem: dict) -> dict:
    """Convert a HumanEval problem to pipeline task_spec."""
    return {
        "task_id": task_id,
        "name": problem["entry_point"],
        "expected_symbol": problem["entry_point"],
        "prompt": problem["prompt"].rstrip() + HUMANEVAL_PROMPT_SUFFIX,
        "test_path": "",
        "humaneval_problem": problem,
        "benchmark": "humaneval",
    }


def write_samples_jsonl(rows: list[dict], path: Path) -> None:
    """Write HumanEval samples.jsonl for official evaluate_functional_correctness."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_humaneval_benchmark(
    run_pipeline_fn,
    output_dir: Path,
    limit: int | None = 10,
    offset: int = 0,
) -> list[dict]:
    """Run pipeline on HumanEval problems and collect pass@1 results."""
    problems = load_humaneval_problems(limit=limit, offset=offset)
    solution_path = output_dir / "solution.py"
    samples: list[dict] = []
    report: list[dict] = []

    print(f"\nHumanEval: {len(problems)} problems (offset={offset}, limit={limit})")
    print("Warning: HumanEval executes untrusted model code. Use only in a sandbox.\n")

    for i, (task_id, problem) in enumerate(problems.items(), 1):
        spec = problem_to_task_spec(task_id, problem)
        print(f"\n{'#' * 60}\n# HumanEval [{i}/{len(problems)}] {task_id}: {problem['entry_point']}\n{'#' * 60}")

        result = run_pipeline_fn(
            task_spec=spec,
            solution_path=str(solution_path),
            use_context=False,
        )

        completion = extract_completion(problem["prompt"], result["final_code"])
        samples.append({"task_id": task_id, "completion": completion})

        report.append(
            {
                "task_id": task_id,
                "name": problem["entry_point"],
                "success": result["success"],
                "failure_type": result["failure_type"],
                "agents_used": len(result["results"]),
                "stab_cycles": result["metrics"].stab_cycles,
                "escalated": result["metrics"].escalated,
                "total_tokens": result["total_tokens"],
                "elapsed_sec": result["elapsed_sec"],
            }
        )

        if result["success"]:
            archive = output_dir / "humaneval" / f"{task_id.replace('/', '_')}.py"
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text(problem["prompt"] + completion, encoding="utf-8")

    samples_path = output_dir / "humaneval_samples.jsonl"
    write_samples_jsonl(samples, samples_path)
    print(f"\nSamples saved to {samples_path}")

    passed_n = sum(1 for r in report if r["success"])
    total = len(report)
    pass_at_1 = passed_n / total if total else 0.0

    print("\nHUMANEVAL REPORT")
    print(f"  pass@1 : {passed_n}/{total} ({pass_at_1:.1%})")
    header = f"{'Task ID':<16} {'Function':<28} {'OK':<6} {'Agents':>7} {'Stab':>5} {'Oracle':>7}"
    print(header)
    print("-" * len(header))
    for row in report:
        oracle = "yes" if row["escalated"] else "no"
        print(
            f"{row['task_id']:<16} {row['name']:<28} {str(row['success']):<6} "
            f"{row['agents_used']:>7} {row['stab_cycles']:>5} {oracle:>7}"
        )

    report_path = output_dir / "humaneval_report.json"
    summary = {
        "benchmark": "HumanEval",
        "pass_at_1": pass_at_1,
        "passed": passed_n,
        "total": total,
        "offset": offset,
        "limit": limit,
        "tasks": report,
    }
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport saved to {report_path}")

    return report
