"""
Конфигурация пайплайна — все секреты берутся из переменных окружения.

Скопируйте .env.example в .env и заполните свои значения:

    LLM_API_KEY=sk-...
    LLM_BASE_URL=https://api.duckduck.cloud/v1
    LLM_MODEL=iairlab/qwen3-32b-reasoning-cache
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    # ── Подключение к LLM (только из .env, без дефолтов) ──────────────────
    api_key: str = ""
    base_url: str = ""
    model: str = ""

    # ── Пороги пайплайна ───────────────────────────────────────────────────
    wmax_threshold: float = 0.85
    entropy_min: float = 0.30
    es_stab_trigger: float = 0.45
    es_oracle_trigger: float = 0.75
    max_stab_cycles: int = 3
    token_overhead: float = 1.50

    # ── Context Agent ──────────────────────────────────────────────────────
    context_extensions: tuple = (".py", ".ipynb", ".txt", ".md", ".json", ".yaml", ".yml")
    context_max_chars_per_file: int = 3_000
    context_max_total_chars: int = 12_000

    def __post_init__(self) -> None:
        self.api_key  = os.environ.get("LLM_API_KEY",  "")
        self.base_url = os.environ.get("LLM_BASE_URL", "")
        self.model    = os.environ.get("LLM_MODEL",    "")

        missing = [k for k, v in {
            "LLM_API_KEY":  self.api_key,
            "LLM_BASE_URL": self.base_url,
            "LLM_MODEL":    self.model,
        }.items() if not v]

        if missing:
            raise EnvironmentError(
                f"Не заданы обязательные переменные окружения: {', '.join(missing)}\n"
                "Скопируйте .env.example в .env и заполните значения."
            )


# Синглтон — импортируйте везде
settings = Settings()
