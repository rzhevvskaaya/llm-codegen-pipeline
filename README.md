# llm-codegen-pipeline

Репозиторий с кодом мультиагентного пайплайна генерации Python-кода: Supervisor → Base Model → проверка → стабилизация (AutoCrit / Attenuation) → Oracle.

## Архитектура

Содержит модули и запускается через `run.py`.

| Компонент | Файл | Задача                                                                                         |
|-----------|------|---------------------------------------------------------------------------------------------|
| Supervisor | `supervisor.py` | Профилирует задачу, возвращает JSON с `entropy_est`, `wmax_est`, `es_score`, `token_budget` |
| Context Agent | `context.py` | Опционально читает файлы проекта и добавляет контекст в промпт                              |
| Base Model | `agents.py` | Первая генерация кода                                                                       |
| Валидация | `validation.py` | Извлечение кода, синтаксис, символ, pytest                                                  |
| AutoCrit | `agents.py` | Починка по digest ошибки тестов                                                             |
| Attenuation | `agents.py` | Включается при `wmax >= 0.85` — «разморозка» застрявшего рассуждения                        |
| Oracle | `agents.py` | Финальная попытка после исчерпания циклов стабилизации                                      |
| Контроллер | `metrics.py` | Entropy, Wmax, ES score, счётчики циклов                                                    |

Логика эскалации в `pipeline.py`:

1. Supervisor оценивает задачу.
2. Base Model генерирует код и гоняет тесты.
3. Если тесты не прошли — до 3 циклов стабилизации (AutoCrit или Attenuation по Wmax).
4. Если снова не прошло (или повторяется та же ошибка) — Oracle.
5. Метрики пишутся в `PipelineMetrics` и в отчёт `run.py`.

**HumanEval:** отдельный режим (`--humaneval`), проверка через `humaneval_eval.py`. На Windows используется свой exec-checker (без `signal.setitimer`).

## Структура

```
stabilization_loop/
  config.py          — пороги, LLM-клиент, .env
  supervisor.py
  agents.py          — Base Model, AutoCrit, Attenuation, Oracle
  validation.py      — pytest, извлечение кода
  humaneval_eval.py  — проверка HumanEval
  reasoning.py       — очистка  тегов reasoning-моделей
  pipeline.py        — run_pipeline()
benchmarks/humaneval.py
tasks/registry.py    — 4 учебные задачи
tests/               — pytest по одному файлу на задачу
run.py
```

## Требования

- Python 3.10+
- Ключ к OpenAI-совместимому API

## Установка

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

HumanEval (опционально):

```bash
pip install -r requirements-benchmark.txt
```

## Настройка

```bash
copy .env.example .env
```

```env
LLM_API_KEY=ваш-ключ
LLM_BASE_URL=ваша ссылка
MODEL=модель
```

## Запуск

Одна задача из локального набора (1–4):

```bash
python run.py --task 1
```

Все 4 задачи:

```bash
python run.py --benchmark --save-report output/benchmark_report.json
```

HumanEval:

```bash
python run.py --humaneval --humaneval-limit 10
```

## Параметры в `config.py`

| Параметр | Значение | Используется |
|----------|----------|--------------|
| `WMAX_THRESHOLD` | 0.85 | Да — выбор Attenuation вместо AutoCrit |
| `MAX_STAB_CYCLES` | 3 | Да — лимит циклов стабилизации |
| `MIN_TOKEN_BUDGET` / `REASONING_MODEL_MIN_TOKEN_BUDGET` | 512 / 2048 | Да — защита от обрезки reasoning-моделей |
| `ES_STAB_TRIGGER`, `ES_ORACLE_TRIGGER` | 0.45 / 0.75 | Заданы в конфиге; эскалация сейчас идёт по результатам тестов, не по этим порогам |

## Зависимости

**`requirements.txt`** (обязательные):

- `openai` — вызов LLM
- `pytest` — проверка сгенерированного кода
- `python-dotenv` — загрузка `.env`

**`requirements-benchmark.txt`** (опционально):

- `human-eval` — датасет HumanEval

Остальное — стандартная библиотека Python.

## Программный вызов

```python
from stabilization_loop import run_pipeline
from tasks.registry import TASK_REGISTRY

result = run_pipeline(task_spec=TASK_REGISTRY[1])
print(result["success"], result["metrics"].summary())
```

## Анализ отчёта

```bash
python experiments/analyze_metrics.py output/benchmark_report.json
```
