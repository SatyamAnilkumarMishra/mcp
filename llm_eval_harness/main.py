# Entry point / CLI wiring. BUILD THIS FILE LAST.
#
# It has almost no logic of its own — it parses args, assembles the
# pieces you already built (dataset, target, evaluators, runner,
# reporter) and calls them in order. If you find yourself writing real
# logic here, it probably belongs in one of the other modules instead.

import asyncio
import argparse
import json
from typing import Dict

from config.settings import settings
from dataset.loader import DatasetLoader
from target.factory import get_model_target
from evaluators.base import BaseEvaluator
from evaluators.exact_match import ExactMatchEvaluator
from evaluators.keyword_match import KeywordMatchEvaluator
from evaluators.rubric import RubricEvaluator
from evaluators.llm_judge import LLMJudgeEvaluator
from target.providers import GeminiTarget
from core.runner import EvaluationRunner
from reports.reporter import Reporter
from experiments.compare import ModelComparison


def build_evaluators() -> Dict[str, BaseEvaluator]:
    evals = {
        "exact_match": ExactMatchEvaluator(),
        "keyword_match": KeywordMatchEvaluator(
            keywords=["correct", "answer", "yes", "no"],
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

    # Only register LLM judge if Gemini key is available
    if settings.gemini_api_key:
        judge_target = GeminiTarget(
            model_name=settings.gemini_judge_model,
            api_key=settings.gemini_api_key,
        )
        evals["llm_judge"] = LLMJudgeEvaluator(
            judge_target=judge_target, threshold=0.7
        )

    return evals


async def main():
    parser = argparse.ArgumentParser(description="Custom LLM Eval Harness")
    parser.add_argument(
        "--dataset", default="dataset/sample_eval.json", help="Path to eval dataset"
    )
    parser.add_argument(
        "--provider",
        default="gemini",
        choices=["gemini", "openai", "openai-compatible"],
        help="API provider",
    )
    parser.add_argument("--model", required=False, help="Model name (required unless --compare)")
    parser.add_argument("--system-prompt", default=None, help="Optional system prompt")
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=settings.max_concurrent,
        help="Max concurrent API calls",
    )
    parser.add_argument(
        "--output-csv", default="report.csv", help="CSV report filename"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run comparison mode (requires editing compare configs in code)",
    )
