#!/usr/bin/env python3
"""
Пример запуска пайплайна на задаче two_sum.

Использование:
    python scripts/run_example.py

Требует заполненного .env в корне проекта (см. .env.example).
"""
import os
import sys

from dotenv import load_dotenv

# Загружаем .env из корня проекта
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import run_pipeline

TASK = """
Напиши функцию two_sum(nums: list[int], target: int) -> list[int],
которая возвращает индексы двух чисел из списка nums, дающих в сумме target.
Гарантировано, что решение существует.
""".strip()

if __name__ == "__main__":
    result = run_pipeline(
        task=TASK,
        solution_path="/tmp/solution.py",
        test_path="",       # пусто → только синтаксическая проверка
        project_dir="",
    )

    print("\n=== ФИНАЛЬНЫЙ КОД ===")
    print(result["final_code"])

    tr = result["test_result"]
    print(f"\ntests_passed = {tr.tests_passed}")
    print(f"tests_failed = {tr.tests_failed}")
    print(f"pass_rate    = {tr.pass_rate:.0%}")
