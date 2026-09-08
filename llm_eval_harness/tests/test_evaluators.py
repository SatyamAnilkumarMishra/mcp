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

def test_keyword_match_all_pass():
    km = KeywordMatchEvaluator(["Python", "Java"], match_all=True)
    r = km.evaluate("I use Python and Java daily", "ref")
    assert r.passed is True
    assert r.score == 1.0


def test_keyword_match_all_fail():
    km = KeywordMatchEvaluator(["Python", "Java"], match_all=True)
    r = km.evaluate("I use Python only", "ref")
    assert r.passed is False


def test_rubric_evaluator():
    rubric = RubricEvaluator(
        [
            {
                "name": "has_number",
                "weight": 1.0,
                "check": lambda p, r: any(c.isdigit() for c in p),
            }
        ]
    )
    r = rubric.evaluate("The answer is 42", "42")
    assert r.passed is True
    assert r.score == 1.0

    r2 = rubric.evaluate("No numbers here", "42")
    assert r2.passed is False
    assert r2.score == 0.0

