#!/usr/bin/env python3
"""Entry point for running the stabilization pipeline on benchmark tasks."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from stabilization_loop.config import LLM_BASE_URL, MODEL  # noqa: E402
from stabilization_loop.pipeline import run_pipeline  # noqa: E402
from tasks.registry import TASK_REGISTRY  # noqa: E402


def print_result(output: dict) -> None:
    """Print final pipeline result summary."""
    tr = output["test_result"]
    print("\nFINAL CODE:")
    print(output["final_code"])
    print("\n" + "=" * 60)
    print(f"success      = {output['success']}")
    print(f"failure_type = {output['failure_type']}")
    print(f"tests_passed = {tr.tests_passed}")
    print(f"tests_failed = {tr.tests_failed}")
    print(f"tests_error  = {tr.tests_error}")
    print(f"pass_rate    = {tr.pass_rate:.0%}")
    if not output["success"]:
        print("\nFailure digest:")
        print(output["failure_digest"])
    print("=" * 60)

    print("\nAGENT TRACE")
    print("-" * 54)
    for i, result in enumerate(output["results"], 1):
        print(f" {i}. {result.agent}")
        print(f"    tokens: {result.tokens}  |  time: {result.elapsed:.1f}s")
        candidate = result.metadata.get("candidate_code", result.text)
        preview = candidate[:160].replace("\n", " ")
        print(f"    -> {preview}...")
        print()


def run_benchmark(output_dir: Path) -> list[dict]:
    """Run all tasks and return benchmark report."""
    report: list[dict] = []
    # Tests always import `from solution import ...` — must write to solution.py.
    solution_path = output_dir / "solution.py"

    for task_id, spec in TASK_REGISTRY.items():
        print(f"\n{'#' * 60}\n# TASK {task_id}: {spec['name']}\n{'#' * 60}")
        result = run_pipeline(
            task_spec=spec,
            solution_path=str(solution_path),
            use_context=False,
        )
        if result["success"] and solution_path.exists():
            shutil.copy2(solution_path, output_dir / f"solution_task_{task_id}.py")

        report.append(
            {
                "task_id": task_id,
                "name": spec["name"],
                "success": result["success"],
                "failure_type": result["failure_type"],
                "agents_used": len(result["results"]),
                "stab_cycles": result["metrics"].stab_cycles,
                "escalated": result["metrics"].escalated,
                "total_tokens": result["total_tokens"],
                "elapsed_sec": result["elapsed_sec"],
            }
        )

    print("\nBENCHMARK REPORT")
    header = f"{'ID':<4} {'Task':<30} {'Success':<8} {'Failure':<22} {'Agents':>7} {'Stab':>5} {'Oracle':>7}"
    print(header)
    print("-" * len(header))
    for row in report:
        oracle = "yes" if row["escalated"] else "no"
        print(
            f"{row['task_id']:<4} {row['name']:<30} {str(row['success']):<8} "
            f"{row['failure_type']:<22} {row['agents_used']:>7} {row['stab_cycles']:>5} {oracle:>7}"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Loop-engineered multi-agent code generation and stabilization pipeline",
    )
    parser.add_argument(
        "--task",
        type=int,
        default=1,
        choices=sorted(TASK_REGISTRY.keys()),
        help="Task ID from benchmark registry (1-4)",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run all custom benchmark tasks (1-4) and print summary report",
    )
    parser.add_argument(
        "--humaneval",
        action="store_true",
        help="Run HumanEval benchmark (requires: pip install human-eval)",
    )
    parser.add_argument(
        "--humaneval-limit",
        type=int,
        default=10,
        help="Number of HumanEval problems to run (default: 10). Use 164 for full benchmark.",
    )
    parser.add_argument(
        "--humaneval-offset",
        type=int,
        default=0,
        help="Skip first N HumanEval problems (default: 0)",
    )
    parser.add_argument(
        "--use-context",
        action="store_true",
        help="Enable Context Agent for codebase analysis",
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=str(ROOT),
        help="Project directory for Context Agent indexing",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(ROOT / "output"),
        help="Directory for generated solution files",
    )
    parser.add_argument(
        "--save-report",
        type=str,
        default="",
        help="Save benchmark report to JSON file",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Configuration")
    print(f"   Model     : {MODEL}")
    print(f"   Base URL  : {LLM_BASE_URL}")

    if args.humaneval:
        from benchmarks.humaneval import run_humaneval_benchmark

        limit = None if args.humaneval_limit == 0 else args.humaneval_limit
        report = run_humaneval_benchmark(
            run_pipeline,
            output_dir,
            limit=limit,
            offset=args.humaneval_offset,
        )
        if args.save_report:
            Path(args.save_report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\nReport saved to {args.save_report}")
        return 0 if all(r["success"] for r in report) else 1

    if args.benchmark:
        report = run_benchmark(output_dir)
        if args.save_report:
            Path(args.save_report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\nReport saved to {args.save_report}")
        return 0 if all(r["success"] for r in report) else 1

    task_spec = TASK_REGISTRY[args.task]
    solution_path = output_dir / "solution.py"

    output = run_pipeline(
        task_spec=task_spec,
        solution_path=str(solution_path),
        use_context=args.use_context,
        project_dir=args.project_dir,
    )
    print_result(output)
    return 0 if output["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
