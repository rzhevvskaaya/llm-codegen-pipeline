#!/usr/bin/env python3
"""
Runner: прогоняет tasks.json через stabilization pipeline.

Использование:
    python run_custom_tasks.py --tasks benchmarks/tasks.json
    python run_custom_tasks.py --tasks benchmarks/tasks.json --task-id T001
    python run_custom_tasks.py --tasks benchmarks/tasks.json --save-report report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def extract_symbol(original_code: str) -> tuple[str | None, str]:
    """Возвращает (имя, тип) — 'func' или 'class'."""
    class_match = re.search(r'^class (\w+)', original_code, re.MULTILINE)
    if class_match:
        return class_match.group(1), 'class'
    func_match = re.search(r'^def (\w+)', original_code, re.MULTILINE)
    if func_match:
        return func_match.group(1), 'func'
    return None, 'unknown'


def build_test_file(task: dict, output_dir: Path) -> Path:
    """Генерирует pytest файл и conftest.py, возвращает путь к тесту."""
    original_code = task['original_code']
    symbol_name, symbol_type = extract_symbol(original_code)

    # conftest.py — добавляет output/ в sys.path чтобы pytest нашёл solution.py
    conftest = output_dir / 'conftest.py'
    conftest.write_text(
        f"import sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0, str(Path(__file__).parent))\n",
        encoding='utf-8'
    )

    lines = [
        'import sys',
        'from pathlib import Path',
        'sys.path.insert(0, str(Path(__file__).parent))',
        '',
    ]

    # Импорт нужного символа
    if symbol_name:
        lines.append(f'from solution import {symbol_name}')
        lines.append('')

    # Генерируем тест-функции
    for test_group in task.get('tests', []):
        test_name = test_group['name']
        # Убеждаемся что имя начинается с test_
        if not test_name.startswith('test_'):
            test_name = 'test_' + test_name
        lines.append(f'def {test_name}():')

        assertions = test_group['assertions']
        if not assertions:
            lines.append('    pass')
        else:
            for assertion in assertions:
                code = assertion['code'].strip()
                for line in code.splitlines():
                    lines.append(f'    {line}')
        lines.append('')

    test_code = '\n'.join(lines)
    test_file = output_dir / f'test_{task["instance_id"]}.py'
    test_file.write_text(test_code, encoding='utf-8')
    return test_file


def build_task_spec(task: dict, output_dir: Path) -> dict:
    """Конвертирует запись из tasks.json в task_spec для run_pipeline."""
    original_code = task['original_code']
    symbol_name, symbol_type = extract_symbol(original_code)
    test_file = build_test_file(task, output_dir)

    prompt = (
        f"{task['problem_statement']}\n\n"
        f"Fix the following Python code so all tests pass:\n\n"
        f"```python\n{original_code}\n```\n\n"
        f"Return ONLY the complete fixed {'class' if symbol_type == 'class' else 'function'}. "
        f"No explanation, no markdown, just raw Python code."
    )

    return {
        'prompt': prompt,
        'test_path': str(test_file),
        'expected_symbol': symbol_name,
        'name': task['instance_id'],
        'difficulty': task.get('difficulty', 'unknown'),
    }


def run_tasks(tasks_path: str, task_id: str | None, save_report: str | None) -> int:
    global PROJECT_ROOT

    tasks = json.loads(Path(tasks_path).read_text(encoding='utf-8'))
    print(f'Загружено задач: {len(tasks)}')

    if task_id:
        tasks = [t for t in tasks if t['instance_id'] == task_id]
        if not tasks:
            print(f'Задача {task_id} не найдена')
            return 1

    try:
        from stabilization_loop.pipeline import run_pipeline
    except ImportError as e:
        print(f'Не удалось импортировать pipeline: {e}')
        print(f'PROJECT_ROOT: {PROJECT_ROOT}')
        return 1

    output_dir = PROJECT_ROOT / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    solution_path = str(output_dir / 'solution.py')

    report: list[dict] = []

    for task in tasks:
        instance_id = task['instance_id']
        difficulty = task.get('difficulty', '?')
        print(f"\n{'='*60}")
        print(f'TASK: {instance_id}  [{difficulty}]')
        print(f"{'='*60}")
        print(f"Problem: {task['problem_statement'][:100]}...")

        task_spec = build_task_spec(task, output_dir)
        t0 = time.time()

        try:
            result = run_pipeline(
                task_spec=task_spec,
                solution_path=solution_path,
                use_context=False,
            )
            elapsed = time.time() - t0

            report.append({
                'instance_id': instance_id,
                'difficulty': difficulty,
                'success': result['success'],
                'failure_type': result['failure_type'],
                'agents_used': len(result['results']),
                'stab_cycles': result['metrics'].stab_cycles,
                'escalated': result['metrics'].escalated,
                'total_tokens': result['total_tokens'],
                'elapsed_sec': round(elapsed, 2),
            })

            status = '✓ PASS' if result['success'] else '✗ FAIL'
            print(f'\n{status} | tokens={result["total_tokens"]} | time={elapsed:.1f}s')
            if not result['success']:
                print(f'Failure: {result["failure_type"]}')

        except Exception as e:
            elapsed = time.time() - t0
            print(f'\n✗ ERROR: {e}')
            report.append({
                'instance_id': instance_id,
                'difficulty': difficulty,
                'success': False,
                'failure_type': f'EXCEPTION: {e}',
                'agents_used': 0,
                'stab_cycles': 0,
                'escalated': False,
                'total_tokens': 0,
                'elapsed_sec': round(elapsed, 2),
            })

    # Итоговый отчёт
    print(f"\n\n{'='*60}")
    print('ИТОГОВЫЙ ОТЧЁТ')
    print(f"{'='*60}")
    header = (
        f"{'ID':<8} "
        f"{'Diff':<8} "
        f"{'Result':<8} "
        f"{'Agents':>6} "
        f"{'Stab':>5} "
        f"{'Oracle':>7} "
        f"{'Tokens':>8} "
        f"{'Time':>7}"
    )
    print(header)
    print('-' * len(header))
    for row in report:
        status = 'PASS' if row['success'] else 'FAIL'
        oracle = 'yes' if row['escalated'] else 'no'

        print(
            f"{row['instance_id']:<8} "
            f"{row['difficulty']:<8} "
            f"{status:<8} "
            f"{row['agents_used']:>6} "
            f"{row['stab_cycles']:>5} "
            f"{oracle:>7} "
            f"{row['total_tokens']:>8} "
            f"{row['elapsed_sec']:>6.1f}s"
        )

    passed = sum(1 for r in report if r['success'])
    print(f'\nРезультат: {passed}/{len(report)} прошло')
    avg_tokens = (
        sum(r['total_tokens'] for r in report) / len(report)
        if report else 0
    )

    avg_time = (
        sum(r['elapsed_sec'] for r in report) / len(report)
        if report else 0
    )

    avg_agents = (
        sum(r['agents_used'] for r in report) / len(report)
        if report else 0
    )

    oracle_count = sum(
        1 for r in report
        if r['escalated']
    )

    total_stab = sum(
        r['stab_cycles']
        for r in report
    )

    print('\nСТАТИСТИКА')
    print('-' * 40)
    print(f'Средние токены : {avg_tokens:.0f}')
    print(f'Среднее время  : {avg_time:.1f}s')
    print(f'Средние агенты : {avg_agents:.2f}')
    print(f'Всего stab     : {total_stab}')
    print(f'Oracle used    : {oracle_count}/{len(report)}')
    for diff in ['easy', 'medium', 'hard']:
        subset = [r for r in report if r['difficulty'] == diff]
        if subset:
            p = sum(1 for r in subset if r['success'])
            print(f'  {diff}: {p}/{len(subset)}')

    if save_report:
        Path(save_report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8'
        )
        print(f'\nОтчёт сохранён: {save_report}')

    return 0 if passed == len(report) else 1


def main() -> int:
    global PROJECT_ROOT
    parser = argparse.ArgumentParser(description='Run tasks.json through stabilization pipeline')
    parser.add_argument('--tasks', default='tasks.json', help='Path to tasks.json')
    parser.add_argument('--task-id', default=None, help='Run only this task (e.g. T001)')
    parser.add_argument('--save-report', default='', help='Save report to JSON file')
    parser.add_argument('--project-root', default=str(PROJECT_ROOT),
                        help='Path to project root')
    args = parser.parse_args()

    PROJECT_ROOT = Path(args.project_root)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    return run_tasks(args.tasks, args.task_id, args.save_report or None)


if __name__ == '__main__':
    raise SystemExit(main())
