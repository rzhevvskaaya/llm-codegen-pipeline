"""Tests for Point class task."""

import math


class TestTask3Point:
    """Point class with coordinates, getter/setter, and distance method."""

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
        P = self._get_cls()
        p1 = P(2, 3)
        p2 = P(-2, 10)
        expected = math.sqrt((2 - (-2)) ** 2 + (3 - 10) ** 2)
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
