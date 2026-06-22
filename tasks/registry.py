"""Benchmark task registry for code generation experiments."""

from __future__ import annotations

from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent / "tests"

TASK_REGISTRY: dict[int, dict] = {
    1: {
        "task_id": 1,
        "name": "unique_elements",
        "expected_symbol": "unique_elements",
        "test_path": str(TESTS_DIR / "test_task_1_unique_elements.py"),
        "prompt": """
Implement a Python function named unique_elements(input_list).

The function receives a list and returns a list containing each unique value from the input.
The order of the returned values is not important for the tests.
For an empty input list, return an empty list.
Return raw Python code only.
""".strip(),
    },
    2: {
        "task_id": 2,
        "name": "simple_array",
        "expected_symbol": "simple_array",
        "test_path": str(TESTS_DIR / "test_task_2_simple_array.py"),
        "prompt": """
Implement a Python function named simple_array(min, max).

The function returns a list of all prime numbers in the inclusive range [min, max].
0 and 1 are not prime. If there are no primes in the range, return an empty list.
Return raw Python code only.
""".strip(),
    },
    3: {
        "task_id": 3,
        "name": "Point",
        "expected_symbol": "Point",
        "test_path": str(TESTS_DIR / "test_task_3_point.py"),
        "prompt": """
Implement a Python class named Point.

Requirements:
- The constructor receives x and y and stores them as public attributes self.x and self.y.
- get_coordinates() returns a tuple (x, y).
- set_coordinates(x, y) updates the coordinates.
- distance_to_another_point(other_point) returns the Euclidean distance to another Point.
Return raw Python code only.
""".strip(),
    },
    4: {
        "task_id": 4,
        "name": "sort_strings_by_length",
        "expected_symbol": "sort_strings_by_length",
        "test_path": str(TESTS_DIR / "test_task_4_sort_strings_by_length.py"),
        "prompt": """
Implement a Python function named sort_strings_by_length(input_list).

The function receives a list of strings and returns two values: sorted_asc and sorted_desc.
sorted_asc must contain the same strings sorted by length in ascending order.
sorted_desc must contain the same strings sorted by length in descending order.
Return raw Python code only.
""".strip(),
    },
}
