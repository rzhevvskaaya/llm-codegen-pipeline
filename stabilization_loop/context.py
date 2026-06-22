"""Context Agent: codebase indexing and analysis."""

from __future__ import annotations

import json
import os

from stabilization_loop.config import (
    CONTEXT_EXTENSIONS,
    CONTEXT_MAX_CHARS_PER_FILE,
    CONTEXT_MAX_TOTAL_CHARS,
)
from stabilization_loop.llm import call_model, clean_llm_json

CONTEXT_AGENT_SYSTEM = """
Ты — Context Agent в мультиагентной системе.
Тебе передаётся снимок кодовой базы проекта и задача пользователя.

Твоя задача:
  1. Определи главные модули и их назначение.
  2. Выдели ключевые классы, функции, зависимости.
  3. Укажи, какие файлы и сущности релевантны для задачи.
  4. Сформируй краткий контекст (context_for_codegen) для передачи в Base Model.

Верни ТОЛЬКО валидный JSON без пояснений и markdown-блоков:
{
  "architecture_summary": "...",
  "relevant_files": ["file1.py", ...],
  "key_entities": ["ClassName", "function_name", ...],
  "context_for_codegen": "... готовый текст-контекст для Base Model ..."
}
"""


def build_context_snapshot(project_dir: str) -> str:
    """Walk project directory and collect file contents for prompt injection."""
    snapshot_parts: list[str] = []
    total_chars = 0
    files_found = 0
    files_skipped = 0

    if not os.path.isdir(project_dir):
        print(f"   Directory not found: {project_dir}")
        return ""

    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [
            d
            for d in dirs
            if d not in ("__pycache__", ".git", ".ipynb_checkpoints", "node_modules", ".venv", "venv", "env")
        ]

        for fname in sorted(files):
            if not fname.endswith(CONTEXT_EXTENSIONS):
                continue
            if total_chars >= CONTEXT_MAX_TOTAL_CHARS:
                files_skipped += 1
                continue

            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, project_dir)

            try:
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read(CONTEXT_MAX_CHARS_PER_FILE)
            except OSError as exc:
                snapshot_parts.append(f"### FILE: {rel}\n[read error: {exc}]\n")
                continue

            chunk = f"### FILE: {rel}\n{content}\n"
            snapshot_parts.append(chunk)
            total_chars += len(chunk)
            files_found += 1

    print(f"   Files indexed: {files_found}")
    if files_skipped:
        print(f"   Files skipped (limit): {files_skipped}")
    print(f"   Snapshot size: {total_chars:,} chars")

    return "\n".join(snapshot_parts)


def context_agent(task: str, project_dir: str) -> dict:
    """Analyze codebase and return structured context for code generation."""
    print("\n  Scanning project...")
    snapshot = build_context_snapshot(project_dir)

    if not snapshot:
        print("    Empty snapshot — pipeline continues without context")
        return {"context_for_codegen": ""}

    prompt = f"Задача пользователя:\n{task}\n\nКодовая база проекта:\n{snapshot}"

    result = call_model(
        system=CONTEXT_AGENT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        agent_name="Context Agent — codebase analysis",
    )

    try:
        cleaned = clean_llm_json(result.text)
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        print("     JSON parse failed — passing snapshot directly")
        data = {"context_for_codegen": snapshot[:4000]}

    print(f"   Relevant files: {len(data.get('relevant_files', []))}")
    print(f"   Key entities: {len(data.get('key_entities', []))}")
    return data
