# Custom LLM Eval Harness

A vanilla-Python, async LLM evaluation harness supporting multiple providers
(Gemini, OpenAI-compatible endpoints like Groq/OpenAI) and multiple scoring
strategies (exact match, keyword match, rubric-based, LLM-as-judge), with
rate-limit-aware retry logic and crash-safe incremental result persistence.

## Features

- **Provider-agnostic targets** — swap between Gemini, OpenAI, or any
  OpenAI-compatible endpoint (Groq, local models via Ollama, etc.) behind a
  single `BaseTarget` interface.
- **Multiple evaluation strategies** — exact match, keyword match, weighted
  rubric scoring, and LLM-as-judge, all behind a shared `BaseEvaluator`
  interface.
- **Async, concurrency-controlled execution** — `asyncio.Semaphore`-gated
  runner so you control exactly how many requests are in flight at once.
- **Rate-limit-aware retries** — parses a provider's own suggested
  retry-after delay (e.g. Gemini's `"Please retry in 12.3s"`) instead of
  relying on generic exponential backoff alone.
- **Crash-safe result persistence** — results are written to disk
  incrementally (append + line-buffered), so an interrupted run still leaves
  completed results on disk instead of losing everything.
- **Multi-model comparison mode** — run the same dataset against N different
  provider/model configs in one command and get a side-by-side summary.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API keys
cp .env.example .env
```

Edit `.env`:

```dotenv
GEMINI_API_KEY=your_gemini_key
GEMINI_JUDGE_MODEL=gemini-flash-latest   # model used by the LLM-judge evaluator

GROQ_API_KEY=your_groq_key
GROQ_BASE_URL=https://api.groq.com/openai/v1

OPENAI_API_KEY=your_openai_key
OPENAI_BASE_URL=https://api.openai.com/v1

MAX_CONCURRENT=1
```

> **Model names change.** Providers deprecate and gate models regularly.
> Before running, confirm what your key can actually access rather than
> trusting a hardcoded string anywhere (including in this README):
>
> ```bash
> python list_models.py
> ```
>
> This prints every model your Gemini key currently has `generateContent`
> access to. Use one of those names for `--model` / `GEMINI_JUDGE_MODEL`.

## Running an evaluation

```bash
python main.py --provider <PROVIDER> --model <MODEL_NAME> --dataset <DATASET_PATH>
```

Examples:

```bash
python main.py --provider gemini --model gemini-flash-latest --dataset dataset/sample_eval.json
python main.py --provider openai-compatible --model openai/gpt-oss-20b --dataset dataset/sample_eval.json
```

`<PROVIDER>` is one of `gemini`, `openai`, `openai-compatible`.

## Comparing multiple models

```bash
python main.py --compare --dataset <DATASET_PATH>
```

Runs the same dataset against every config in `compare_configs` (defined in
`main.py`), each with its own provider/model/API key, and prints a
side-by-side table (pass rate, avg score, avg latency) at the end.

To add a new comparison target, add another entry to `compare_configs` in
`main.py`, e.g.:

```python
{
    "provider": "openai-compatible",
    "model": "openai/gpt-oss-20b",
    "name": "groq_gpt_oss_20b",
    "system_prompt": args.system_prompt,
    "kwargs": {"api_key": settings.groq_api_key, "base_url": settings.groq_base_url},
    "max_concurrent": 1,
},
```

## Dataset format

Each dataset is a JSON list of samples matching the `EvalSample` schema:

```json
{
  "id": "tc_001",
  "question": "What is the capital of France? Return ONLY the city name.",
  "expected_answer": "Paris",
  "evaluator": "exact_match",
  "metadata": { "system_prompt": "You are a concise factual assistant." }
}
```

- `evaluator` must be one of: `exact_match`, `keyword_match`, `rubric`,
  `llm_judge`.
- Use `exact_match` for short, deterministic answers. Use `llm_judge` for
  open-ended answers (explanations, code, multi-paragraph responses) where
  exact string matching would almost never pass a correct answer.
- `metadata` is a free-form dict — useful for storing extra context (e.g.
  per-sample `system_prompt`, difficulty tier) that the current schema
  doesn't have a first-class field for.

## Project structure

| File | Purpose |
|---|---|
| `main.py` | CLI entry point; wires up evaluators, target, and runs single or comparison mode |
| `config/settings.py` | Loads all API keys/config from `.env` |
| `target/base.py` | `BaseTarget` interface + `TargetResponse` shape |
| `target/providers.py` | `GeminiTarget`, `OpenAICompatibleTarget`, retry logic |
| `target/factory.py` | Builds a concrete target from a provider string |
| `dataset/loader.py` | `EvalSample` schema + JSON dataset loading |
| `evaluators/base.py` | `BaseEvaluator` interface + `EvalResult` shape |
| `evaluators/llm_judge.py` | LLM-as-judge evaluator |
| `core/runner.py` | Async, concurrency-controlled evaluation runner |
| `core/recorder.py` | Crash-safe incremental result persistence |
| `reports/reporter.py` | Terminal table + CSV report output |
| `experiments/compare.py` | Multi-config comparison runner |
| `list_models.py` | Diagnostic script — lists models your API key can access |

## Known limitations

- **Latency.** Free-tier provider rate limits (e.g. a handful of requests
  per minute, or a low daily cap) mean larger datasets, and datasets with
  many `llm_judge` samples (two API calls per sample instead of one), can
  take a long time to complete end-to-end. `MAX_CONCURRENT` and per-provider
  quotas are the main levers for run time — plan for longer runs on free
  tiers, or reduce dataset size for fast iteration.


