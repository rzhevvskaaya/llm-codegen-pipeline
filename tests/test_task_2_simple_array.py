"""Tests for simple_array task."""


class TestTask2Primes:
    """simple_array(min, max) returns prime numbers in the inclusive range [min, max]."""

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
        fn = self._get_fn()
        assert fn(8, 10) == []

    def test_starts_from_two(self):
        fn = self._get_fn()
        assert fn(0, 2) == [2]

    def test_range_1_to_76(self):
        fn = self._get_fn()
        expected = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73]
        assert fn(1, 76) == expected

    def test_large_prime(self):
        fn = self._get_fn()
        assert fn(97, 97) == [97]

    def test_zero_and_one_not_prime(self):
        fn = self._get_fn()
        assert fn(0, 1) == []
