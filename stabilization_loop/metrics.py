"""Data structures and controller metrics for the stabilization pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from stabilization_loop.config import MAX_STAB_CYCLES, WMAX_THRESHOLD


@dataclass
class TestResult:
    """Result of one validation/test run for the generated solution."""

    tests_passed: int = 0
    tests_failed: int = 0
    tests_error: int = 0
    output: str = ""
    returncode: int = -1
    failure_type: str = "UNKNOWN_FAILURE"
    failure_signature: str = ""
    digest: str = ""
    test_path: str = ""

    @property
    def total(self) -> int:
        return self.tests_passed + self.tests_failed + self.tests_error

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.total if self.total > 0 else 0.0

    @property
    def passed(self) -> bool:
        return self.returncode == 0 and self.tests_failed == 0 and self.tests_error == 0

    def summary(self) -> str:
        icon = "PASS" if self.passed else "FAIL"
        return (
            f"{icon}  tests_passed = {self.tests_passed}  |  "
            f"tests_failed = {self.tests_failed}  |  "
            f"tests_error  = {self.tests_error}  |  "
            f"pass_rate    = {self.pass_rate:.0%}  |  "
            f"failure_type = {self.failure_type}"
        )


@dataclass
class PipelineMetrics:
    """Controller metrics for the loop-engineered code stabilization pipeline."""

    entropy: float = 1.0
    wmax: float = 0.0
    es_score: float = 0.0
    stab_cycles: int = 0
    token_ratio: float = 1.0
    escalated: bool = False
    stabilized: bool = False
    test_result: TestResult = field(default_factory=TestResult)
    _error_history: list[str] = field(default_factory=list)

    def register_test_result(self, tr: TestResult) -> None:
        """Update ES score based on validation/test result."""
        self.test_result = tr

        if tr.failure_signature:
            self._error_history.append(tr.failure_signature)

        if tr.passed:
            self.es_score = 0.0
            return

        fail_penalty = 1.0 - tr.pass_rate
        no_tests_penalty = 1.0 if tr.total == 0 else 0.0

        hard_failure_types = {
            "NON_CODE_OUTPUT",
            "NO_CODE_EXTRACTED",
            "SYNTAX_ERROR",
            "MISSING_SYMBOL",
            "WRONG_SIGNATURE",
            "TEST_FILE_ERROR",
            "TASK_TEST_MISMATCH",
            "TIMEOUT",
        }
        hard_failure_penalty = 0.35 if tr.failure_type in hard_failure_types else 0.15

        repeat_penalty = 0.0
        if len(self._error_history) >= 2 and self._error_history[-1] == self._error_history[-2]:
            repeat_penalty = 0.25
            print("   Warning: repeated failure signature detected")

        raw = fail_penalty * 0.45 + no_tests_penalty * 0.15 + hard_failure_penalty + repeat_penalty
        self.es_score = round(min(1.0, max(raw, self.es_score * 0.50)), 3)

    def tests_pending(self) -> bool:
        """True before the first validation/pytest run."""
        return self.test_result.failure_type == "UNKNOWN_FAILURE"

    def summary(self) -> str:
        bars = {
            "entropy": self._bar(self.entropy),
            "wmax": self._bar(self.wmax),
            "es_score": self._bar(self.es_score),
        }
        if self.tests_pending:
            status = "PROFILED"
        elif self.test_result.passed:
            status = "STABLE"
            if self.stabilized:
                status = "STABILIZED"
        else:
            status = "NEEDS REPAIR"
        if self.escalated:
            status = "ESCALATED"
        if self.stabilized and self.test_result.passed:
            status = "STABILIZED"

        tr = self.test_result
        if self.tests_pending:
            tests_line = "  Tests     (not run yet)"
            failure_line = ""
        else:
            tests_line = f"  Tests     passed={tr.tests_passed}  failed={tr.tests_failed}  error={tr.tests_error}"
            failure_line = f"  Failure   {tr.failure_type}\n"

        return (
            f"\n{'=' * 60}\n"
            f"  CONTROLLER METRICS          {status}\n"
            f"{'=' * 60}\n"
            f"  Entropy   {bars['entropy']}  {self.entropy:.2f}\n"
            f"  Wmax      {bars['wmax']}  {self.wmax:.2f}  (threshold {WMAX_THRESHOLD})\n"
            f"  ES score  {bars['es_score']}  {self.es_score:.2f}\n"
            f"  Tokens    {self.token_ratio:.2f}x   Stabilization cycles: {self.stab_cycles}/{MAX_STAB_CYCLES}\n"
            f"{tests_line}\n"
            f"{failure_line}"
            f"{'=' * 60}"
        )

    @staticmethod
    def _bar(value: float, width: int = 20) -> str:
        filled = max(0, min(width, round(value * width)))
        return f"[{'#' * filled}{'.' * (width - filled)}]"


@dataclass
class AgentResult:
    """Result produced by one agent call."""

    agent: str
    text: str
    tokens: int
    elapsed: float
    metadata: dict = field(default_factory=dict)
