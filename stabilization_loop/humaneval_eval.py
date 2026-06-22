"""HumanEval completion extraction and functional checking."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap

from stabilization_loop.metrics import TestResult
from stabilization_loop.validation import extract_code_block, print_test_result

# human_eval.execution uses Unix signal.setitimer — unavailable on Windows.
_USE_HUMAN_EVAL_EXEC = sys.platform != "win32"


def _entry_point_name(prompt: str) -> str | None:
    match = re.search(r"^def\s+(\w+)", prompt, re.MULTILINE)
    return match.group(1) if match else None


def _ensure_indented_body(completion: str, indent: str = "    ") -> str:
    """HumanEval completions must be indented function bodies."""
    if not completion.strip():
        return completion

    lines = completion.splitlines()
    if not lines:
        return completion

    first = lines[0]
    if first.startswith(("def ", "class ", "@")):
        return completion

    if first.startswith(indent) or first.startswith("\t"):
        return completion if completion.endswith("\n") else completion + "\n"

    indented = "\n".join(indent + line if line.strip() else line for line in lines)
    return indented.rstrip() + "\n"


def _fix_body_indent(completion: str, base: str = "    ") -> str:
    """
    Fix HumanEval body when the first line lost leading whitespace
    but nested lines kept their absolute indentation.
    """
    lines = completion.splitlines()
    nonempty = [line for line in lines if line.strip()]
    if not nonempty:
        return completion

    indents = [len(line) - len(line.lstrip()) for line in nonempty]
    if indents[0] == 0 and any(i > 0 for i in indents):
        fixed: list[str] = []
        for line in lines:
            if not line.strip():
                fixed.append("")
                continue
            cur = len(line) - len(line.lstrip())
            if cur == 0:
                fixed.append(base + line.lstrip())
            else:
                fixed.append(line)
        return "\n".join(fixed).rstrip() + "\n"

    return _ensure_indented_body(completion, base)


def extract_completion(prompt: str, generated: str) -> str:
    """Extract HumanEval completion (text appended to the dataset prompt)."""
    code = extract_code_block(generated).rstrip("\n")
    entry = _entry_point_name(prompt)

    if entry:
        pattern = re.compile(
            rf"^def\s+{re.escape(entry)}\s*\([^)]*\)\s*(?:->\s*[^:]+)?\s*:",
            re.MULTILINE,
        )
        match = pattern.search(code)
        if match:
            body_start = code.find("\n", match.end())
            if body_start != -1:
                after_def = code[body_start + 1 :]
                doc_end = after_def.find('"""')
                if after_def.lstrip().startswith('"""'):
                    doc_end = after_def.find('"""', 3)
                    if doc_end != -1:
                        body = after_def[doc_end + 3 :].lstrip("\n")
                        return _fix_body_indent(body)
                body = after_def.lstrip("\n")
                return _fix_body_indent(body)

    if code.startswith(prompt.strip()):
        return _fix_body_indent(code[len(prompt.strip()) :].lstrip("\n"))

    prompt_lines = prompt.splitlines()
    code_lines = code.splitlines()
    if prompt_lines and code_lines:
        match_len = 0
        for pl, cl in zip(prompt_lines, code_lines):
            if pl.strip() == cl.strip():
                match_len += 1
            else:
                break
        if match_len > 0:
            remainder = code_lines[match_len:]
            if remainder:
                return _fix_body_indent("\n".join(remainder))

    if code and not code.startswith(("def ", "class ")):
        return _fix_body_indent(code)

    return _fix_body_indent(code)


def _fallback_check(problem: dict, completion: str, timeout: float) -> tuple[bool, str]:
    """Windows-compatible exec-based HumanEval check."""
    program = problem["prompt"] + completion
    test_code = problem["test"]
    entry_point = problem["entry_point"]

    script = textwrap.dedent(
        f"""
        import sys
        ns = {{}}
        try:
            exec({program!r}, ns)
            exec({test_code!r}, ns)
            ns["check"](ns[{entry_point!r}])
        except Exception as exc:
            print(f"failed: {{exc}}", file=sys.stderr)
            sys.exit(1)
        """
    ).strip()

    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"

    if proc.returncode == 0:
        return True, "passed"
    return False, (proc.stderr or proc.stdout or "failed").strip()[-2000:]


def run_humaneval_check(problem: dict, completion: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Run HumanEval functional check."""
    if not _USE_HUMAN_EVAL_EXEC:
        return _fallback_check(problem, completion, timeout)

    payload = {"problem": problem, "completion": completion, "timeout": timeout}
    runner = textwrap.dedent(
        """
        import json, sys
        from human_eval.execution import check_correctness

        data = json.loads(sys.stdin.read())
        result = check_correctness(
            data["problem"],
            data["completion"],
            timeout=data["timeout"],
        )
        print(json.dumps({"passed": result["passed"], "result": result.get("result", "")}))
        """
    ).strip()

    try:
        proc = subprocess.run(
            [sys.executable, "-c", runner],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout + 15,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"

    if proc.returncode != 0:
        return _fallback_check(problem, completion, timeout)

    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return _fallback_check(problem, completion, timeout)

    result_msg = str(data.get("result", ""))
    if "setitimer" in result_msg or not data.get("passed") and "failed" in result_msg:
        if "setitimer" in result_msg:
            return _fallback_check(problem, completion, timeout)

    return bool(data.get("passed")), result_msg


def test_humaneval_output(
    llm_text: str,
    problem: dict,
    solution_path: str,
) -> tuple[str, TestResult]:
    """Validate LLM output against HumanEval functional tests."""
    prompt = problem["prompt"]
    completion = extract_completion(prompt, llm_text)

    if not completion.strip():
        tr = TestResult(
            tests_error=1,
            output="No completion extracted from model output.",
            returncode=1,
            failure_type="NO_CODE_EXTRACTED",
            failure_signature="NO_CODE_EXTRACTED",
            digest="The model did not return a HumanEval completion.",
        )
        print_test_result(tr)
        return completion, tr

    full_program = prompt + completion
    try:
        compile(full_program, "<humaneval>", "exec")
    except SyntaxError as exc:
        digest = f"SyntaxError at line {exc.lineno}: {exc.msg}"
        tr = TestResult(
            tests_error=1,
            output=digest,
            returncode=1,
            failure_type="SYNTAX_ERROR",
            failure_signature=f"SYNTAX_ERROR:{exc.lineno}:{exc.msg}",
            digest=digest,
        )
        print_test_result(tr)
        return completion, tr

    from stabilization_loop.validation import write_code_to_file

    write_code_to_file(full_program, solution_path)
    passed, message = run_humaneval_check(problem, completion)

    if passed:
        tr = TestResult(
            tests_passed=1,
            output=message,
            returncode=0,
            failure_type="PASSED",
            failure_signature="PASSED",
        )
    else:
        tr = TestResult(
            tests_failed=1,
            output=message,
            returncode=1,
            failure_type="ASSERTION_FAILURE",
            failure_signature=f"HUMANEVAL:{message[:80]}",
            digest=f"HumanEval check failed: {message}",
        )

    print_test_result(tr)
    return completion, tr
