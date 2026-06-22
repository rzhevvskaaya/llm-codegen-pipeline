#!/usr/bin/env python3
"""
Command-line interface for the pipeline.

Examples
--------
# Basic usage (syntax check only):
python -m pipeline.cli --task "Write a function two_sum(nums, target)..."

# With a pytest file:
python -m pipeline.cli \
    --task "Write a function two_sum(nums, target)..." \
    --test-path tests/test_tasks.py \
    --solution-path /tmp/solution.py

# With project context:
python -m pipeline.cli \
    --task "Add input validation to existing functions" \
    --project-dir ./my_project \
    --test-path tests/test_tasks.py
"""
import argparse
import sys

from pipeline.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM multi-agent code generation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--task", required=True, help="Coding task description")
    parser.add_argument("--solution-path", default="/tmp/solution.py", help="Where to write generated code")
    parser.add_argument("--test-path", default="", help="Path to pytest file (empty = syntax check)")
    parser.add_argument("--project-dir", default="", help="Codebase root for context agent")
    parser.add_argument("--quiet", action="store_true", help="Suppress streaming output")
    args = parser.parse_args()

    result = run_pipeline(
        task=args.task,
        solution_path=args.solution_path,
        test_path=args.test_path,
        project_dir=args.project_dir,
        verbose=not args.quiet,
    )

    print("\n--- FINAL CODE ---")
    print(result["final_code"])

    tr = result["test_result"]
    print(f"\ntests_passed = {tr.tests_passed}")
    print(f"tests_failed = {tr.tests_failed}")
    print(f"tests_error  = {tr.tests_error}")
    print(f"pass_rate    = {tr.pass_rate:.0%}")

    sys.exit(0 if tr.tests_failed == 0 and tr.tests_error == 0 else 1)


if __name__ == "__main__":
    main()
