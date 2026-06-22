"""Loop-engineered multi-agent code stabilization pipeline."""

from stabilization_loop.pipeline import run_pipeline
from stabilization_loop.metrics import PipelineMetrics, TestResult, AgentResult

__all__ = [
    "run_pipeline",
    "PipelineMetrics",
    "TestResult",
    "AgentResult",
]

__version__ = "1.0.0"
