"""
Code generation utilities:

  extract_code_block()  — pull Python code out of an LLM response
  write_code_to_file()  — persist generated code to disk
  run_tests()           — run pytest and return a TestResult
"""
from __future__ import annotations

import os
import re
import subprocess

from pipeline.models import TestResult


def extract_code_block(text: str) -> str:
    """
    Extract a Python code block from an LLM response.

    Priority:
      1. ```python ... ```
      2. ``` ... ```
      3. Full text as-is (fallback)
    """
    m = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def write_code_to_file(code: str, filepath: str) -> str:
    """Write *code* to *filepath*, creating parent directories as needed."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"  📄 Code written → {filepath}  ({len(code)} chars)")
    return filepath


def run_tests(solution_path: str, test_path: str, timeout: int = 30) -> TestResult:
    """
    Run pytest for *test_path* (which imports *solution_path*).

    If *test_path* does not exist, fall back to a py_compile syntax check.
    Returns a TestResult with pass/fail/error counts and raw pytest output.
    """
    if not test_path or not os.path.exists(test_path):
        print(f"  ⚠️  Test file not found: {test_path!r}")
        print("     Running syntax check on solution...")
        return _syntax_check(solution_path, timeout)

    try:
        result = subprocess.run(
            [
                "python3", "-m", "pytest", test_path,
                "-v", "--tb=short", "--no-header",
                f"--rootdir={os.path.dirname(os.path.abspath(solution_path))}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONPATH": os.path.dirname(os.path.abspath(solution_path))},
        )
    except subprocess.TimeoutExpired:
        tr = TestResult(
            tests_error=1,
            output=f"Timeout ({timeout}s) running pytest",
            returncode=-1,
        )
        _print_result(tr)
        return tr

    output = result.stdout + result.stderr
    tr = _parse_pytest_output(output, result.returncode)
    _print_result(tr)
    return tr


# ── Internal helpers ──────────────────────────────────────────────────────────

def _syntax_check(solution_path: str, timeout: int) -> TestResult:
    try:
        result = subprocess.run(
            ["python3", "-m", "py_compile", solution_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            tr = TestResult(tests_passed=1, output="Syntax check passed", returncode=0)
        else:
            tr = TestResult(tests_failed=1, output=result.stderr, returncode=result.returncode)
    except subprocess.TimeoutExpired:
        tr = TestResult(tests_error=1, output="Timeout during syntax check", returncode=-1)
    _print_result(tr)
    return tr


def _parse_pytest_output(output: str, returncode: int) -> TestResult:
    """Parse the summary line pytest emits at the end of a run."""
    passed = failed = error = 0
    summary_line = ""
    for line in output.splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            summary_line = line

    p = re.search(r"(\d+) passed", summary_line)
    f = re.search(r"(\d+) failed", summary_line)
    e = re.search(r"(\d+) error", summary_line)

    if p:
        passed = int(p.group(1))
    if f:
        failed = int(f.group(1))
    if e:
        error = int(e.group(1))

    if passed == failed == error == 0 and returncode != 0:
        error = 1

    return TestResult(
        tests_passed=passed,
        tests_failed=failed,
        tests_error=error,
        output=output,
        returncode=returncode,
    )


def _print_result(tr: TestResult) -> None:
    print(f"\n  {'─'*50}")
    print(f"  {tr.summary()}")
    if tr.tests_failed > 0 or tr.tests_error > 0:
        tail = "\n".join(tr.output.splitlines()[-20:])
        print(f"\n  pytest output (tail):\n{tail}")
    print(f"  {'─'*50}")
