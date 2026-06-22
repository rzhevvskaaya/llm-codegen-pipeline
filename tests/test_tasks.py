"""
Тест-файл для проверки решений из репозитория rzhevvskaaya/test_python.

Как использовать:
  - LLM генерирует код в /tmp/solution.py
  - run_tests("/tmp/solution.py", "test_tasks.py") запускает pytest
  - В solution.py должна быть одна из функций/классов ниже

Пайплайн определяет нужный тест по TASK_ID (1..4).
Чтобы тестировать конкретную задачу — раскомментируй нужный import.
"""

import sys
import os
import math
import pytest

# Добавляем /tmp в путь, чтобы импортировать сгенерированный файл
sys.path.insert(0, "/tmp")
sys.path.insert(0, os.path.dirname(__file__))

# ─────────────────────────────────────────────────────────────────────────────
# TASK 1 — unique_elements(input_list) → список уникальных элементов
# ─────────────────────────────────────────────────────────────────────────────

class TestTask1UniqueElements:
    """Функция принимает список и возвращает только уникальные элементы."""

    def _get_fn(self):
        from solution import unique_elements  # type: ignore
        return unique_elements

    def test_basic_duplicates(self):
        fn = self._get_fn()
        result = fn([1, 2, 3, 1, 2])
        assert sorted(result) == [1, 2, 3]

    def test_no_duplicates(self):
        fn = self._get_fn()
        result = fn([4, 5, 6])
        assert sorted(result) == [4, 5, 6]

    def test_all_same(self):
        fn = self._get_fn()
        result = fn([7, 7, 7, 7])
        assert sorted(result) == [7]

    def test_empty_list(self):
        fn = self._get_fn()
        assert fn([]) == []

    def test_single_element(self):
        fn = self._get_fn()
        assert fn([42]) == [42]

    def test_preserves_all_unique_values(self):
        fn = self._get_fn()
        original = [1, 2, 3, 5, 1, 4, 2, 4, 5, 1, 6, 7, 7]
        result = fn(original)
        assert sorted(result) == [1, 2, 3, 4, 5, 6, 7]

    def test_length_correct(self):
        fn = self._get_fn()
        result = fn([10, 10, 20, 30, 30, 30])
        assert len(result) == 3

    def test_negative_numbers(self):
        fn = self._get_fn()
        result = fn([-1, -2, -1, 0])
        assert sorted(result) == [-2, -1, 0]


# ─────────────────────────────────────────────────────────────────────────────
# TASK 2 — simple_array(min, max) → список простых чисел в диапазоне [min, max]
# ─────────────────────────────────────────────────────────────────────────────

class TestTask2Primes:
    """Функция возвращает список простых чисел в диапазоне [min, max] включительно."""

    def _get_fn(self):
        from solution import simple_array  # type: ignore
        return simple_array

    def test_basic_range(self):
        fn = self._get_fn()
        assert fn(1, 10) == [2, 3, 5, 7]

    def test_single_prime(self):
        fn = self._get_fn()
        assert fn(7, 7) == [7]

    def test_single_non_prime(self):
        fn = self._get_fn()
        assert fn(4, 4) == []

    def test_no_primes_in_range(self):
        # 8=2³, 9=3², 10=2·5 → не простые
        fn = self._get_fn()
        assert fn(8, 10) == []

    def test_starts_from_two(self):
        fn = self._get_fn()
        result = fn(0, 2)
        assert result == [2]

    def test_range_1_to_76(self):
        """Проверяем точный список из README-примера."""
        fn = self._get_fn()
        expected = [2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73]
        assert fn(1, 76) == expected

    def test_large_prime(self):
        fn = self._get_fn()
        assert fn(97, 97) == [97]

    def test_zero_and_one_not_prime(self):
        fn = self._get_fn()
        assert fn(0, 1) == []


# ─────────────────────────────────────────────────────────────────────────────
# TASK 3 — class Point(x, y) с методами distance_to_another_point, get/set_coordinates
# ─────────────────────────────────────────────────────────────────────────────

class TestTask3Point:
    """Класс Point с координатами и методами расстояния / геттеров / сеттеров."""

    def _get_cls(self):
        from solution import Point  # type: ignore
        return Point

    def test_init(self):
        P = self._get_cls()
        p = P(3, 4)
        assert p.x == 3
        assert p.y == 4

    def test_get_coordinates(self):
        P = self._get_cls()
        p = P(1, 2)
        assert p.get_coordinates() == (1, 2)

    def test_set_coordinates(self):
        P = self._get_cls()
        p = P(0, 0)
        p.set_coordinates(5, -3)
        assert p.get_coordinates() == (5, -3)

    def test_distance_to_origin(self):
        P = self._get_cls()
        p = P(3, 4)
        origin = P(0, 0)
        assert math.isclose(p.distance_to_another_point(origin), 5.0)

    def test_distance_example_from_readme(self):
        """point1=(2,3), point2=(-2,10) → sqrt(16+49)=sqrt(65)≈8.062"""
        P = self._get_cls()
        p1 = P(2, 3)
        p2 = P(-2, 10)
        expected = math.sqrt((2 - (-2))**2 + (3 - 10)**2)
        assert math.isclose(p1.distance_to_another_point(p2), expected, rel_tol=1e-9)

    def test_distance_symmetry(self):
        P = self._get_cls()
        p1 = P(1, 1)
        p2 = P(4, 5)
        assert math.isclose(
            p1.distance_to_another_point(p2),
            p2.distance_to_another_point(p1),
        )

    def test_distance_same_point(self):
        P = self._get_cls()
        p = P(7, 7)
        assert p.distance_to_another_point(P(7, 7)) == 0.0

    def test_set_then_get(self):
        P = self._get_cls()
        p = P(0, 0)
        p.set_coordinates(1, 9)
        assert p.get_coordinates() == (1, 9)


# ─────────────────────────────────────────────────────────────────────────────
# TASK 4 — sort_strings_by_length(input_list) → (sorted_asc, sorted_desc)
# ─────────────────────────────────────────────────────────────────────────────

class TestTask4SortByLength:
    """
    Функция принимает список строк и возвращает кортеж (asc, desc),
    отсортированных по длине строки.
    """

    def _get_fn(self):
        from solution import sort_strings_by_length  # type: ignore
        return sort_strings_by_length

    def test_basic_example_from_readme(self):
        fn = self._get_fn()
        inp = ["cat", "turtle", "hamster", "fish", "chinchilla"]
        asc, desc = fn(inp.copy())
        assert [len(s) for s in asc]  == sorted([len(s) for s in asc])
        assert [len(s) for s in desc] == sorted([len(s) for s in desc], reverse=True)

    def test_asc_order(self):
        fn = self._get_fn()
        asc, _ = fn(["banana", "kiwi", "fig", "mango"])
        lengths = [len(s) for s in asc]
        assert lengths == sorted(lengths)

    def test_desc_order(self):
        fn = self._get_fn()
        _, desc = fn(["banana", "kiwi", "fig", "mango"])
        lengths = [len(s) for s in desc]
        assert lengths == sorted(lengths, reverse=True)

    def test_asc_contains_all_words(self):
        fn = self._get_fn()
        words = ["cat", "turtle", "hamster", "fish", "chinchilla"]
        asc, _ = fn(words.copy())
        assert sorted(asc) == sorted(words)

    def test_desc_contains_all_words(self):
        fn = self._get_fn()
        words = ["cat", "turtle", "hamster", "fish", "chinchilla"]
        _, desc = fn(words.copy())
        assert sorted(desc) == sorted(words)

    def test_single_element(self):
        fn = self._get_fn()
        asc, desc = fn(["hello"])
        assert asc == ["hello"]
        assert desc == ["hello"]

    def test_all_same_length(self):
        fn = self._get_fn()
        words = ["cat", "dog", "fox"]
        asc, desc = fn(words.copy())
        assert len(asc) == 3
        assert len(desc) == 3

    def test_returns_tuple_or_two_values(self):
        fn = self._get_fn()
        result = fn(["a", "bb", "ccc"])
        assert len(result) == 2

    def test_does_not_mix_asc_and_desc(self):
        fn = self._get_fn()
        asc, desc = fn(["apple", "kiwi", "fig"])
        # asc: fig(3) < kiwi(4) < apple(5)
        assert asc[0] == "fig"
        assert asc[-1] == "apple"
        # desc: apple(5) > kiwi(4) > fig(3)
        assert desc[0] == "apple"
        assert desc[-1] == "fig"


# ─────────────────────────────────────────────────────────────────────────────
# Запуск напрямую: python test_tasks.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
