"""
The simplest possible evaluator: string equality after normalization.

WHY START HERE: it has zero dependencies, zero network calls, and forces
you to think about normalization (case, whitespace) before you ever touch
an API. Every eval method downstream has this same "what counts as equal"
problem in a fuzzier form — exact_match just makes it explicit and cheap
to reason about.

WHEN TO USE IT: only when there's exactly one correct surface form of the
answer (e.g. "1889", "Guido van Rossum" if you're strict about it). It's
brittle for anything with paraphrase-able answers — that's what
keyword_match and llm_judge are for.
"""

from evaluators.base import BaseEvaluator, EvalResult


class ExactMatchEvaluator(BaseEvaluator):
    name = "exact_match"

    def __init__(self, case_sensitive: bool = False, strip: bool = True):
        self.case_sensitive = case_sensitive
        self.strip = strip

    def evaluate(self, prediction: str, reference: str, **kwargs) -> EvalResult:
        pred = prediction.strip() if self.strip else prediction
        ref = reference.strip() if self.strip else reference

        if not self.case_sensitive:
            pred = pred.lower()
            ref = ref.lower()

        passed = pred == ref
        return EvalResult(
            score=1.0 if passed else 0.0,
            passed=passed,
            reasoning="Exact match" if passed else f"Expected '{ref}', got '{pred}'",
        )
