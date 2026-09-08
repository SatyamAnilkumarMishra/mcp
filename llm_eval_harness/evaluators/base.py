"""
Core evaluator abstraction.

THE BIG IDEA: every evaluation method — no matter how different it looks
(string comparison, keyword search, an LLM grading another LLM) — reduces
to the same shape:

    (prediction, reference) -> EvalResult(score, passed, reasoning)

That's the interface worth internalizing. If you build this file first
and get this abstraction right, every evaluator you add later (including
ones you invent yourself) just plugs in.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from pydantic import BaseModel


class EvalResult(BaseModel):
    """
    Standardized output of any evaluator.

    score:    a continuous number (usually 0.0-1.0). Even "binary" checks
              like exact_match report a score so you can average across
              a whole run and see *how* wrong things were, not just
              pass/fail counts.
    passed:   the thresholded, binary decision derived from score. Keeping
              this separate from score is deliberate: it lets you change
              a pass/fail threshold later without re-running the eval.
    reasoning: human-readable explanation. Non-negotiable for LLM judges
              (otherwise you can't debug *why* a judge scored something
              low) but useful even for exact_match ("expected X, got Y").
    metadata: escape hatch for anything evaluator-specific you want to
              carry through to the report (e.g. per-criterion breakdown).
    """

    score: float
    passed: bool
    metadata: Dict[str, Any] = {}
    reasoning: str = ""


class BaseEvaluator(ABC):
    """
    Every evaluator subclasses this and implements `evaluate()`.

    Design note: `evaluate()` is sync and `aevaluate()` is async. Most
    evaluators (exact_match, keyword_match, rubric) are pure string
    comparisons — no I/O, no reason to be async. But LLM-as-judge *does*
    need to make a network call, so it overrides `aevaluate()` directly.

    The default `aevaluate()` just calls the sync `evaluate()` — so the
    runner can always `await evaluator.aevaluate(...)` uniformly, whether
    or not a given evaluator is actually async under the hood. This is a
    useful pattern any time you're mixing sync and async implementations
    behind one interface.
    """

    name: str = "base"

    @abstractmethod
    def evaluate(self, prediction: str, reference: str, **kwargs) -> EvalResult:
        """Synchronous scoring. Required for every evaluator."""
        pass

    async def aevaluate(self, prediction: str, reference: str, **kwargs) -> EvalResult:
        """Async wrapper. Override this (not evaluate()) if you need I/O,
        like LLMJudgeEvaluator does."""
        return self.evaluate(prediction, reference, **kwargs)
