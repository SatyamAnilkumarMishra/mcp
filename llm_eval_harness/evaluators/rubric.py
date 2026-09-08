"""
Weighted multi-criterion scoring.

WHY THIS EXISTS: most real answers aren't right-or-wrong on one axis —
they need to be *correct*, *complete*, and *well-formed*, and those can
trade off against each other. A rubric lets you say "correctness matters
3x more than formatting" and get a single blended score back.

Each criterion is just a `(prediction, reference) -> bool` function —
same shape as an evaluator's core job, just narrower. This is a good
place to notice the recursive pattern: a rubric is basically several
tiny evaluators combined by weighted average.

FIXED BUG (from the original version of this file): `threshold` used to
be read from `kwargs` inside `evaluate()`, but the runner never actually
passes a `threshold` kwarg when it calls an evaluator — so it silently
always fell back to the hardcoded default (0.8), no matter what you
configured. The fix: `threshold` is now a constructor argument, set once
when you build the evaluator, same pattern as LLMJudgeEvaluator. This is
a good general lesson — config that's meant to be set once per evaluator
instance belongs in `__init__`, not smuggled through per-call kwargs that
nothing upstream is guaranteed to populate.
"""

from typing import List, Dict, Any, Callable
from evaluators.base import BaseEvaluator, EvalResult


class RubricEvaluator(BaseEvaluator):
    name = "rubric"

    def __init__(self, criteria: List[Dict[str, Any]], threshold: float = 0.8):
        """
        criteria: list of dicts like
            {"name": "has_substance", "weight": 1.0, "check": lambda p, r: ...}
        threshold: minimum weighted score (0.0-1.0) to count as passed.
        """
        self.criteria = criteria
        self.threshold = threshold

    def evaluate(self, prediction: str, reference: str, **kwargs) -> EvalResult:
        total_score = 0.0
        total_weight = 0.0
        details = []

        for crit in self.criteria:
            name = crit["name"]
            weight = crit.get("weight", 1.0)
            check: Callable[[str, str], bool] = crit["check"]

            passed = check(prediction, reference)
            score = 1.0 if passed else 0.0
            total_score += score * weight
            total_weight += weight
            details.append(f"{name}: {score} (weight {weight})")

        final_score = total_score / total_weight if total_weight > 0 else 0.0

        return EvalResult(
            score=final_score,
            passed=final_score >= self.threshold,
            reasoning="; ".join(details),
        )
