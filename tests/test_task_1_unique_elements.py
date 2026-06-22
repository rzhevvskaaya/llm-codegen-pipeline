"""Tests for unique_elements task."""


class TestTask1UniqueElements:
    """unique_elements(input_list) returns the unique values from a list."""

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
