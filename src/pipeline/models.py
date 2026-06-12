"""
Data models for the pipeline: TestResult, PipelineMetrics, AgentResult.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from pipeline.config import settings


@dataclass
class TestResult:
    """Result of a single pytest run."""

    tests_passed: int = 0
    tests_failed: int = 0
    tests_error: int = 0
    output: str = ""
    returncode: int = -1

    @property
    def total(self) -> int:
        return self.tests_passed + self.tests_failed + self.tests_error

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.total if self.total > 0 else 0.0

    def summary(self) -> str:
        icon = "✅" if self.tests_failed == 0 and self.tests_error == 0 else "❌"
        return (
            f"{icon}  tests_passed={self.tests_passed}  "
            f"tests_failed={self.tests_failed}  "
            f"tests_error={self.tests_error}  "
            f"pass_rate={self.pass_rate:.0%}"
        )


@dataclass
class PipelineMetrics:
    """Running metrics / escalation state of the pipeline."""

    entropy: float = 1.0
    wmax: float = 0.0
    es_score: float = 0.0
    stab_cycles: int = 0
    token_ratio: float = 1.0
    escalated: bool = False
    stabilized: bool = False
    test_result: TestResult = field(default_factory=TestResult)
    _error_history: List[str] = field(default_factory=list)

    def register_test_result(self, tr: TestResult) -> None:
        """Recompute es_score from test outcomes."""
        self.test_result = tr

        if tr.output:
            self._error_history.append(tr.output[-300:])

        fail_penalty = (tr.tests_failed + tr.tests_error) / max(tr.total, 1)
        no_tests_penalty = 1.0 if tr.total == 0 else 0.0

        repeat_penalty = 0.0
        if len(self._error_history) >= 2:
            last = self._error_history[-1]
            prev = self._error_history[-2]
            common = sum(a == b for a, b in zip(last, prev)) / max(len(last), len(prev), 1)
            if common > 0.8:
                repeat_penalty = 0.4
                print("   ⚠️  Repeated error detected — penalty applied to ES score")

        raw = (
            fail_penalty * 0.5
            + no_tests_penalty * 0.3
            + repeat_penalty * 0.2
            + self.es_score * 0.3
        )
        self.es_score = round(min(1.0, raw), 3)

    def summary(self) -> str:
        bars = {
            "entropy": self._bar(self.entropy),
            "wmax": self._bar(self.wmax),
            "es_score": self._bar(self.es_score),
        }
        if self.escalated:
            status = "⬆️  ESCALATED"
        elif self.stabilized:
            status = "🔧 STABILIZED"
        else:
            status = "✅ STABLE"

        tr = self.test_result
        wmax_threshold = settings.wmax_threshold
        max_cycles = settings.max_stab_cycles
        return (
            f"\n{'='*60}\n"
            f"  CONTROLLER METRICS          {status}\n"
            f"{'='*60}\n"
            f"  Entropy   {bars['entropy']}  {self.entropy:.2f}\n"
            f"  Wmax      {bars['wmax']}  {self.wmax:.2f}  (threshold {wmax_threshold})\n"
            f"  ES score  {bars['es_score']}  {self.es_score:.2f}\n"
            f"  Tokens    {self.token_ratio:.2f}x   Stab cycles: {self.stab_cycles}/{max_cycles}\n"
            f"  Tests     passed={tr.tests_passed}  failed={tr.tests_failed}  error={tr.tests_error}\n"
            f"{'='*60}"
        )

    @staticmethod
    def _bar(v: float, width: int = 20) -> str:
        filled = round(v * width)
        return f"[{'█' * filled}{'░' * (width - filled)}]"


@dataclass
class AgentResult:
    """Result returned by a single agent call."""

    agent: str
    text: str
    tokens: int
    elapsed: float
    metadata: dict = field(default_factory=dict)
