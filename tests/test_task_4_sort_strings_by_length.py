"""Tests for sort_strings_by_length task."""


class TestTask4SortByLength:
    """sort_strings_by_length(input_list) returns (sorted_asc, sorted_desc)."""

    def _get_fn(self):
        from solution import sort_strings_by_length  # type: ignore

        return sort_strings_by_length

    def test_basic_example_from_readme(self):
        fn = self._get_fn()
        inp = ["cat", "turtle", "hamster", "fish", "chinchilla"]
        asc, desc = fn(inp.copy())
        assert [len(s) for s in asc] == sorted([len(s) for s in asc])
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
        assert asc[0] == "fig"
        assert asc[-1] == "apple"
        assert desc[0] == "apple"
        assert desc[-1] == "fig"
