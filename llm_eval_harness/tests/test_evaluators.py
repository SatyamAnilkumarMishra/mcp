import pytest
from evaluators.exact_match import ExactMatchEvaluator
from evaluators.keyword_match import KeywordMatchEvaluator
from evaluators.rubric import RubricEvaluator


def test_exact_match_pass():
    em = ExactMatchEvaluator()
    r = em.evaluate("Paris", "Paris")
    assert r.passed is True
    assert r.score == 1.0


def test_exact_match_fail():
    em = ExactMatchEvaluator()
    r = em.evaluate("Paris", "London")
    assert r.passed is False
    assert r.score == 0.0


def test_exact_match_case_insensitive():
    em = ExactMatchEvaluator(case_sensitive=False)
    r = em.evaluate("paris", "Paris")
    assert r.passed is True


def test_keyword_match_any():
    km = KeywordMatchEvaluator(["Python", "Java"], match_all=False)
    r = km.evaluate("I love Python", "ref")
    assert r.passed is True
    assert r.score == 0.5
