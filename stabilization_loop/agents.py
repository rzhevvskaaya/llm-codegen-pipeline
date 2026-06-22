"""Base Model, stabilization agents (AutoCrit/Attenuation), and Oracle."""

from __future__ import annotations

from stabilization_loop.config import WMAX_THRESHOLD, is_reasoning_model, resolve_token_budget
from stabilization_loop.llm import call_model
from stabilization_loop.metrics import AgentResult, PipelineMetrics
from stabilization_loop.validation import prepare_and_test_llm_output

BASE_SYSTEM = """
You are the Base Code Generator inside a deterministic loop-engineered multi-agent system.

CRITICAL OUTPUT CONTRACT:
- Return raw Python code only.
- Do NOT use reasoning tags or  blocks — output code immediately.
- Do not use markdown fences.
- Do not explain the code.
- The first character of your response must be valid Python code (def, class, or import).
- The file will be saved directly as solution.py and executed by pytest.
"""

AUTOCRIT_SYSTEM = """
You are AutoCrit, a repair agent inside a deterministic loop-engineered code stabilization system.

CRITICAL OUTPUT CONTRACT:
- Return raw Python code only.
- Do not use markdown fences.
- Do not explain your repair.
- Do not include reasoning tags.
- Preserve the expected top-level function/class name exactly.
- The file will be saved directly as solution.py and executed by pytest.
"""

ATTENUATION_SYSTEM = """
You are the Attenuation Agent inside a deterministic loop-engineered code stabilization system.
The previous attempt is stuck or overly committed to one wrong approach.

CRITICAL OUTPUT CONTRACT:
- Return raw Python code only.
- Do not use markdown fences.
- Do not explain your repair.
- Do not include reasoning tags.
- Preserve the expected top-level function/class name exactly.
- The file will be saved directly as solution.py and executed by pytest.
"""

ORACLE_SYSTEM = """
You are the Oracle Agent, the final repair agent in a deterministic loop-engineered code stabilization system.

Your job is not to explain the failure. Your job is to produce the final corrected solution.py.

CRITICAL OUTPUT CONTRACT:
- Return raw Python code only.
- Do not use markdown fences.
- Do not include explanations.
- Do not include reasoning tags.
- Preserve the expected top-level function/class name exactly.
- The file will be saved directly as solution.py and executed by pytest.
"""


def estimate_entropy(text: str) -> float:
    """Simple entropy proxy based on bigram uniqueness."""
    words = text.lower().split()
    if len(words) < 4:
        return 0.5
    bigrams = [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]
    unique_ratio = len(set(bigrams)) / len(bigrams)
    return round(min(unique_ratio, 1.0), 3)


def estimate_wmax(text: str) -> float:
    """Heuristic Wmax proxy: frequency share of the most common long token."""
    words = [w for w in text.lower().split() if len(w) > 3]
    if not words:
        return 0.0
    freq: dict[str, int] = {}
    for word in words:
        freq[word] = freq.get(word, 0) + 1
    return round(max(freq.values()) / len(words), 3)


def base_model_reason(
    task: str,
    metrics: PipelineMetrics,
    token_budget: int = 900,
    solution_path: str = "solution.py",
    test_path: str = "",
    expected_symbol: str | None = None,
    humaneval_problem: dict | None = None,
) -> AgentResult:
    """Base Model: generate code, validate, write file, run tests."""
    max_tokens = resolve_token_budget(token_budget)
    exact_contract = (
        f"Task:\n{task}\n\n"
        f"Expected top-level symbol: {expected_symbol or '(not specified)'}\n"
        f"Return ONLY raw Python code for solution.py."
    )
    if is_reasoning_model():
        exact_contract += "\n\n/no_think"

    result = call_model(
        system=BASE_SYSTEM,
        messages=[{"role": "user", "content": exact_contract}],
        max_tokens=max_tokens,
        agent_name="Base Model — code generation",
    )

    metrics.entropy = estimate_entropy(result.text)
    metrics.wmax = estimate_wmax(result.text)
    metrics.token_ratio = result.metadata.get("output_tokens", 0) / max(max_tokens * 0.5, 1)

    code, tr = prepare_and_test_llm_output(
        result.text,
        solution_path=solution_path,
        test_path=test_path,
        expected_symbol=expected_symbol,
        humaneval_problem=humaneval_problem,
    )
    result.metadata["candidate_code"] = code
    result.metadata["test_result"] = tr
    metrics.register_test_result(tr)

    print(metrics.summary())
    return result


def stabilize(
    task: str,
    previous_code: str,
    metrics: PipelineMetrics,
    cycle: int,
    solution_path: str = "solution.py",
    test_path: str = "",
    expected_symbol: str | None = None,
    humaneval_problem: dict | None = None,
) -> AgentResult:
    """Repair code based on structured validation/pytest feedback."""
    metrics.stab_cycles += 1

    test_context = ""
    if metrics.test_result:
        test_context = (
            f"\n\nPrevious validation/test result:\n"
            f"{metrics.test_result.summary()}\n\n"
            f"Structured failure digest:\n{metrics.test_result.digest}\n"
        )

    if metrics.wmax >= WMAX_THRESHOLD:
        print(f"\n  Wmax={metrics.wmax:.2f} > {WMAX_THRESHOLD} -> Attenuation cycle {cycle}")
        system = ATTENUATION_SYSTEM
        agent_name = f"Attenuation Agent cycle {cycle}"
    else:
        print(f"\n  ES={metrics.es_score:.2f} -> AutoCrit cycle {cycle}")
        system = AUTOCRIT_SYSTEM
        agent_name = f"AutoCrit Agent cycle {cycle}"

    user_msg = (
        f"Task:\n{task}\n\n"
        f"Expected top-level symbol: {expected_symbol or '(not specified)'}\n\n"
        f"Previous code:\n{previous_code}\n"
        f"{test_context}\n"
        f"Return only the corrected raw Python code."
    )
    if is_reasoning_model():
        user_msg += "\n\n/no_think"

    result = call_model(
        system=system,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=resolve_token_budget(1024),
        agent_name=agent_name,
    )

    code, tr = prepare_and_test_llm_output(
        result.text,
        solution_path=solution_path,
        test_path=test_path,
        expected_symbol=expected_symbol,
        humaneval_problem=humaneval_problem,
    )
    result.metadata["candidate_code"] = code
    result.metadata["test_result"] = tr
    metrics.register_test_result(tr)

    metrics.entropy = min(1.0, estimate_entropy(result.text) + 0.1)
    metrics.wmax = max(0.0, estimate_wmax(result.text) - 0.1)
    metrics.stabilized = True

    print(metrics.summary())
    return result


def oracle_agent(
    task: str,
    history: list[str],
    metrics: PipelineMetrics,
    expected_symbol: str | None = None,
    humaneval_problem: dict | None = None,
) -> AgentResult:
    """Oracle Agent: final code-only repair attempt."""
    metrics.escalated = True

    history_text = "\n\n".join(f"--- Attempt {i + 1} code ---\n{h}" for i, h in enumerate(history[-4:]))
    user_msg = (
        f"Task:\n{task}\n\n"
        f"Expected top-level symbol: {expected_symbol or '(not specified)'}\n\n"
        f"Last failure digest:\n{metrics.test_result.digest}\n\n"
        f"Previous attempts:\n{history_text}\n\n"
        f"Return only the final corrected raw Python code."
    )
    if is_reasoning_model():
        user_msg += "\n\n/no_think"

    result = call_model(
        system=ORACLE_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=resolve_token_budget(1500),
        agent_name="Oracle Agent — final code repair",
    )

    metrics.entropy = 0.9
    return result
