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


def run_eval(dataset: str, model: str, provider: str = "gemini",
             system_prompt: str | None = None, max_concurrent: int | None = None) -> dict:
    """Run an eval dataset against a model using the real harness pipeline
    (DatasetLoader -> target -> EvaluationRunner -> evaluators -> metrics).
    Returns a run_id plus the summary; full per-sample results are stored
    and retrievable via get_results(run_id, detail=True)."""
    dataset_path = _resolve_dataset_path(dataset)
    samples = DatasetLoader.from_json(dataset_path)

    target = get_model_target(provider, model)
    evaluators = _build_evaluators()
    concurrency = max_concurrent or settings.max_concurrent
    runner = EvaluationRunner(target, max_concurrent=concurrency)

    results = asyncio.run(runner.run(samples, evaluators, system_prompt))

    run_id = f"run-{next(_run_counter)}"
    summary = runner.metrics.summary()
    _runs[run_id] = {
        "run_id": run_id,
        "dataset": os.path.basename(dataset_path),
        "provider": provider,
        "model": model,
        "timestamp": time.time(),
        "summary": summary,
        "results": results,
    }
    return {"run_id": run_id, "summary": summary}


def get_results(run_id: str, detail: bool = False) -> dict:
    """Retrieve results for a previously completed eval run. Pass
    detail=True to include full per-sample predictions/scores/reasoning."""
    if run_id not in _runs:
        raise ValueError(f"Unknown run_id: {run_id}")
    run = _runs[run_id]
    out = {
        "run_id": run_id,
        "dataset": run["dataset"],
        "provider": run["provider"],
        "model": run["model"],
        "summary": run["summary"],
    }
    if detail:
        out["results"] = run["results"]
    return out


def list_run_history() -> list[dict]:
    """List all eval runs completed so far in this server session."""
    return [
        {
            "run_id": r["run_id"],
            "dataset": r["dataset"],
            "provider": r["provider"],
            "model": r["model"],
            "pass_rate": r["summary"]["pass_rate"],
        }
        for r in _runs.values()
    ]

