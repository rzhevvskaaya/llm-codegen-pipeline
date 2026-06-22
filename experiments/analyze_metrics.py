"""Analyze saved benchmark reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def analyze_report(report_path: Path) -> None:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    if not data:
        print("Empty report.")
        return

    total = len(data)
    passed = sum(1 for row in data if row.get("success"))
    total_tokens = sum(row.get("total_tokens", 0) for row in data)
    total_stab = sum(row.get("stab_cycles", 0) for row in data)
    escalated = sum(1 for row in data if row.get("escalated"))

    print(f"Tasks total     : {total}")
    print(f"Tasks passed    : {passed} ({passed / total:.0%})")
    print(f"Total tokens    : {total_tokens}")
    print(f"Stab cycles sum : {total_stab}")
    print(f"Oracle escalated: {escalated}")

    print("\nPer-task breakdown:")
    for row in data:
        status = "OK" if row.get("success") else "FAIL"
        print(
            f"  [{status}] task {row.get('task_id')} ({row.get('name')}): "
            f"agents={row.get('agents_used')}, stab={row.get('stab_cycles')}, "
            f"tokens={row.get('total_tokens')}, time={row.get('elapsed_sec')}s"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze benchmark JSON report")
    parser.add_argument("report", type=str, help="Path to benchmark_report.json")
    args = parser.parse_args()

    path = Path(args.report)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    analyze_report(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
