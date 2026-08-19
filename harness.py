"""
Adapter between the MCP server and the real llm_eval_harness codebase
(in ./llm_eval_harness/). This module imports the actual harness classes
directly - DatasetLoader, get_model_target, EvaluationRunner, evaluators,
MetricsTracker - and exposes plain sync functions the MCP server's tool
handlers can call.

The harness itself is async (EvaluationRunner.run is a coroutine); since
the MCP server processes one stdio request at a time, each function here
just wraps the async call with asyncio.run().
"""

import sys
import os
import glob
import time
import asyncio
import itertools

_HARNESS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_eval_harness")
if _HARNESS_ROOT not in sys.path:
    sys.path.insert(0, _HARNESS_ROOT)

from config.settings import settings
from dataset.loader import DatasetLoader
from target.factory import get_model_target
from target.providers import GeminiTarget
from evaluators.exact_match import ExactMatchEvaluator
from evaluators.keyword_match import KeywordMatchEvaluator
from evaluators.rubric import RubricEvaluator
from evaluators.llm_judge import LLMJudgeEvaluator
from core.runner import EvaluationRunner

_run_counter = itertools.count(1)
_runs: dict[str, dict] = {}  # run_id -> full run record (summary + per-sample results)


def _build_evaluators() -> dict:
    """Mirrors main.py's build_evaluators(): register the standard
    evaluators, and only register llm_judge if a Gemini key is configured."""
    evals = {
        "exact_match": ExactMatchEvaluator(),
        "keyword_match": KeywordMatchEvaluator(
            keywords=["correct", "answer", "yes", "no"], match_all=False
        ),
        "rubric": RubricEvaluator(
            criteria=[{
                "name": "has_substance",
                "weight": 1.0,
                "check": lambda p, r: len(p.split()) >= 3,
            }]
        ),
    }
    if settings.gemini_api_key:
        judge_target = GeminiTarget(
            model_name=settings.gemini_judge_model, api_key=settings.gemini_api_key
        )
        evals["llm_judge"] = LLMJudgeEvaluator(judge_target=judge_target, threshold=0.7)
    return evals


def _resolve_dataset_path(dataset: str) -> str:
    """Accept either a bare filename ('sample_eval.json') relative to the
    harness's own dataset/ dir, or a full/relative path as-is."""
    if os.path.exists(dataset):
        return dataset
    candidate = os.path.join(_HARNESS_ROOT, "dataset", dataset)
    if os.path.exists(candidate):
        return candidate
    raise ValueError(f"Dataset not found: {dataset}")


def list_datasets() -> list[dict]:
    """List dataset JSON files available under the harness's dataset/ dir,
    with sample counts."""
    dataset_dir = os.path.join(_HARNESS_ROOT, "dataset")
    out = []
    for path in sorted(glob.glob(os.path.join(dataset_dir, "*.json"))):
        name = os.path.basename(path)
        try:
            samples = DatasetLoader.from_json(path)
            out.append({"dataset": name, "num_samples": len(samples)})
        except Exception as e:
            out.append({"dataset": name, "error": str(e)})
    return out
