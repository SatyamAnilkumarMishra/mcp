"""
Substring/regex presence check — a step up from exact_match.

WHY THIS EXISTS: real model outputs rarely match a reference verbatim.
"Guido van Rossum created it in 1991" should still pass against reference
"Guido van Rossum" — exact_match would fail that. keyword_match trades
precision for recall: it can't tell you if the answer is *correct*, only
whether certain expected tokens/phrases showed up.

LEARNING POINT: notice `match_all` — this is the first place the harness
distinguishes "contains at least one required thing" (OR semantics) from
"contains everything required" (AND semantics). Getting this distinction
right matters a lot once you're checking, say, a RAG answer for multiple
required facts vs. checking it avoids ANY of a list of banned phrases.
"""

import re
from typing import List, Union
from evaluators.base import BaseEvaluator, EvalResult


class KeywordMatchEvaluator(BaseEvaluator):
    name = "keyword_match"

    def __init__(
        self,
        keywords: Union[List[str], str],
        match_all: bool = False,
        use_regex: bool = False,
    ):
        if isinstance(keywords, str):
            self.keywords = [keywords]
        else:
            self.keywords = keywords
        self.match_all = match_all
        self.use_regex = use_regex

    def evaluate(self, prediction: str, reference: str, **kwargs) -> EvalResult:
        text = prediction
        matches = 0
        details = []

        for kw in self.keywords:
            if self.use_regex:
                found = bool(re.search(kw, text, re.IGNORECASE))
            else:
                found = kw.lower() in text.lower()

            if found:
                matches += 1
            details.append(f"{kw}: {'found' if found else 'missing'}")

        if self.match_all:
            passed = matches == len(self.keywords)
        else:
            passed = matches > 0

        # score is fraction of keywords found — even when match_all=True
        # and the sample technically fails, the score still tells you
        # "found 2 of 3", which is far more useful for debugging than a
        # flat 0.0.
        score = matches / len(self.keywords) if self.keywords else 0.0

        return EvalResult(
            score=score,
            passed=passed,
            reasoning="; ".join(details),
        )
