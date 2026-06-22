"""
Main pipeline entry point.

Usage:
    from pipeline import run_pipeline

    result = run_pipeline(
        task="Write a function two_sum(nums, target) ...",
        solution_path="/tmp/solution.py",
        test_path="tests/test_tasks.py",
        project_dir="path/to/codebase",   # optional
    )
    print(result["final_code"])
    print(result["test_result"].summary())
"""
from __future__ import annotations

import os
import time

from pipeline.agents import (
    base_model_reason,
    context_agent,
    extract_code_block,
    oracle_agent,
    stabilize,
    supervisor_profile,
)
from pipeline.code_tools import run_tests, write_code_to_file
from pipeline.config import settings
from pipeline.models import PipelineMetrics


def run_pipeline(
    task: str,
    solution_path: str = "/tmp/solution.py",
    test_path: str = "",
    project_dir: str = "",
    verbose: bool = True,
) -> dict:
    """
    Run the full multi-agent code generation pipeline.

    Parameters
    ----------
    task          : Natural-language coding task.
    solution_path : Where to write the generated code.
    test_path     : Path to a pytest file. Empty = syntax check only.
    project_dir   : Codebase root for the Context Agent (optional).

    Returns
    -------
    dict with keys:
        final_code   — the best code produced
        test_result  — TestResult from the last test run
        metrics      — PipelineMetrics
        results      — list[AgentResult] from every agent called
        profile      — Supervisor JSON profile
        total_tokens — total tokens consumed
        elapsed_sec  — wall-clock time
    """
    print("🚀 MULTI-AGENT CODE GENERATION PIPELINE")
    print(f"   Task         : {task[:80]}{'...' if len(task) > 80 else ''}")
    print(f"   Solution     : {solution_path}")
    print(f"   Tests        : {test_path or '(syntax check only)'}")

    metrics = PipelineMetrics()
    history: list[str] = []
    results = []
    t_total = time.perf_counter()

    # ── 1. Supervisor ─────────────────────────────────────────────────────
    profile = supervisor_profile(task, metrics)
    token_budget = int(profile.get("token_budget", 900))

    print(f"\n   Task profile  : {profile.get('profile', '')}")
    print(f"   ES score      : {metrics.es_score:.2f}")
    print(f"   Token budget  : {token_budget}")

    # ── 2. Context Agent ──────────────────────────────────────────────────
    enriched_task = task
    if project_dir:
        ctx_data = context_agent(task, project_dir)
        context_injection = ctx_data.get("context_for_codegen", "")
        if context_injection:
            enriched_task = (
                f"PROJECT CONTEXT:\n{context_injection}\n\n"
                f"USER TASK:\n{task}"
            )
            print(f"\n   Context injected ({len(context_injection)} chars)")

    # ── 3. Base Model ─────────────────────────────────────────────────────
    base_result = base_model_reason(
        enriched_task, metrics, token_budget,
        solution_path=solution_path, test_path=test_path,
    )
    history.append(base_result.text)
    results.append(base_result)
    current_text = base_result.text

    # ── 4. Stabilisation loop ─────────────────────────────────────────────
    for cycle in range(1, settings.max_stab_cycles + 1):
        if metrics.es_score < settings.es_stab_trigger:
            print(f"\n  ✅ ES={metrics.es_score:.2f} < {settings.es_stab_trigger} — no stabilisation needed")
            break

        if metrics.es_score >= settings.es_oracle_trigger:
            print(f"\n  ⬆️  ES={metrics.es_score:.2f} >= {settings.es_oracle_trigger} — escalating to Oracle")
            break

        print(f"\n  🔧 ES={metrics.es_score:.2f} — stabilisation cycle {cycle}/{settings.max_stab_cycles}")
        stab_result = stabilize(
            task, current_text, metrics, cycle,
            solution_path=solution_path, test_path=test_path,
        )
        history.append(stab_result.text)
        results.append(stab_result)
        current_text = stab_result.text

    # ── 5. Oracle (if needed) ─────────────────────────────────────────────
    if metrics.es_score >= settings.es_oracle_trigger:
        print("\n  ⬆️  FINAL ESCALATION → Oracle Agent")
        oracle_result = oracle_agent(task, history, metrics)
        results.append(oracle_result)
        current_text = oracle_result.text

        code = extract_code_block(current_text)
        write_code_to_file(code, solution_path)
        tr = run_tests(solution_path, test_path)
        metrics.register_test_result(tr)

    # ── Summary ───────────────────────────────────────────────────────────
    elapsed = time.perf_counter() - t_total
    total_tokens = sum(r.tokens for r in results)
    tr = metrics.test_result

    print("\n" + "=" * 60)
    print("✅ PIPELINE COMPLETE")
    print(f"   Agents used        : {len(results)}")
    print(f"   Stabilisation cycles: {metrics.stab_cycles}")
    print(f"   Oracle escalated   : {'Yes' if metrics.escalated else 'No'}")
    print(f"   Total tokens       : {total_tokens}")
    print(f"   Wall-clock time    : {elapsed:.1f}s")
    print(f"   {'─' * 20}")
    print(f"   {tr.summary()}")
    print("=" * 60)

    final_code = ""
    if os.path.exists(solution_path):
        with open(solution_path) as f:
            final_code = f.read()

    return {
        "final_code": final_code,
        "test_result": tr,
        "metrics": metrics,
        "results": results,
        "profile": profile,
        "total_tokens": total_tokens,
        "elapsed_sec": round(elapsed, 2),
    }
