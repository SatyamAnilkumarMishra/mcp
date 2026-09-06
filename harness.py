
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

_HARNESS_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "llm_eval_harness",
)

if _HARNESS_ROOT not in sys.path:
    sys.path.insert(0, _HARNESS_ROOT)


try:
    from llm_eval_harness.config.settings import settings
    from llm_eval_harness.dataset.loader import DatasetLoader
    from llm_eval_harness.target.factory import get_model_target
    from llm_eval_harness.target.providers import GeminiTarget
    from llm_eval_harness.evaluators.exact_match import ExactMatchEvaluator
    from llm_eval_harness.evaluators.keyword_match import KeywordMatchEvaluator
    from llm_eval_harness.evaluators.rubric import RubricEvaluator
    from llm_eval_harness.evaluators.llm_judge import LLMJudgeEvaluator
    from llm_eval_harness.core.runner import EvaluationRunner
except ImportError:
    from config.settings import settings
    from dataset.loader import DatasetLoader
    from target.factory import get_model_target
    from target.providers import GeminiTarget
    from evaluators.exact_match import ExactMatchEvaluator
    from evaluators.keyword_match import KeywordMatchEvaluator
    from evaluators.rubric import RubricEvaluator
    from evaluators.llm_judge import LLMJudgeEvaluator
    from core.runner import EvaluationRunner


# ---------------------------------------------------------------------------
# MCP run tracking
# ---------------------------------------------------------------------------

_run_counter = itertools.count(1)

# run_id -> complete run record
_runs: dict = {}


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------

def _build_evaluators() -> dict:
    """
    Build the standard evaluator set.

    The LLM judge is registered only when a Gemini API key is available.
    """

    evals = {
        "exact_match": ExactMatchEvaluator(),

        "keyword_match": KeywordMatchEvaluator(
            keywords=[
                "correct",
                "answer",
                "yes",
                "no",
            ],
            match_all=False,
        ),

        "rubric": RubricEvaluator(
            criteria=[
                {
                    "name": "has_substance",
                    "weight": 1.0,
                    "check": lambda p, r: len(p.split()) >= 3,
                }
            ]
        ),
    }

    # Register the LLM judge only when Gemini is configured.
    if settings.gemini_api_key:
        judge_target = GeminiTarget(
            model_name=settings.gemini_judge_model,
            api_key=settings.gemini_api_key,
        )

        evals["llm_judge"] = LLMJudgeEvaluator(
            judge_target=judge_target,
            threshold=0.7,
        )

    return evals


# ---------------------------------------------------------------------------
# Dataset resolution
# ---------------------------------------------------------------------------

def _resolve_dataset_path(dataset: str) -> str:
    """
    Accept either:

        sample_eval.json

    or:

        dataset/sample_eval.json

    or an absolute/relative path that already exists.
    """

    # First check exactly what the caller supplied.
    if os.path.exists(dataset):
        return os.path.abspath(dataset)

    # Then check the harness dataset directory.
    candidate = os.path.join(
        _HARNESS_ROOT,
        "dataset",
        dataset,
    )

    if os.path.exists(candidate):
        return os.path.abspath(candidate)

    raise ValueError(
        f"Dataset not found: {dataset}"
    )


# ---------------------------------------------------------------------------
# Dataset listing
# ---------------------------------------------------------------------------

def list_datasets() -> list[dict]:
    """
    List JSON datasets available under:

        D:\\mcp\\llm_eval_harness\\dataset
    """

    dataset_dir = os.path.join(
        _HARNESS_ROOT,
        "dataset",
    )

    out = []

    for path in sorted(
        glob.glob(
            os.path.join(
                dataset_dir,
                "*.json",
            )
        )
    ):
        name = os.path.basename(path)

        try:
            samples = DatasetLoader.from_json(path)

            out.append(
                {
                    "dataset": name,
                    "num_samples": len(samples),
                }
            )

        except Exception as e:
            out.append(
                {
                    "dataset": name,
                    "error": str(e),
                }
            )

    return out


# ---------------------------------------------------------------------------
# Run evaluation
# ---------------------------------------------------------------------------

def run_eval(
    dataset: str,
    model: str,
    provider: str = "gemini",
    system_prompt: str | None = None,
    max_concurrent: int | None = None,
) -> dict:
    """
    Run an evaluation dataset against a model using the real evaluation
    pipeline:

        DatasetLoader
            ↓
        Model Target
            ↓
        EvaluationRunner
            ↓
        Evaluators
            ↓
        MetricsTracker
            ↓
        ResultRecorder

    Returns the MCP run_id and summary.

    Full per-sample results are retained in memory and can be retrieved
    using get_results(run_id, detail=True).
    """

    # Preserve the existing model aliases used by the project.
    if model in (
        "gemini-flash-latest",
        "gemini-flash",
        "gemini-2.5-flash",
    ):
        model = "gemini-3.6-flash"

    # Resolve dataset to an absolute path.
    dataset_path = _resolve_dataset_path(dataset)

    # Load evaluation samples.
    samples = DatasetLoader.from_json(
        dataset_path
    )

    # Create the model target.
    target = get_model_target(
        provider,
        model,
    )

    # Build evaluators.
    evaluators = _build_evaluators()

    # Use configured concurrency unless explicitly overridden.
    concurrency = (
        max_concurrent
        if max_concurrent is not None
        else settings.max_concurrent
    )

    # Run the evaluation.
    runner = EvaluationRunner(
        target,
        max_concurrent=concurrency,
    )

    try:
        results = asyncio.run(
            runner.run(
                samples,
                evaluators,
                system_prompt,
            )
        )

        # Generate MCP-level run ID.
        run_id = f"run-{next(_run_counter)}"

        # Generate metrics summary.
        summary = runner.metrics.summary()

        # Store complete run information in memory.
        _runs[run_id] = {
            "run_id": run_id,
            "dataset": os.path.basename(dataset_path),
            "provider": provider,
            "model": model,
            "timestamp": time.time(),
            "summary": summary,
            "results": results,
        }

        return {
            "run_id": run_id,
            "summary": summary,
        }

    finally:
        # Make sure the recorder's file handle is closed even if
        # evaluation fails partway through.
        try:
            runner.recorder.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Get results
# ---------------------------------------------------------------------------

def get_results(
    run_id: str,
    detail: bool = False,
) -> dict:
    """
    Retrieve results for a previously completed evaluation run.

    detail=False:
        Returns metadata + summary.

    detail=True:
        Also returns all per-sample results.
    """

    if run_id not in _runs:
        raise ValueError(
            f"Unknown run_id: {run_id}"
        )

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


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------

def list_run_history() -> list[dict]:
    """
    List all evaluation runs completed during the current
    MCP server session.
    """

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
