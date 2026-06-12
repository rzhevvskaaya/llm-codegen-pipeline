# llm-codegen-pipeline

Мультиагентный пайплайн: LLM генерирует Python-код, запускает pytest, итеративно исправляет ошибки до прохождения всех тестов или исчерпания бюджета стабилизации.

## Как это работает

```
Задача
 └─▶ Supervisor Agent              — профилирует задачу, вычисляет ES score
 └─▶ Context Agent                 — сканирует кодовую базу, инжектирует контекст
 └─▶ Base Model                    — генерирует код → записывает файл → запускает тесты
 └─▶ [цикл] AutoCrit / Attenuation — исправляет ошибки, тестирует заново
 └─▶ Oracle Agent     — финальная эскалация после повторных сбоев
```

**ES score** (Escalation Score) пересчитывается после каждого прогона тестов из трёх компонент: доля упавших тестов, штраф за отсутствие тестов, штраф за повторяющиеся ошибки.

## Быстрый старт

```bash
# 1. Клонировать
git clone https://github.com/your-org/llm-codegen-pipeline.git
cd llm-codegen-pipeline

# 2. Создать виртуальное окружение и установить зависимости
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 3. Настроить переменные окружения
cp .env.example .env
# Открыть .env в редакторе и заполнить три переменные

# 4. Запустить пример
python scripts/run_example.py

# 5. Запустить со своей задачей и тестами
python -m pipeline.cli \
    --task "Напиши функцию unique_elements(lst) которая убирает дубликаты" \
    --test-path tests/test_tasks.py \
    --solution-path /tmp/solution.py
```

## Настройка секретов

Создайте файл `.env` в корне проекта (он добавлен в `.gitignore` и никогда не попадёт в репозиторий):

```bash
cp .env.example .env
```

Откройте `.env` и заполните три строки:

```env
LLM_API_KEY=sk-ваш-ключ
LLM_BASE_URL=https://api.duckduck.cloud/v1
LLM_MODEL=iairlab/qwen3-32b-reasoning-cache
```

Все три переменные обязательны — пайплайн не запустится без них и сразу сообщит что именно не задано.

## Структура проекта

```
llm-codegen-pipeline/
├── src/pipeline/
│   ├── __init__.py      # публичное API: run_pipeline()
│   ├── config.py        # настройки из переменных окружения
│   ├── models.py        # TestResult, PipelineMetrics, AgentResult
│   ├── llm.py           # call_model(), _clean_llm_json()
│   ├── code_tools.py    # extract_code_block(), write_code_to_file(), run_tests()
│   ├── agents.py        # все 6 агентов
│   ├── pipeline.py      # оркестратор run_pipeline()
│   └── cli.py           # точка входа python -m pipeline.cli
├── tests/
│   ├── conftest.py                  # настройка pytest
│   ├── test_pipeline_internals.py   # юнит-тесты (без LLM)
│   └── test_tasks.py                # тест-сьют для задач из репозитория
├── scripts/
│   └── run_example.py   # пример запуска
├── .env.example         # шаблон переменных (без реальных значений)
├── .gitignore
├── pyproject.toml
└── requirements.txt
```

## Запуск тестов

```bash
# Юнит-тесты — не требуют LLM и API ключа
pytest tests/test_pipeline_internals.py -v

# Полный набор
pytest -v
```

## Использование из Python

```python
from dotenv import load_dotenv
load_dotenv()  # читает .env

from pipeline import run_pipeline

result = run_pipeline(
    task="Напиши функцию two_sum(nums, target)...",
    solution_path="/tmp/solution.py",
    test_path="tests/test_tasks.py",
    project_dir="путь/к/кодовой/базе",   # опционально
)

print(result["final_code"])
print(result["test_result"].summary())
```

## Пороги пайплайна

| Параметр | По умолчанию | Описание |
|---|---|---|
| `ES_STAB_TRIGGER` | 0.45 | ES score выше которого запускается стабилизация |
| `ES_ORACLE_TRIGGER` | 0.75 | ES score выше которого вызывается Oracle |
| `MAX_STAB_CYCLES` | 3 | Максимум итераций AutoCrit / Attenuation |
| `WMAX_THRESHOLD` | 0.85 | Wmax выше которого Attenuation заменяет AutoCrit |

## Совместимые провайдеры

Работает любой OpenAI-совместимый API: OpenAI, Azure OpenAI, Together AI, LiteLLM, vLLM, Ollama, DuckDuck Cloud и другие. Нужно только задать `LLM_BASE_URL` и `LLM_MODEL`.

> **Reasoning-модели** (qwen3, deepseek-r1) выводят `<think>...</think>` блоки перед JSON-ответом. Пайплайн автоматически их вырезает через `_clean_llm_json()`.

## Лицензия

MIT
