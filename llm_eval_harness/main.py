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

    args = parser.parse_args()
    evaluators = build_evaluators()

    if args.compare:
        compare_configs = [
            {
                "provider": "gemini",
                "model": "gemini-flash-latest",
                "name": "gemini_flash_latest",
                "system_prompt": args.system_prompt,
                "kwargs": {"api_key": settings.gemini_api_key},
                "max_concurrent": 1,
            },
            {
                "provider": "openai-compatible",
                "model": "openai/gpt-oss-20b",
                "name": "groq_gpt_oss_20b",
                "system_prompt": args.system_prompt,
                "kwargs": {"api_key": settings.groq_api_key, "base_url": settings.groq_base_url},
                "max_concurrent": 1,
                
            },
            # Add more models here manually or load from a JSON config
        ]
        comp = ModelComparison(args.dataset, evaluators)
        await comp.compare(compare_configs)
        return

    dataset = DatasetLoader.from_json(args.dataset)
    target = get_model_target(args.provider, args.model)
    runner = EvaluationRunner(target, max_concurrent=args.max_concurrent)

    results = await runner.run(dataset, evaluators, args.system_prompt)

    reporter = Reporter()
    reporter.print_table(results, runner.metrics)

    csv_path = reporter.to_csv(results, args.output_csv)
    jsonl_path = runner.recorder.flush()

    print(f"CSV Report: {csv_path}")
    print(f"JSONL Raw:  {jsonl_path}")
    print(f"Summary:\n{json.dumps(runner.metrics.summary(), indent=2)}")


if __name__ == "__main__":
    asyncio.run(main())
