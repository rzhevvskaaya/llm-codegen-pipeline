"""Pipeline configuration and LLM client initialization."""

from __future__ import annotations

import os
from getpass import getpass
from pathlib import Path

from openai import OpenAI

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv

    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

# Escalation / stabilization thresholds
WMAX_THRESHOLD = 0.85
ENTROPY_MIN = 0.30
ES_STAB_TRIGGER = 0.45
ES_ORACLE_TRIGGER = 0.75
MAX_STAB_CYCLES = 3
TOKEN_OVERHEAD = 1.50

# Reasoning models spend hundreds of tokens in  blocks before code.
DEFAULT_TOKEN_BUDGET = 1024
MIN_TOKEN_BUDGET = 512
REASONING_MODEL_MIN_TOKEN_BUDGET = 2048

# LLM settings (override via environment variables)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.duckduck.cloud/v1")
MODEL = os.getenv("MODEL", "iairlab/qwen3-32b-reasoning-cache")

# Context Agent limits
CONTEXT_EXTENSIONS = (".py", ".ipynb", ".txt", ".md", ".json", ".yaml", ".yml")
CONTEXT_MAX_CHARS_PER_FILE = 3000
CONTEXT_MAX_TOTAL_CHARS = 12000

_client: OpenAI | None = None


def is_reasoning_model(model: str | None = None) -> bool:
    """True for models that emit long  blocks before the answer."""
    name = (model or MODEL).lower()
    return any(marker in name for marker in ("reasoning", "qwen3", "deepseek-r1", "-r1"))


def resolve_token_budget(supervisor_estimate: int | float | None) -> int:
    """Apply floors; reasoning models need a much higher cap than Supervisor often estimates."""
    estimate = max(MIN_TOKEN_BUDGET, int(supervisor_estimate or DEFAULT_TOKEN_BUDGET))
    if is_reasoning_model():
        estimate = max(estimate, REASONING_MODEL_MIN_TOKEN_BUDGET)
    return estimate


def get_api_key() -> str:
    """Resolve API key from environment or interactive prompt."""
    key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        key = getpass("Enter your LLM API key: ").strip()
    if not key:
        raise RuntimeError(
            "LLM_API_KEY is missing. Add it to .env or set LLM_API_KEY / OPENAI_API_KEY."
        )
    return key


def get_client() -> OpenAI:
    """Return a singleton OpenAI-compatible client."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=get_api_key(), base_url=LLM_BASE_URL)
    return _client


def reset_client() -> None:
    """Reset client (useful in tests)."""
    global _client
    _client = None
