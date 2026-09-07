"""
Run the same dataset against multiple model/config combinations and
print a side-by-side summary.

BUILD THIS LAST — it's the payoff, not a new concept: it just loops the
same EvaluationRunner you already built once per config. This is also
where you'll actually *use* the harness for your RAG project — e.g.
compare "gpt-4o-mini" vs "gemini-1.5-flash" as your generator, or
compare two system prompts against the same retrieved contexts, and see
which one has a higher pass rate / lower latency.

NOTE ON main.py's --compare flag: as shipped, `main.py` only puts ONE
config into `compare_configs` (with a comment saying "add more here").
That's intentionally left as an exercise — to make comparison mode
actually useful, either hardcode a second config, or (better, as a
learning exercise) extend main.py to accept `--compare-config path.json`
and load a list of `{provider, model, name, system_prompt}` dicts from
a file instead of editing Python source each time.
"""

import asyncio
from typing import List, Dict, Any
from dataset.loader import DatasetLoader
from target.factory import get_model_target
from evaluators.base import BaseEvaluator
from core.runner import EvaluationRunner
from reports.reporter import Reporter


class ModelComparison:
    def __init__(self, dataset_path: str, evaluators: Dict[str, BaseEvaluator]):
        self.dataset = DatasetLoader.from_json(dataset_path)
        self.evaluators = evaluators
        self.reporter = Reporter()

    async def compare(self, configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        all_results = {}

        for cfg in configs:
            name = cfg.get("name", f"{cfg['provider']}_{cfg['model']}")
            print(f"\n>>> Running: {name}")

            target = get_model_target(
                cfg["provider"], cfg["model"], **cfg.get("kwargs", {})
            )
            # A fresh EvaluationRunner per config — each gets its own
            # metrics tracker and recorder, so results from different
            # models never bleed into each other's aggregates.
            runner = EvaluationRunner(
                target, max_concurrent=cfg.get("max_concurrent", 5)
            )

            results = await runner.run(
                self.dataset,
                self.evaluators,
                cfg.get("system_prompt"),
            )

            self.reporter.print_table(results, runner.metrics)

            all_results[name] = {
                "results": results,
                "metrics": runner.metrics.summary(),
            }

        print("\n" + "=" * 70)
        print(f"{'MODEL':<25} {'PASS RATE':<12} {'AVG SCORE':<12} {'AVG LATENCY':<12}")
        print("-" * 70)
        for name, data in all_results.items():
            m = data["metrics"]
            print(
                f"{name:<25} {m['pass_rate']:<12.2%} {m['avg_score']:<12.3f} {m['avg_latency_ms']:<12.1f}"
            )
        print("=" * 70)

        return all_results
