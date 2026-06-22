"""Main multi-agent pipeline orchestration."""

from __future__ import annotations

import os
import time

from stabilization_loop.agents import base_model_reason, oracle_agent, stabilize
from stabilization_loop.config import DEFAULT_TOKEN_BUDGET, MAX_STAB_CYCLES, resolve_token_budget
from stabilization_loop.context import context_agent
from stabilization_loop.metrics import PipelineMetrics
from stabilization_loop.supervisor import supervisor_profile
from stabilization_loop.validation import prepare_and_test_llm_output


def run_pipeline(
    task: str | None = None,
    solution_path: str = "output/solution.py",
    test_path: str | None = None,
    expected_symbol: str | None = None,
    task_spec: dict | None = None,
    use_context: bool = False,
    project_dir: str | None = None,
    verbose: bool = True,
) -> dict:
    """
    Deterministic multi-agent pipeline with isolated pytest verification.

    Recommended usage:
        output = run_pipeline(task_spec=TASK_REGISTRY[1])

    Core gates:
      1. Supervisor profiling
      2. Optional Context Agent
      3. Base Model code generation
      4. Code-only / syntax / symbol gates
      5. Isolated pytest gate
      6. AutoCrit/Attenuation stabilization loop
      7. Oracle final repair attempt
    """
    if task_spec is not None:
        task = task_spec["prompt"]
        test_path = task_spec["test_path"]
        expected_symbol = task_spec.get("expected_symbol")
        humaneval_problem = task_spec.get("humaneval_problem")
    else:
        humaneval_problem = None

    if not task:
        raise ValueError("run_pipeline requires either task or task_spec")

    test_path = test_path or ""

    print("LOOP-ENGINEERED MULTI-AGENT PIPELINE")
    print(f"   Task          : {task[:90]}{'...' if len(task) > 90 else ''}")
    print(f"   Expected name : {expected_symbol or '(not specified)'}")
    print(f"   Solution      : {solution_path}")
    print(f"   Tests         : {test_path or ('HumanEval' if humaneval_problem else '(syntax only)')}")

    metrics = PipelineMetrics()
    history: list[str] = []
    results = []
    t_total = time.perf_counter()

    # 1. Supervisor
    profile = supervisor_profile(task, metrics, task_spec=task_spec)
    raw_budget = int(profile.get("token_budget", DEFAULT_TOKEN_BUDGET))
    token_budget = resolve_token_budget(raw_budget)
    if token_budget != raw_budget:
        print(f"   Token budget raised to {token_budget} (Supervisor estimate {raw_budget} is too low)")

    print(f"\n   Task profile : {profile.get('profile', '')}")
    print(f"   ES score     : {metrics.es_score:.2f}")
    print(f"   Token budget : {token_budget}")

    # 2. Optional Context Agent
    enriched_task = task
    ctx_data: dict = {"context_for_codegen": ""}
    if use_context and project_dir:
        ctx_data = context_agent(task, project_dir)
        context_injection = ctx_data.get("context_for_codegen", "")
        if context_injection:
            enriched_task = f"Project context:\n{context_injection}\n\nUser task:\n{task}"
            print(f"\n   Context added ({len(context_injection)} chars)")

    # 3. Base Model + gates + tests
    base_result = base_model_reason(
        enriched_task,
        metrics,
        token_budget,
        solution_path=solution_path,
        test_path=test_path,
        expected_symbol=expected_symbol,
        humaneval_problem=humaneval_problem,
    )
    current_code = base_result.metadata.get("candidate_code", "")
    history.append(current_code)
    results.append(base_result)

    # 4. Stabilization loop
    early_stop_types = {"TEST_FILE_ERROR", "TASK_TEST_MISMATCH"}

    for cycle in range(1, MAX_STAB_CYCLES + 1):
        if metrics.test_result.passed:
            print("\n  Verification gate passed — stabilization is not needed")
            break

        if metrics.test_result.failure_type in early_stop_types:
            print(f"\n  Configuration failure detected: {metrics.test_result.failure_type}. Stopping early.")
            break

        if len(metrics._error_history) >= 2 and metrics._error_history[-1] == metrics._error_history[-2]:
            print("\n  Repeated failure signature detected — escalating to Oracle")
            break

        print(f"\n  Tests not passed — stabilization cycle {cycle}/{MAX_STAB_CYCLES}")
        stab_result = stabilize(
            task,
            current_code,
            metrics,
            cycle,
            solution_path=solution_path,
            test_path=test_path,
            expected_symbol=expected_symbol,
            humaneval_problem=humaneval_problem,
        )
        current_code = stab_result.metadata.get("candidate_code", current_code)
        history.append(current_code)
        results.append(stab_result)

    # 5. Oracle final attempt if still failing
    if not metrics.test_result.passed and metrics.test_result.failure_type not in early_stop_types:
        print("\n  FINAL ESCALATION -> Oracle Agent")
        oracle_result = oracle_agent(
            task, history, metrics,
            expected_symbol=expected_symbol,
            humaneval_problem=humaneval_problem,
        )
        results.append(oracle_result)
        oracle_code, tr = prepare_and_test_llm_output(
            oracle_result.text,
            solution_path=solution_path,
            test_path=test_path,
            expected_symbol=expected_symbol,
            humaneval_problem=humaneval_problem,
        )
        oracle_result.metadata["candidate_code"] = oracle_code
        oracle_result.metadata["test_result"] = tr
        current_code = oracle_code
        history.append(current_code)
        metrics.register_test_result(tr)
        print(metrics.summary())

    elapsed = time.perf_counter() - t_total
    total_tokens = sum(r.tokens for r in results)
    tr = metrics.test_result
    final_code = open(solution_path, encoding="utf-8").read() if os.path.exists(solution_path) else current_code

    print("\n" + "=" * 60)
    print("PIPELINE FINISHED")
    print(f"   Success              : {'YES' if tr.passed else 'NO'}")
    print(f"   Agents used          : {len(results)}")
    print(f"   Stabilization cycles : {metrics.stab_cycles}")
    print(f"   Oracle escalation    : {'YES' if metrics.escalated else 'NO'}")
    print(f"   Total tokens         : {total_tokens}")
    print(f"   Total time           : {elapsed:.1f}s")
    print(f"   Final status         : {tr.summary()}")
    print("=" * 60)

    return {
        "success": tr.passed,
        "failure_type": tr.failure_type,
        "failure_digest": tr.digest,
        "final_answer": current_code,
        "final_code": final_code,
        "test_result": tr,
        "metrics": metrics,
        "results": results,
        "profile": profile,
        "task_spec": task_spec,
        "total_tokens": total_tokens,
        "elapsed_sec": round(elapsed, 2),
    }
