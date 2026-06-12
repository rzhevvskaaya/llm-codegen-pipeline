"""
All pipeline agents:

  supervisor_profile()   — profiles the task, returns ES metrics (strict JSON)
  context_agent()        — scans a codebase and builds a context snapshot
  base_model_reason()    — first-pass code generation
  stabilize()            — AutoCrit or Attenuation correction loop
  oracle_agent()         — final escalation after repeated failures
"""
from __future__ import annotations

import json
import os
import re

from pipeline.code_tools import extract_code_block, run_tests, write_code_to_file
from pipeline.config import settings
from pipeline.llm import _clean_llm_json, call_model
from pipeline.models import AgentResult, PipelineMetrics, TestResult


# ── Supervisor ────────────────────────────────────────────────────────────────

SUPERVISOR_SYSTEM = """
You are the Supervisor Agent (escalation controller) in a multi-agent system.

Your job: analyse the incoming task and return a JSON object with these fields:
  profile      — short task description (1-2 sentences)
  complexity   — task complexity [0..1]
  entropy_est  — expected reasoning diversity [0..1], higher = better
  wmax_est     — expected Wmax (dominant-path weight) [0..1]
  risk_loops   — CoT loop risk [0..1]
  es_score     — Escalation Score [0..1]
  token_budget — expected token count for the task (integer)

CRITICAL:
- Return ONLY valid JSON. No explanations, no markdown fences, no reasoning text.
- First character must be '{', last must be '}'.
- Any other format is an error that will stop the pipeline.
"""


class SupervisorJSONError(Exception):
    """Raised when the Supervisor returns something that is not valid JSON."""


def supervisor_profile(task: str, metrics: PipelineMetrics) -> dict:
    """
    Profile the task with the Supervisor Agent.

    Raises SupervisorJSONError on malformed output — never falls back to defaults.
    """
    result = call_model(
        system=SUPERVISOR_SYSTEM,
        messages=[{"role": "user", "content": task}],
        max_tokens=512,
        agent_name="Supervisor Agent",
    )

    cleaned = _clean_llm_json(result.text)

    if not cleaned:
        raise SupervisorJSONError(
            f"Supervisor returned an empty response after cleaning.\n"
            f"Raw response (first 300 chars):\n{result.text[:300]}"
        )

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise SupervisorJSONError(
            f"Supervisor returned invalid JSON.\n"
            f"Parse error: {exc}\n"
            f"Cleaned text (first 300 chars):\n{cleaned[:300]}"
        ) from exc

    required = {"entropy_est", "wmax_est", "es_score", "token_budget"}
    missing = required - data.keys()
    if missing:
        raise SupervisorJSONError(
            f"Supervisor JSON missing required fields: {missing}\n"
            f"Got fields: {list(data.keys())}"
        )

    metrics.entropy = float(data["entropy_est"])
    metrics.wmax = float(data["wmax_est"])
    metrics.es_score = float(data["es_score"])

    print(metrics.summary())
    return data


# ── Context Agent ─────────────────────────────────────────────────────────────

CONTEXT_AGENT_SYSTEM = """
You are the Context Agent in a multi-agent system.
You receive a snapshot of a project's codebase and a user task.

Your job:
  1. Identify the main modules and their purpose.
  2. Extract key classes, functions, dependencies.
  3. Note which files and entities are relevant to the task.
  4. Build a concise context string (context_for_codegen) to pass to the Base Model.

Return ONLY valid JSON without explanations or markdown:
{
  "architecture_summary": "...",
  "relevant_files": ["file1.py", ...],
  "key_entities": ["ClassName", "function_name", ...],
  "context_for_codegen": "... ready-to-use context text for Base Model ..."
}
"""


def _build_context_snapshot(project_dir: str) -> str:
    """Walk *project_dir* and collect file contents up to the configured limits."""
    snapshot_parts: list[str] = []
    total_chars = files_found = files_skipped = 0

    if not os.path.isdir(project_dir):
        print(f"   Directory not found: {project_dir}")
        return ""

    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [
            d for d in dirs
            if d not in {"__pycache__", ".git", ".ipynb_checkpoints", "node_modules", ".venv", "venv", "env"}
        ]
        for fname in sorted(files):
            if not fname.endswith(settings.context_extensions):
                continue
            if total_chars >= settings.context_max_total_chars:
                files_skipped += 1
                continue

            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, project_dir)
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read(settings.context_max_chars_per_file)
            except Exception as exc:
                snapshot_parts.append(f"### FILE: {rel}\n[read error: {exc}]\n")
                continue

            chunk = f"### FILE: {rel}\n{content}\n"
            snapshot_parts.append(chunk)
            total_chars += len(chunk)
            files_found += 1

    print(f"   Files indexed : {files_found}")
    if files_skipped:
        print(f"   Files skipped (limit): {files_skipped}")
    print(f"   Snapshot chars: {total_chars:,}")
    return "\n".join(snapshot_parts)


def context_agent(task: str, project_dir: str) -> dict:
    """Scan *project_dir* and return a structured context dict."""
    print("\n  Scanning project...")
    snapshot = _build_context_snapshot(project_dir)

    if not snapshot:
        print("    Empty snapshot — continuing without context")
        return {"context_for_codegen": ""}

    prompt = f"User task:\n{task}\n\nProject codebase:\n{snapshot}"

    result = call_model(
        system=CONTEXT_AGENT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        agent_name="Context Agent",
    )

    try:
        data = json.loads(_clean_llm_json(result.text))
    except json.JSONDecodeError:
        print("     JSON parse failed — passing raw snapshot")
        data = {"context_for_codegen": snapshot[:4000]}

    print(f"   Relevant files : {len(data.get('relevant_files', []))}")
    print(f"   Key entities   : {len(data.get('key_entities', []))}")
    return data


# ── Base Model ────────────────────────────────────────────────────────────────

BASE_SYSTEM = """
You are the base language model in a multi-agent code generation system.

REQUIRED RESPONSE FORMAT:
1. One or two sentences describing your approach.
2. The implementation inside a single code block:
```python
# your code here
```
No text after the closing triple backticks.
"""


def _estimate_entropy(text: str) -> float:
    words = text.lower().split()
    if len(words) < 4:
        return 0.5
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    return round(min(len(set(bigrams)) / len(bigrams), 1.0), 3)


def _estimate_wmax(text: str) -> float:
    words = [w for w in text.lower().split() if len(w) > 3]
    if not words:
        return 0.0
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return round(max(freq.values()) / len(words), 3)


def base_model_reason(
    task: str,
    metrics: PipelineMetrics,
    token_budget: int = 900,
    solution_path: str = "/tmp/solution.py",
    test_path: str = "",
) -> AgentResult:
    """First-pass code generation → write → test → update ES score."""
    result = call_model(
        system=BASE_SYSTEM,
        messages=[{"role": "user", "content": task}],
        max_tokens=token_budget,
        agent_name="Base Model",
    )

    metrics.entropy = _estimate_entropy(result.text)
    metrics.wmax = _estimate_wmax(result.text)
    metrics.token_ratio = result.metadata["output_tokens"] / max(token_budget * 0.5, 1)

    code = extract_code_block(result.text)
    write_code_to_file(code, solution_path)

    tr = run_tests(solution_path, test_path)
    metrics.register_test_result(tr)

    print(metrics.summary())
    return result


# ── Stabilisation (AutoCrit / Attenuation) ────────────────────────────────────

AUTOCRIT_SYSTEM = """
You are the AutoCrit Agent (self-critique and iterative error correction).

You receive the task, the previous code, and the output of the failed tests.
Algorithm:
  1. CRITIQUE: identify the specific causes of test failures.
  2. FIX: correct exactly the lines that cause errors.
  3. Return the fixed code in a block:
```python
# fixed code
```
If tests pass — write "CRITIQUE: No errors found." and repeat the code unchanged.
"""

ATTENUATION_SYSTEM = """
You are the Attenuation Agent (adaptive diversification).

The code shows signs of "dogmatism" (one approach dominates).
Your job:
  1. Identify the dominant approach that may be causing failures.
  2. Propose 2-3 alternative implementations.
  3. Synthesise the best variant and return it in a block:
```python
# optimal implementation
```
"""


def stabilize(
    task: str,
    previous_reasoning: str,
    metrics: PipelineMetrics,
    cycle: int,
    solution_path: str = "/tmp/solution.py",
    test_path: str = "",
) -> AgentResult:
    """
    Stabilisation block: fix code based on test results.
    Uses Attenuation when Wmax exceeds threshold, AutoCrit otherwise.
    """
    metrics.stab_cycles += 1

    test_context = ""
    if metrics.test_result.total > 0:
        test_context = (
            f"\n\nTEST RESULTS (cycle {cycle - 1}):\n"
            f"{metrics.test_result.summary()}\n"
            f"pytest output (last 30 lines):\n"
            + "\n".join(metrics.test_result.output.splitlines()[-30:])
        )

    if metrics.wmax >= settings.wmax_threshold:
        print(f"\n  🔄 Wmax={metrics.wmax:.2f} > {settings.wmax_threshold} → Attenuation (cycle {cycle})")
        system = ATTENUATION_SYSTEM
        agent_name = f"Attenuation Agent (cycle {cycle})"
    else:
        print(f"\n  🔧 ES={metrics.es_score:.2f} → AutoCrit (cycle {cycle})")
        system = AUTOCRIT_SYSTEM
        agent_name = f"AutoCrit Agent (cycle {cycle})"

    user_msg = (
        f"TASK:\n{task}\n\n"
        f"PREVIOUS CODE:\n{previous_reasoning}"
        f"{test_context}"
    )

    result = call_model(
        system=system,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=1024,
        agent_name=agent_name,
    )

    code = extract_code_block(result.text)
    write_code_to_file(code, solution_path)
    tr = run_tests(solution_path, test_path)
    metrics.register_test_result(tr)

    metrics.entropy = min(1.0, _estimate_entropy(result.text) + 0.1)
    metrics.wmax = max(0.0, _estimate_wmax(result.text) - 0.1)
    metrics.stabilized = True

    print(metrics.summary())
    return result


# ── Oracle (final escalation) ─────────────────────────────────────────────────

ORACLE_SYSTEM = """
You are the Oracle Agent, the most powerful agent in the multi-agent system.
You are called after several failed stabilisation attempts.

You receive the full history of previous reasoning. Your job:
  1. Study all previous attempts.
  2. Identify exactly where the system went wrong.
  3. Produce the most accurate, structured and reliable final answer.

Format:
  FAILURE DIAGNOSIS: ...
  FINAL ANSWER:
  ...
"""


def oracle_agent(
    task: str,
    history: list[str],
    metrics: PipelineMetrics,
) -> AgentResult:
    """Final escalation — called when ES score stays above the oracle threshold."""
    metrics.escalated = True

    history_text = "\n\n".join(
        f"--- Attempt {i + 1} ---\n{h}" for i, h in enumerate(history)
    )
    user_msg = f"TASK:\n{task}\n\nATTEMPT HISTORY:\n{history_text}"

    result = call_model(
        system=ORACLE_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=1500,
        agent_name="Oracle Agent",
    )

    metrics.es_score = 0.05
    metrics.entropy = 0.9
    print(metrics.summary())
    return result
