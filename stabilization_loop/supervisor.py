"""Supervisor Agent: task profiling and escalation scoring."""

from __future__ import annotations

import json
import re

from stabilization_loop.config import DEFAULT_TOKEN_BUDGET, is_reasoning_model, resolve_token_budget
from stabilization_loop.llm import call_model, clean_llm_json, try_extract_json
from stabilization_loop.metrics import PipelineMetrics

SUPERVISOR_SYSTEM = """
You are the Supervisor Agent (escalation controller) in a multi-agent code generation system.

Analyze the task and return ONLY a JSON object with these fields:
  profile      — one short sentence (max 10 words)
  complexity   — float [0..1]
  entropy_est  — float [0..1]
  wmax_est     — float [0..1]
  risk_loops   — float [0..1]
  es_score     — float [0..1]
  token_budget — integer (512–2048 for code generation)

CRITICAL:
- Output ONLY valid JSON. No markdown, no reasoning tags, no extra text.
- First character must be '{', last must be '}'.
"""

SUPERVISOR_RETRY_MSG = """Return ONLY this JSON shape, nothing else:
{"profile":"code generation","complexity":0.5,"entropy_est":0.5,"wmax_est":0.5,"risk_loops":0.3,"es_score":0.4,"token_budget":1024}"""

DEFAULT_SUPERVISOR_PROFILE: dict = {
    "profile": "code generation task",
    "complexity": 0.5,
    "entropy_est": 0.5,
    "wmax_est": 0.5,
    "risk_loops": 0.3,
    "es_score": 0.4,
    "token_budget": DEFAULT_TOKEN_BUDGET,
}


class SupervisorJSONError(Exception):
    """Supervisor returned invalid JSON."""


def summarize_task_for_supervisor(task: str, task_spec: dict | None = None) -> str:
    """Short task summary so Supervisor does not burn tokens on long HumanEval prompts."""
    if task_spec and task_spec.get("benchmark") == "humaneval":
        problem = task_spec["humaneval_problem"]
        entry = problem["entry_point"]
        sig_match = re.search(rf"def\s+{re.escape(entry)}\s*\([^)]*\)", task)
        signature = sig_match.group(0) if sig_match else entry
        return (
            f"HumanEval algorithmic task.\n"
            f"Function: {entry}\n"
            f"Signature: {signature}\n"
            f"Complete the function body to pass hidden unit tests."
        )

    if len(task) > 800:
        return task[:800] + "\n...(truncated for supervisor profiling)"
    return task


def _parse_supervisor_json(text: str) -> dict:
    cleaned = clean_llm_json(text)
    if not cleaned.strip():
        cleaned = try_extract_json(text)
    if cleaned and not cleaned.strip().startswith("{"):
        cleaned = try_extract_json(cleaned)
    return json.loads(cleaned)


def _apply_profile(data: dict, metrics: PipelineMetrics) -> dict:
    required = {"entropy_est", "wmax_est", "es_score", "token_budget"}
    missing = required - data.keys()
    if missing:
        raise SupervisorJSONError(f"Supervisor JSON missing fields: {missing}")

    metrics.entropy = float(data["entropy_est"])
    metrics.wmax = float(data["wmax_est"])
    metrics.es_score = float(data["es_score"])
    print(metrics.summary())
    return data


def _fallback_profile(task_summary: str, metrics: PipelineMetrics, reason: str) -> dict:
    print(f"  Warning: Supervisor fallback — {reason}")
    data = dict(DEFAULT_SUPERVISOR_PROFILE)
    first_line = task_summary.strip().splitlines()[0][:60]
    data["profile"] = first_line or data["profile"]
    return _apply_profile(data, metrics)


def supervisor_profile(
    task: str,
    metrics: PipelineMetrics,
    task_spec: dict | None = None,
) -> dict:
    """Profile task and update pipeline metrics. Falls back to defaults if JSON fails."""
    task_summary = summarize_task_for_supervisor(task, task_spec)
    user_content = task_summary
    if is_reasoning_model():
        user_content += "\n\n/no_think"

    max_tokens = resolve_token_budget(512)

    result = call_model(
        system=SUPERVISOR_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
        max_tokens=max_tokens,
        agent_name="Supervisor Agent — task profiling",
    )

    try:
        return _apply_profile(_parse_supervisor_json(result.text), metrics)
    except (json.JSONDecodeError, SupervisorJSONError):
        print("  Warning: Supervisor JSON parse failed — retrying...")

    retry_content = f"Task: {task_summary[:200]}\n\n{SUPERVISOR_RETRY_MSG}"
    if is_reasoning_model():
        retry_content += "\n/no_think"

    result = call_model(
        system=SUPERVISOR_SYSTEM,
        messages=[{"role": "user", "content": retry_content}],
        max_tokens=256,
        agent_name="Supervisor Agent — retry",
    )

    try:
        return _apply_profile(_parse_supervisor_json(result.text), metrics)
    except (json.JSONDecodeError, SupervisorJSONError) as exc:
        return _fallback_profile(task_summary, metrics, str(exc)[:120])
