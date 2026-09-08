"""
LLM-as-a-judge: use a model to grade another model's output.

WHY THIS EXISTS: exact_match and keyword_match can't judge semantic
correctness — "No, that's a common misconception; net oxygen production
is nearly zero" and "Yes the Amazon produces a lot of oxygen, it's often
called the lungs of the planet" share zero required keywords with a
correct reference but are opposite in meaning. Only something that can
*read* can tell them apart. That's what this evaluator buys you, at the
cost of being slower, non-deterministic, and dependent on the judge
model's own judgment.

THINGS TO LEARN / PITFALLS TO INTERNALIZE (this is the hardest evaluator
in the harness to get right — treat it as the deep-dive of your build):

1. Structured output beats free text. This prompt explicitly asks for
   JSON matching JudgeSchema, and forces `response_mime_type=json` /
   `response_schema=` on the API call. Without this, you're regex-parsing
   prose out of a judge's response, which breaks constantly and silently.

2. Explicit, decomposed criteria beat "is this good?". The prompt breaks
   the grade into accuracy/completeness/clarity with stated weights,
   rather than asking for one vague quality score. Vague judge prompts
   correlate poorly between runs of the *same* input.

3. Judges fail closed. If the API call throws or the JSON doesn't parse,
   this returns score=0.0 / passed=False rather than crashing the whole
   run or silently defaulting to a pass. Decide deliberately whether
   "fail closed" (assume broken = wrong) or "fail open" (assume broken =
   skip/retry) is right for your use case — this harness chose fail
   closed, which is usually the safer default for an eval suite.

4. Known failure modes worth researching as you build your own version:
   - Position/verbosity bias (judges tend to prefer longer answers)
   - Self-preference bias (a model judging its own family's outputs)
   - Judge inconsistency across repeated calls on the same input
   - Circularity: your "ground truth" is only as good as the judge model

5. threshold lives on the evaluator instance (see how RubricEvaluator was
   fixed to do the same) rather than being re-derived per call — the
   `passed` field returned by the judge model is a secondary check, but
   we don't blindly trust the judge's own math; we still gate on our
   own `score >= self.threshold` conceptually (worth adding as an
   exercise: right now `passed` trusts the judge's boolean if present —
   consider whether you'd rather always recompute it yourself from score).
"""

import json
from typing import Optional
from pydantic import BaseModel
from evaluators.base import BaseEvaluator, EvalResult
from target.providers import GeminiTarget
from google.genai import types


class JudgeSchema(BaseModel):
    score: float
    passed: bool
    reasoning: str


class LLMJudgeEvaluator(BaseEvaluator):
    name = "llm_judge"

    def __init__(self, judge_target: GeminiTarget, threshold: float = 0.7):
        self.judge = judge_target
        self.threshold = threshold

    def evaluate(self, prediction: str, reference: str, **kwargs) -> EvalResult:
        raise NotImplementedError(
        "LLMJudgeEvaluator is async-only — call aevaluate() instead."
    )

    async def aevaluate(self, prediction: str, reference: str, **kwargs) -> EvalResult:
        question = kwargs.get("question", "")

        prompt = f"""You are evaluating a RAG (Retrieval-Augmented Generation) system.

Question: {question}
Reference Answer: {reference}
Model Response: {prediction}

Evaluate the model response on:
1. Accuracy (0.6): Is the factual content correct relative to the reference?
2. Completeness (0.3): Are all key points from the reference present?
3. Clarity (0.1): Is the response well-structured and easy to understand?

Return a JSON object with:
- score: float between 0.0 and 1.0
- passed: boolean (true if score >= {self.threshold})
- reasoning: one-sentence explanation
"""

        try:
            response = await self.judge.generate(
                prompt=prompt,
                system_prompt="You are a fair, rigorous evaluator. Always respond with valid JSON.",
                response_mime_type="application/json",
                response_schema=JudgeSchema,
            )

            data = json.loads(response.text)
            score = float(data.get("score", 0.0))
            # We recompute `passed` from our own threshold rather than
            # trusting the judge's boolean verbatim — the judge is asked
            # to compute it too (so you can sanity-check for disagreement
            # in `reasoning`/logs), but our threshold is the source of
            # truth, not the model's arithmetic.
            passed = score >= self.threshold
            reasoning = data.get("reasoning", "")

        except Exception as e:
            # Fail closed: a broken judge call counts as a failed sample,
            # not a skipped one. See module docstring point 3.
            score = 0.0
            passed = False
            reasoning = f"Judge parse error: {e}"

        return EvalResult(score=score, passed=passed, reasoning=reasoning)
