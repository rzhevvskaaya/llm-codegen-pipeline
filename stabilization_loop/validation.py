"""Code extraction, validation, and pytest execution."""

from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
import sys

from stabilization_loop.metrics import TestResult
from stabilization_loop.reasoning import has_reasoning_artifacts, remove_reasoning_tags

FAILURE_TYPES = {
    "NO_CODE_EXTRACTED",
    "NON_CODE_OUTPUT",
    "SYNTAX_ERROR",
    "IMPORT_ERROR",
    "MISSING_SYMBOL",
    "WRONG_SIGNATURE",
    "ASSERTION_FAILURE",
    "RUNTIME_ERROR",
    "TIMEOUT",
    "TEST_FILE_ERROR",
    "TASK_TEST_MISMATCH",
    "TEST_COLLECTION_ERROR",
    "UNKNOWN_FAILURE",
    "PASSED",
}


def _looks_like_code_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if stripped.startswith(("def ", "class ", "@", "import ", "from ", "return ", "if ", "for ", "while ")):
        return True
    if stripped.endswith(":"):
        return True
    if stripped.startswith((" ", "\t")):
        return True
    return bool(re.match(r"^[A-Za-z_][\w.\[\],:()\"'=\-+*/%|&^~<>! ]+$", stripped))


def _extract_python_lines(text: str) -> str:
    """Keep contiguous Python block starting from first def/class/import."""
    lines = text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("def ", "class ", "@", "import ", "from ")):
            start = i
            break

    if start is None:
        return text.rstrip()

    code_lines: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if code_lines and stripped and not _looks_like_code_line(line):
            break
        code_lines.append(line)

    return "\n".join(code_lines).rstrip()


def extract_code_block(text: str) -> str:
    """Extract Python code from an LLM answer."""
    text = remove_reasoning_tags(text)

    match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).rstrip()

    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).rstrip()

    return _extract_python_lines(text)


def _top_level_symbols(code: str) -> set[str]:
    tree = ast.parse(code)
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
    return symbols


def validate_generated_code(code: str, expected_symbol: str | None = None) -> tuple[bool, TestResult, str]:
    """Layered pre-pytest validation: code-only, syntax, and expected symbol."""
    cleaned = extract_code_block(code)

    if not cleaned.strip():
        return False, TestResult(
            tests_error=1,
            output="No code was extracted from the LLM response.",
            failure_type="NO_CODE_EXTRACTED",
            failure_signature="NO_CODE_EXTRACTED",
            digest="The model did not return executable Python code.",
        ), cleaned

    if has_reasoning_artifacts(cleaned):
        return False, TestResult(
            tests_error=1,
            output=cleaned[:1000],
            failure_type="NON_CODE_OUTPUT",
            failure_signature="NON_CODE_OUTPUT_MARKDOWN_OR_THINK_TAGS",
            digest="The model returned markdown/reasoning tags instead of raw Python code.",
        ), cleaned

    try:
        symbols = _top_level_symbols(cleaned)
    except SyntaxError as exc:
        digest = f"SyntaxError at line {exc.lineno}: {exc.msg}"
        return False, TestResult(
            tests_error=1,
            output=digest,
            failure_type="SYNTAX_ERROR",
            failure_signature=f"SYNTAX_ERROR:{exc.lineno}:{exc.msg}",
            digest=digest,
        ), cleaned

    if expected_symbol and expected_symbol not in symbols:
        digest = (
            f"Expected top-level symbol '{expected_symbol}' was not found. "
            f"Found symbols: {sorted(symbols)}"
        )
        return False, TestResult(
            tests_error=1,
            output=digest,
            failure_type="MISSING_SYMBOL",
            failure_signature=f"MISSING_SYMBOL:{expected_symbol}",
            digest=digest,
        ), cleaned

    return True, TestResult(returncode=0, failure_type="PASSED", failure_signature="PASSED"), cleaned


def write_code_to_file(code: str, filepath: str) -> str:
    """Write validated Python code to a file."""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code.rstrip() + "\n")
    print(f"  Code written -> {filepath}  ({len(code)} chars)")
    return filepath


def _classify_pytest_failure(output: str, returncode: int) -> str:
    if returncode == 0:
        return "PASSED"
    lowered = output.lower()
    if "syntaxerror" in lowered:
        return "SYNTAX_ERROR"
    if "cannot import name" in lowered or "has no attribute" in lowered:
        return "MISSING_SYMBOL"
    if "modulenotfounderror" in lowered or "importerror" in lowered:
        return "IMPORT_ERROR"
    if "error collecting" in lowered or "collection error" in lowered:
        return "TEST_COLLECTION_ERROR"
    if "assert" in lowered or "assertionerror" in lowered or " failed" in lowered:
        return "ASSERTION_FAILURE"
    if "timeout" in lowered:
        return "TIMEOUT"
    if "traceback" in lowered or "exception" in lowered:
        return "RUNTIME_ERROR"
    return "UNKNOWN_FAILURE"


def _make_failure_signature(failure_type: str, output: str) -> str:
    """Create a compact deterministic signature for repeat detection."""
    useful_lines: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(
            key in stripped.lower()
            for key in [
                "error",
                "failed",
                "assert",
                "syntaxerror",
                "importerror",
                "modulenotfounderror",
                "cannot import",
                "expected",
                "got",
            ]
        ):
            useful_lines.append(stripped[:180])
    if not useful_lines:
        useful_lines = output.splitlines()[-8:]
    raw = failure_type + "\n" + "\n".join(useful_lines[-12:])
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _build_failure_digest(output: str, failure_type: str, max_lines: int = 50) -> str:
    """Convert noisy pytest output into compact repair feedback for AutoCrit.

    Включает:
    - строки с ключевыми словами ошибок
    - строки с префиксом 'E ' — это детали assert от pytest (actual vs expected)
    - последние строки вывода как fallback
    """
    lines = output.splitlines()
    selected: list[str] = []

    capture_keywords = [
        "FAILED",
        "ERROR",
        "AssertionError",
        "assert",
        "E   ",       # детали assert: actual value, diff
        "E  +",       # diff: что лишнее
        "E  -",       # diff: чего не хватает
        "E  ?",       # diff: указатель
        "SyntaxError",
        "ImportError",
        "ModuleNotFoundError",
        "cannot import name",
        "short test summary info",
        "At index",   # "At index 0 diff: ..."
        "Full diff",
    ]

    for line in lines:
        if any(key.lower() in line.lower() for key in capture_keywords):
            selected.append(line)

    # если ничего не нашли — берём хвост вывода
    if not selected:
        selected = lines[-max_lines:]

    selected = selected[-max_lines:]
    return f"Failure type: {failure_type}\n" + "\n".join(selected)


def _parse_pytest_output(output: str, returncode: int, test_path: str = "") -> TestResult:
    """Parse pytest summary into TestResult."""
    passed = failed = error = 0

    summary_line = ""
    for line in reversed(output.splitlines()):
        low = line.lower()
        if (" passed" in low or " failed" in low or " error" in low) and " in " in low:
            summary_line = line
            break

    match = re.search(r"(\d+)\s+passed", summary_line)
    if match:
        passed = int(match.group(1))
    match = re.search(r"(\d+)\s+failed", summary_line)
    if match:
        failed = int(match.group(1))
    match = re.search(r"(\d+)\s+errors?", summary_line)
    if match:
        error = int(match.group(1))

    if passed == failed == error == 0 and returncode != 0:
        error = 1

    failure_type = _classify_pytest_failure(output, returncode)
    if returncode == 0:
        failure_type = "PASSED"

    return TestResult(
        tests_passed=passed,
        tests_failed=failed,
        tests_error=error,
        output=output,
        returncode=returncode,
        failure_type=failure_type,
        failure_signature=_make_failure_signature(failure_type, output),
        digest=_build_failure_digest(output, failure_type),
        test_path=test_path,
    )


def print_test_result(tr: TestResult) -> None:
    print(f"\n  {'-' * 50}")
    print(f"  {tr.summary()}")
    if not tr.passed:
        digest = tr.digest or "\n".join(tr.output.splitlines()[-20:])
        print(f"\n  Failure digest:\n{digest}")
    print(f"  {'-' * 50}")


def run_tests(solution_path: str, test_path: str, timeout: int = 30) -> TestResult:
    """Run syntax check or pytest for the selected isolated test file."""
    python = sys.executable

    if not os.path.exists(solution_path):
        tr = TestResult(
            tests_error=1,
            output=f"Solution file does not exist: {solution_path}",
            failure_type="NO_CODE_EXTRACTED",
            failure_signature="MISSING_SOLUTION_FILE",
            digest=f"Solution file does not exist: {solution_path}",
            test_path=test_path,
        )
        print_test_result(tr)
        return tr

    if not test_path:
        try:
            result = subprocess.run(
                [python, "-m", "py_compile", solution_path],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                tr = TestResult(
                    tests_passed=1,
                    output="Syntax check passed",
                    returncode=0,
                    failure_type="PASSED",
                )
            else:
                tr = TestResult(
                    tests_error=1,
                    output=result.stderr,
                    returncode=result.returncode,
                    failure_type="SYNTAX_ERROR",
                    failure_signature=_make_failure_signature("SYNTAX_ERROR", result.stderr),
                    digest=_build_failure_digest(result.stderr, "SYNTAX_ERROR"),
                )
        except subprocess.TimeoutExpired:
            tr = TestResult(
                tests_error=1,
                output="Timeout during syntax check",
                returncode=-1,
                failure_type="TIMEOUT",
            )
        print_test_result(tr)
        return tr

    if not os.path.exists(test_path):
        tr = TestResult(
            tests_error=1,
            output=f"Selected test file does not exist: {test_path}",
            failure_type="TEST_FILE_ERROR",
            failure_signature=f"TEST_FILE_ERROR:{test_path}",
            digest=f"Selected test file does not exist: {test_path}",
            test_path=test_path,
        )
        print_test_result(tr)
        return tr

    try:
        solution_dir = os.path.dirname(solution_path) or "."
        test_dir = os.path.dirname(test_path) or "."
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join([solution_dir, test_dir, os.environ.get("PYTHONPATH", "")]),
        }
        result = subprocess.run(
            # -vv даёт полный diff при ASSERTION_FAILURE — модель видит actual vs expected
            [python, "-m", "pytest", test_path, "-vv", "--tb=short", "--no-header", f"--rootdir={test_dir}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        tr = TestResult(
            tests_error=1,
            output=f"Timeout ({timeout}s) while running pytest",
            returncode=-1,
            failure_type="TIMEOUT",
            failure_signature=f"TIMEOUT:{test_path}",
            digest=f"Timeout ({timeout}s) while running pytest for {test_path}",
            test_path=test_path,
        )
        print_test_result(tr)
        return tr

    output = result.stdout + result.stderr
    tr = _parse_pytest_output(output, result.returncode, test_path=test_path)
    print_test_result(tr)
    return tr


def prepare_and_test_llm_output(
    llm_text: str,
    solution_path: str,
    test_path: str,
    expected_symbol: str | None = None,
    humaneval_problem: dict | None = None,
) -> tuple[str, TestResult]:
    """Extract candidate code, validate it, write it, and run tests."""
    if humaneval_problem:
        from stabilization_loop.humaneval_eval import test_humaneval_output

        return test_humaneval_output(llm_text, humaneval_problem, solution_path)

    ok, validation_result, code = validate_generated_code(llm_text, expected_symbol=expected_symbol)
    if not ok:
        print("  Code validation failed before pytest")
        print_test_result(validation_result)
        return code, validation_result

    write_code_to_file(code, solution_path)
    tr = run_tests(solution_path, test_path)
    return code, tr
