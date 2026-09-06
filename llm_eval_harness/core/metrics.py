"""
Aggregates per-sample results into run-level metrics.

BUILD THIS LAST of the core/ files — it's the simplest, and it's much
easier to design once you already have real `result` dicts flowing out
of the runner to look at. Notice everything here is a `@property`
computed on demand from `self.results`, not maintained incrementally —
for eval-run sizes (dozens to low thousands of samples) that's simpler
and less bug-prone than incremental running averages, and correctness
matters more than micro-optimizing this.
"""

from typing import List, Dict, Any
from statistics import mean


class MetricsTracker:
    def __init__(self):
        self.results: List[Dict[str, Any]] = []

    def add(self, result: Dict[str, Any]):
        self.results.append(result)

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r["passed"]) / len(self.results)

    @property
    def avg_score(self) -> float:
        if not self.results:
            return 0.0
        return mean(r["score"] for r in self.results)

    @property
    def avg_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        return mean(r["latency_ms"] for r in self.results)

    @property
    def total_tokens(self) -> Dict[str, int]:
        # Guards against None usage (e.g. a provider that didn't report
        # token counts) rather than assuming every result has clean data —
        # worth defending against, since not every provider/response
        # shape guarantees usage metadata.
        prompt = 0
        completion = 0
        for r in self.results:
            usage = r.get("usage") or {}
            if usage and isinstance(usage, dict):
                pt = usage.get("prompt_tokens")
                ct = usage.get("completion_tokens")
                if pt is not None:
                    prompt += pt
                if ct is not None:
                    completion += ct
        return {"prompt": prompt, "completion": completion}

    def summary(self) -> Dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        return {
            "total_samples": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": self.pass_rate,
            "avg_score": self.avg_score,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "total_tokens": self.total_tokens,
        }
