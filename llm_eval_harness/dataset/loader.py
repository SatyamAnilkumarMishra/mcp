"""
Dataset schema + loading.

BUILD THIS THIRD (after evaluators and target work standalone) — you
need somewhere for real questions/answers to live before the runner can
do anything useful. Pydantic validation here is doing real work: a
malformed dataset (missing `question`, wrong types) fails loudly at load
time with a clear error, instead of blowing up 40 samples into a run
with a confusing KeyError.

`evaluator: str = "exact_match"` is worth noticing: it's a per-sample
field, not a per-run setting. That's what lets one dataset file mix
strict exact-match questions with fuzzy LLM-judged ones (see
dataset/sample_eval.json) — the dataset itself declares how each of its
own questions should be graded.
"""

import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EvalSample(BaseModel):
    id: str
    context: Optional[str] = None
    question: str
    expected_answer: str
    evaluator: str = "exact_match"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DatasetLoader:
    @staticmethod
    def from_json(path: str) -> List[EvalSample]:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Accept either a bare list of samples, or {"samples": [...]}
        # so a dataset file can carry top-level metadata (name, version,
        # description) alongside the samples without breaking the loader.
        if isinstance(raw, dict) and "samples" in raw:
            raw = raw["samples"]
        return [EvalSample(**item) for item in raw]

    @staticmethod
    def from_jsonl(path: str) -> List[EvalSample]:
        """JSONL variant — one JSON object per line. Useful for large
        datasets you're streaming/appending to over time, where a single
        giant JSON array file would be awkward to append to."""
        samples = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    samples.append(EvalSample(**json.loads(line)))
        return samples
