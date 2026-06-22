"""
Unit tests for pipeline internals (no LLM calls).

Run with:
    pytest tests/test_pipeline_internals.py -v
"""
import re
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline.code_tools import _parse_pytest_output, extract_code_block
from pipeline.llm import _clean_llm_json
from pipeline.models import PipelineMetrics, TestResult


# ── _clean_llm_json ───────────────────────────────────────────────────────────

class TestCleanLlmJson:
    def test_strips_closed_think_tag(self):
        raw = "<think>I need to think carefully.</think>\n{\"es_score\": 0.3}"
        assert _clean_llm_json(raw) == '{"es_score": 0.3}'

    def test_strips_multiline_think_tag(self):
        raw = "<think>\nline1\nline2\n</think>\n{\"a\": 1}"
        assert _clean_llm_json(raw) == '{"a": 1}'

    def test_strips_unclosed_think_tag(self):
        raw = "<think>\nThinking about the problem...\n"
        assert _clean_llm_json(raw) == ""

    def test_strips_markdown_fence(self):
        raw = "```json\n{\"a\": 1}\n```"
        assert _clean_llm_json(raw) == '{"a": 1}'

    def test_strips_python_fence(self):
        raw = "```python\nx = 1\n```"
        assert _clean_llm_json(raw) == "x = 1"

    def test_plain_json_unchanged(self):
        raw = '{"entropy_est": 0.5, "wmax_est": 0.4}'
        assert _clean_llm_json(raw) == raw

    def test_empty_input(self):
        assert _clean_llm_json("") == ""


# ── extract_code_block ────────────────────────────────────────────────────────

class TestExtractCodeBlock:
    def test_python_fence(self):
        text = "Here is the solution:\n```python\ndef foo(): pass\n```"
        assert extract_code_block(text) == "def foo(): pass"

    def test_generic_fence(self):
        text = "```\ndef bar(): return 1\n```"
        assert extract_code_block(text) == "def bar(): return 1"

    def test_no_fence_returns_full_text(self):
        text = "def baz(): pass"
        assert extract_code_block(text) == "def baz(): pass"

    def test_prefers_python_fence_over_generic(self):
        text = "```python\ndef good(): pass\n```\n```\ndef bad(): pass\n```"
        assert extract_code_block(text) == "def good(): pass"


# ── _parse_pytest_output ──────────────────────────────────────────────────────

class TestParsePytestOutput:
    def test_all_passed(self):
        output = "5 passed in 0.12s"
        tr = _parse_pytest_output(output, 0)
        assert tr.tests_passed == 5
        assert tr.tests_failed == 0
        assert tr.tests_error == 0

    def test_mixed_results(self):
        output = "3 passed, 2 failed, 1 error in 0.5s"
        tr = _parse_pytest_output(output, 1)
        assert tr.tests_passed == 3
        assert tr.tests_failed == 2
        assert tr.tests_error == 1

    def test_nonzero_returncode_with_no_summary(self):
        tr = _parse_pytest_output("ImportError: something", 1)
        assert tr.tests_error == 1


# ── PipelineMetrics.register_test_result ──────────────────────────────────────

class TestPipelineMetrics:
    def test_es_score_zero_when_all_pass(self):
        m = PipelineMetrics()
        tr = TestResult(tests_passed=5, tests_failed=0, tests_error=0, output="ok", returncode=0)
        m.register_test_result(tr)
        assert m.es_score == 0.0

    def test_es_score_high_when_all_fail(self):
        m = PipelineMetrics()
        tr = TestResult(tests_passed=0, tests_failed=5, tests_error=0, output="fail", returncode=1)
        m.register_test_result(tr)
        assert m.es_score > 0.4

    def test_repeat_penalty_applied(self):
        m = PipelineMetrics()
        same_output = "E  AssertionError: assert 1 == 2" * 20
        tr = TestResult(tests_passed=0, tests_failed=1, output=same_output, returncode=1)
        m.register_test_result(tr)
        score_after_first = m.es_score
        m.register_test_result(tr)
        assert m.es_score >= score_after_first

    def test_pass_rate(self):
        tr = TestResult(tests_passed=3, tests_failed=1)
        assert tr.pass_rate == pytest.approx(0.75)

    def test_pass_rate_zero_total(self):
        tr = TestResult()
        assert tr.pass_rate == 0.0
