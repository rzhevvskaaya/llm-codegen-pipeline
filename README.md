# llm-codegen-pipeline

Мультиагентный пайплайн для автоматической генерации и верификации Python-кода. Проект исследует стратегии стабилизации: как детектировать деградацию генерации и восстанавливать корректный вывод без ручного вмешательства.

## Как работает пайплайн

Пайплайн строится из нескольких специализированных агентов, каждый из которых отвечает за свой этап:

| Компонент | Файл | Роль |
|-----------|------|------|
| Supervisor | `supervisor.py` | Профилирует задачу: оценивает сложность (`entropy_est`, `wmax_est`, `es_score`), выставляет `token_budget` |
| Context Agent | `context.py` | Опционально читает файлы проекта и добавляет релевантный контекст в промпт |
| Base Model | `agents.py` | Первичная генерация кода |
| Валидация | `validation.py` | Извлечение кода, проверка синтаксиса, поиск целевого символа, запуск pytest |
| AutoCrit | `agents.py` | Цикл исправления по дайджесту ошибок тестов |
| Attenuation | `agents.py` | Включается при `wmax ≥ 0.85` — разморозка застрявшего рассуждения через изменение температуры/промпта |
| Oracle | `agents.py` | Финальная попытка после исчерпания циклов стабилизации |
| Метрики | `metrics.py` | Entropy, Wmax, ES-score, счётчики циклов |

### Логика эскалации (`pipeline.py`)

1. **Supervisor** оценивает задачу и выставляет параметры.
2. **Base Model** генерирует код, запускаются тесты.
3. При провале — до 3 циклов стабилизации: **AutoCrit** (обычный случай) или **Attenuation** (если `wmax ≥ 0.85`).
4. Если после циклов код всё ещё не работает или ошибка повторяется — вызывается **Oracle**.
5. Все метрики аккумулируются в `PipelineMetrics` и сохраняются в отчёт.

## Структура проекта

```
stabilization_loop/
  config.py           — пороги, LLM-клиент, загрузка .env
  supervisor.py       — оценка задачи
  agents.py           — Base Model, AutoCrit, Attenuation, Oracle
  validation.py       — извлечение кода, pytest
  humaneval_eval.py   — проверка задач HumanEval
  reasoning.py        — очистка тегов reasoning-моделей
  pipeline.py         — run_pipeline()
  llm.py              — обёртка над LLM-клиентом
  metrics.py          — метрики пайплайна

benchmarks/
  humaneval.py        — загрузка задач HumanEval
  mbpp.jsonl          — датасет MBPP
  tasks.json          — кастомный набор задач

tasks/
  registry.py         — 4 учебные задачи для быстрой проверки

experiments/
  analyze_metrics.py  — анализ JSON-отчёта

tests/                — pytest-тесты по одному файлу на задачу

run.py                — основной запуск (HumanEval / benchmark / одна задача)
run_custom_tasks.py   — запуск на произвольных задачах из tasks.json
```

## Требования

- Python 3.10+
- Доступ к OpenAI-совместимому API (ключ + base URL)

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux / macOS
pip install -r requirements.txt
```

Для бенчмарков (HumanEval):

```bash
pip install -r requirements-benchmark.txt
```

## Конфигурация

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # Linux / macOS
```

Заполните `.env`:

```env
LLM_API_KEY=ваш-ключ
LLM_BASE_URL=https://...
MODEL=название-модели
```

## Запуск

**Одна задача из локального набора (1–4):**

```bash
python run.py --task 1
```

**Весь локальный бенчмарк:**

```bash
python run.py --benchmark --save-report output/benchmark_report.json
```

**HumanEval (первые N задач):**

```bash
python run.py --humaneval --humaneval-limit 10
```

**Кастомные задачи из `tasks.json`:**

```bash
python run_custom_tasks.py --tasks benchmarks/tasks.json
python run_custom_tasks.py --tasks benchmarks/tasks.json --task-id T001
python run_custom_tasks.py --tasks benchmarks/tasks.json --save-report output/report.json
```

## Ключевые параметры (`config.py`)

| Параметр | Значение по умолчанию | Описание |
|---|---|---|
| `WMAX_THRESHOLD` | `0.85` | Порог для переключения с AutoCrit на Attenuation |
| `MAX_STAB_CYCLES` | `3` | Максимальное число циклов стабилизации |
| `MIN_TOKEN_BUDGET` | `512` | Минимальный бюджет токенов |
| `REASONING_MODEL_MIN_TOKEN_BUDGET` | `2048` | Минимум для reasoning-моделей (защита от обрезки) |
| `ES_STAB_TRIGGER` | `0.45` | Порог ES для запуска стабилизации (задан, но эскалация сейчас идёт по результатам тестов) |
| `ES_ORACLE_TRIGGER` | `0.75` | Порог ES для вызова Oracle |

## Программный вызов

```python
from stabilization_loop import run_pipeline
from tasks.registry import TASK_REGISTRY

result = run_pipeline(task_spec=TASK_REGISTRY[1])
print(result["success"], result["metrics"].summary())
```

## Анализ результатов

```bash
python experiments/analyze_metrics.py output/benchmark_report.json
```
