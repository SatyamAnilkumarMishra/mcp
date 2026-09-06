# MCP LLM Evaluation Harness

A modular **LLM evaluation and benchmarking framework exposed through the Model Context Protocol (MCP)**.

This project allows AI assistants such as Claude Desktop to interact with an LLM evaluation system through MCP tools. It supports multiple LLM providers, automated evaluation strategies, experiment metrics, result persistence, run history, and model comparison.

The system is designed to make LLM evaluation **repeatable, measurable, and accessible through an AI-native tool interface**.

---

## 🚀 Overview

Evaluating an LLM application manually can quickly become difficult when multiple models, datasets, prompts, and evaluation criteria are involved.

This project provides an evaluation pipeline that can:

* Load structured evaluation datasets
* Execute prompts against different LLM providers
* Evaluate model responses using multiple evaluation strategies
* Track pass rates, scores, latency, and token usage
* Persist per-sample evaluation results
* Maintain evaluation run history
* Compare different models
* Expose the entire evaluation workflow through MCP
* Allow Claude Desktop to execute evaluations using natural-language tool calls
* Provide MCP Inspector support for direct testing and debugging

### High-Level Flow

```text
                    ┌──────────────────────┐
                    │     Claude Desktop   │
                    └──────────┬───────────┘
                               │
                               │ MCP
                               ▼
                    ┌──────────────────────┐
                    │      MCP Server      │
                    │     server.py        │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Evaluation        │
                    │     Harness         │
                    │     harness.py      │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
        ┌───────────┐   ┌────────────┐   ┌──────────────┐
        │  Dataset  │   │   Model    │   │ Evaluators   │
        │  Loader   │   │  Factory   │   │              │
        └───────────┘   └─────┬──────┘   └──────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
              ┌──────────┐        ┌──────────┐
              │  Gemini  │        │   Groq   │
              └──────────┘        └──────────┘
                    │                   │
                    └─────────┬─────────┘
                              ▼
                    ┌──────────────────────┐
                    │ Metrics + Recorder   │
                    └──────────────────────┘
```

---

# 🧠 Core Architecture

The project separates the evaluation system into independent components.

```text
MCP Layer
    ↓
MCP Server
    ↓
Evaluation Harness
    ↓
Model Factory
    ↓
Provider Abstraction
    ↓
LLM
    ↓
Evaluation
    ↓
Metrics
    ↓
Result Recording
```

This separation allows new models, providers, evaluators, and MCP capabilities to be added without tightly coupling the entire system.

---

# 🔌 MCP Integration

The project exposes the evaluation harness through **Model Context Protocol (MCP)**.

Instead of manually running Python commands for every evaluation, an MCP-compatible client such as Claude Desktop can discover and invoke the evaluation functionality as tools.

The MCP server currently exposes **four primary tools**:

1. `list_datasets`
2. `run_eval`
3. `get_results`
4. `list_run_history`

---

# 🛠️ The Four MCP Tools

## 1. `list_datasets`

### Purpose

Discovers all available evaluation datasets and reports the number of samples contained in each dataset.

### What it does

The server scans the evaluation dataset directory, loads each JSON dataset, and returns metadata about the available datasets.

### Example request

```text
Use the list_datasets tool and show me all available evaluation datasets with their sample counts.
```

### Example response

```text
sample_eval.json
Samples: 10
```

### Why it is useful

This provides dataset discovery directly through the MCP interface.

An AI assistant does not need to know the filesystem structure beforehand. It can first discover what evaluation datasets are available and then select one for evaluation.

---

# 2. `run_eval`

### Purpose

Executes an evaluation against a selected dataset and LLM.

This is the **main execution tool** of the system.

### Inputs

The tool accepts:

* `dataset`
* `model`
* `provider`
* `system_prompt`
* `max_concurrent`

### Example — Gemini

```text
Use the run_eval tool to evaluate sample_eval.json using the Gemini provider and the gemini-flash-latest model. Return the run_id and complete evaluation summary.
```

### Example — Groq

```text
Use the run_eval tool to evaluate sample_eval.json using the openai-compatible provider and the openai/gpt-oss-20b model. Return the run_id and complete evaluation summary.
```

### Internal execution flow

```text
Dataset
   ↓
DatasetLoader
   ↓
EvaluationRunner
   ↓
Model Target
   ↓
LLM API
   ↓
Generated Response
   ↓
Evaluator
   ↓
MetricsTracker
   ↓
ResultRecorder
   ↓
Run Summary
```

### Concurrency

The evaluation runner supports configurable concurrency using `max_concurrent`.

For example:

```text
max_concurrent = 1
```

runs requests sequentially.

```text
max_concurrent = 4
```

allows multiple samples to be evaluated concurrently.

This allows the evaluation system to balance execution speed against API rate limits and resource constraints.

---

# 3. `get_results`

### Purpose

Retrieves the results of a previously completed evaluation run.

Every evaluation run receives a unique `run_id`.

For example:

```text
run-1
run-2
run-3
```

### Basic result retrieval

The tool returns information such as:

* run ID
* dataset
* provider
* model
* evaluation summary

### Detailed result retrieval

The `detail` parameter can be enabled to retrieve per-sample evaluation results.

### Example

```text
Use the get_results tool for run-1 with detail=true and show me the complete per-sample evaluation results.
```

### Example flow

```text
run_eval
    ↓
run-1
    ↓
get_results(run-1)
    ↓
Dataset + Model + Summary + Per-sample Results
```

This makes individual evaluation experiments inspectable after execution.

---

# 4. `list_run_history`

### Purpose

Returns the evaluation runs completed during the current server session.

It provides a high-level view of previous experiments.

### Example

```text
Use the list_run_history tool and show me all evaluation runs completed in this server session, including the run_id, dataset, provider, model, and pass_rate.
```

### Example output

```text
run-1
Dataset: sample_eval.json
Provider: gemini
Model: gemini-3.6-flash
Pass Rate: 0.80

run-2
Dataset: sample_eval.json
Provider: openai-compatible
Model: openai/gpt-oss-20b
Pass Rate: 0.90
```

### Why it matters

Run history provides a simple experiment-tracking layer and makes it easier to identify and compare previous model evaluations.

---

# 📊 Evaluation System

The framework supports multiple evaluation strategies.

## Exact Match

Checks whether the generated response matches the expected answer according to the evaluator's exact-match logic.

Useful for deterministic tasks where the expected answer is known.

---

## Keyword Match

Checks whether required keywords are present in the generated response.

The current implementation supports configured keyword matching such as:

```text
correct
answer
yes
no
```

This is useful when multiple valid responses may exist but certain concepts or terms must appear.

---

## Rubric Evaluation

Evaluates responses against configurable criteria.

The current harness includes a basic substance criterion based on response length.

The rubric architecture is designed so additional criteria can be added later.

---

## LLM-as-a-Judge

Uses another LLM to evaluate the quality of a generated response.

The current implementation uses Gemini as the judge when a Gemini API key is configured.

This allows semantic evaluation where exact matching is insufficient.

---

# 📈 Metrics

The evaluation framework tracks several metrics.

### Pass Rate

Percentage of evaluation samples that pass their configured evaluator.

### Average Score

Average evaluation score across the run.

### Average Latency

Measures model response latency in milliseconds.

### Token Usage

Tracks prompt and completion token usage when provided by the model API.

These metrics make it possible to evaluate models based on more than just response correctness.

For example:

```text
             Gemini       Groq
----------------------------------
Pass Rate     82%         88%
Score         0.81        0.86
Latency       1.8s        0.9s
Tokens        1240        980
```

This enables practical model benchmarking across multiple dimensions.

---

# 🔄 Multi-Provider Model Architecture

The project uses a model factory and provider abstraction to avoid coupling the evaluation runner to a specific LLM provider.

Currently supported providers include:

### Gemini

Uses Google's Gemini API through the `google-genai` client.

### OpenAI-Compatible

Supports APIs that expose an OpenAI-compatible interface.

The project currently uses this interface for Groq.

For example:

```text
provider = openai-compatible
model = openai/gpt-oss-20b
```

The provider factory routes the request to the appropriate API configuration.

This architecture makes it easier to add additional providers in the future.

---

# 🔐 Provider Configuration

Provider credentials are loaded through environment variables.

Supported configuration includes:

```text
GEMINI_API_KEY
OPENAI_API_KEY
OPENAI_BASE_URL
GROQ_API_KEY
GROQ_BASE_URL
MAX_CONCURRENT
GEMINI_JUDGE_MODEL
```

Groq uses its OpenAI-compatible API endpoint.

API keys should never be committed to the repository.

---

# 🔁 Retry and Backoff

LLM APIs can fail because of transient network issues, rate limits, or temporary service errors.

The project includes a shared retry mechanism with exponential backoff.

The retry mechanism also attempts to detect server-provided retry delays such as:

```text
retry in 5s
```

When such a delay is available, the system uses the suggested delay plus a small buffer.

Otherwise, exponential backoff is used.

Conceptually:

```text
API Request
    ↓
Success ─────────────→ Continue
    │
    └── Failure
          ↓
      Retry Delay
          ↓
      Retry Request
          ↓
       Success
```

This improves resilience when interacting with external LLM APIs.

---

# 💾 Result Persistence

Evaluation results are persisted as JSONL files.

Each evaluation sample is recorded as an individual JSON object on its own line.

Example:

```text
reports/
└── results/
    ├── run_20260906_....jsonl
    ├── run_20260906_....jsonl
    └── ...
```

This provides a lightweight and machine-readable format for storing evaluation results.

---

# 🧪 Model Comparison

The project also includes a CLI-based comparison workflow.

The comparison system can evaluate multiple models against the same dataset and compare their performance.

For example:

```text
                    Dataset
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
          Gemini                Groq
             │                   │
             ▼                   ▼
        Evaluation           Evaluation
             │                   │
             └─────────┬─────────┘
                       ▼
                  Comparison
                       │
                       ▼
              Performance Metrics
```

The comparison can be executed from the evaluation harness CLI.

Example:

```text
cd D:\mcp\llm_eval_harness
C:\Python313\python.exe main.py --dataset dataset/sample_eval.json --compare
```

This allows models to be benchmarked using the same evaluation dataset and criteria.

---

# 🤖 Using Claude Desktop

The MCP server can be connected to Claude Desktop through its MCP configuration.

Example configuration:

```json
{
  "mcpServers": {
    "eval-harness": {
      "command": "C:\\Python313\\python.exe",
      "args": [
        "D:\\mcp\\server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "GEMINI_API_KEY": "YOUR_GEMINI_API_KEY",
        "GROQ_API_KEY": "YOUR_GROQ_API_KEY"
      }
    }
  }
}
```

API keys should be replaced locally and must **never be committed to GitHub**.

After restarting Claude Desktop, the `eval-harness` MCP server becomes available and its tools can be invoked through natural-language requests.

---

# 🔍 MCP Inspector

The project can also be tested independently of Claude Desktop using MCP Inspector.

Launch the Inspector with:

```text
npx @modelcontextprotocol/inspector C:\Python313\python.exe D:\mcp\server.py
```

MCP Inspector can be used to:

* Connect directly to the MCP server
* Inspect available tools
* Inspect tool schemas
* Execute MCP tools manually
* Debug tool calls
* Verify server behavior independently of Claude Desktop

This provides a useful development and debugging workflow:

```text
Development
     ↓
MCP Inspector
     ↓
Verify MCP Server
     ↓
Claude Desktop
     ↓
Real AI Assistant Integration
```

---

# 📁 Project Structure

```text
mcp/
│
├── server.py
│   └── MCP server and tool definitions
│
└── llm_eval_harness/
    │
    ├── main.py
    │   └── CLI and model comparison
    │
    ├── harness.py
    │   └── Evaluation orchestration
    │
    ├── config/
    │   └── settings.py
    │       └── Environment configuration
    │
    ├── dataset/
    │   ├── loader.py
    │   └── sample_eval.json
    │
    ├── target/
    │   ├── base.py
    │   ├── factory.py
    │   └── providers.py
    │
    ├── evaluators/
    │   ├── base.py
    │   ├── exact_match.py
    │   ├── keyword_match.py
    │   ├── rubric.py
    │   └── llm_judge.py
    │
    ├── core/
    │   ├── runner.py
    │   ├── metrics.py
    │   └── recorder.py
    │
    └── reports/
        └── results/
            └── *.jsonl
```

---

# 🧩 Component Responsibilities

| Component     | Responsibility                                               |
| ------------- | ------------------------------------------------------------ |
| `server.py`   | Exposes the evaluation system through MCP                    |
| `harness.py`  | Orchestrates dataset loading, model execution and evaluation |
| `main.py`     | CLI execution and model comparison                           |
| `dataset/`    | Dataset loading and evaluation samples                       |
| `target/`     | Model abstraction and provider implementations               |
| `evaluators/` | Response evaluation strategies                               |
| `runner.py`   | Asynchronous evaluation execution                            |
| `metrics.py`  | Tracks evaluation metrics                                    |
| `recorder.py` | Persists evaluation results                                  |
| `settings.py` | Environment and provider configuration                       |

---

# 🛠️ Installation

## Requirements

* Python 3.10+
* Node.js / npm
* Gemini API key
* Groq API key
* Claude Desktop (optional)
* MCP Inspector (optional)

## Install Python dependencies

From the project environment, install the required dependencies:

```text
pip install -r requirements.txt
```

Configure the required environment variables before running the system.

---

# ▶️ Running the MCP Server

The server is designed to communicate using MCP over STDIO.

Run:

```text
C:\Python313\python.exe D:\mcp\server.py
```

For normal usage, it can be launched automatically by Claude Desktop.

---

# 🧪 Example Evaluation Workflow

A typical workflow looks like this:

### Step 1 — Discover datasets

```text
list_datasets
```

### Step 2 — Run Gemini evaluation

```text
run_eval
provider: gemini
model: gemini-flash-latest
dataset: sample_eval.json
```

### Step 3 — Run Groq evaluation

```text
run_eval
provider: openai-compatible
model: openai/gpt-oss-20b
dataset: sample_eval.json
```

### Step 4 — Retrieve detailed results

```text
get_results
run_id: run-1
detail: true
```

### Step 5 — Inspect previous runs

```text
list_run_history
```

### Step 6 — Compare models

```text
main.py --compare
```

---

# 🎯 Design Goals

The project was built around several principles:

### Modularity

Providers, evaluators, datasets, and metrics are separated into independent modules.

### Provider Agnosticism

The evaluation runner does not need to know the implementation details of individual LLM providers.

### Reproducibility

The same dataset and evaluation criteria can be executed against different models.

### Observability

Latency, token usage, scores, and pass rates are captured for each evaluation run.

### Extensibility

New providers and evaluation strategies can be added without redesigning the entire system.

### AI-Native Interaction

MCP allows an AI assistant to interact with the evaluation framework as a set of tools rather than requiring direct CLI interaction.

---

# 🚧 Future Improvements

Planned improvements include:

* Asynchronous/background evaluation jobs
* Persistent experiment database
* Improved evaluation dashboards
* More sophisticated RAG-specific evaluation
* Additional LLM providers
* More advanced LLM-as-a-judge strategies
* Evaluation result visualization
* Docker containerization
* CI/CD integration
* Automated evaluation pipelines
* Production deployment
* Guardrails and safety evaluation
* Improved observability and monitoring
* Kubernetes-based deployment

---

# 💡 Why This Project?

LLM applications need more than a working model call.

A production-oriented AI system needs to answer questions such as:

* Is the model producing correct answers?
* Which model performs better?
* How consistent are the results?
* How much does each request cost in tokens?
* How fast is the model?
* Does a prompt change improve performance?
* Can evaluations be reproduced?
* Can the evaluation process itself be automated?

This project provides the foundation for answering those questions through a reusable evaluation and benchmarking system.

---

# 📌 Key Technologies

* **Python**
* **Model Context Protocol (MCP)**
* **Claude Desktop**
* **MCP Inspector**
* **Google Gemini**
* **Groq**
* **OpenAI-compatible APIs**
* **AsyncIO**
* **Pydantic**
* **JSONL**
* **LLM Evaluation**
* **LLM-as-a-Judge**
* **Model Benchmarking**

---

# 👨‍💻 Project Objective

The goal of this project is to build a reusable **LLM evaluation infrastructure layer** rather than a single-purpose model application.

By combining:

**MCP + LLM Providers + Evaluation Strategies + Metrics + Experiment Tracking**

the system provides an extensible foundation for evaluating and benchmarking modern LLM applications.

---

## ⭐ Summary

```text
             MCP Evaluation Harness
                       │
          ┌────────────┼────────────┐
          │            │            │
       Dataset       Models      Evaluators
          │            │            │
          │       ┌────┴────┐       │
          │       │         │       │
          │    Gemini      Groq     │
          │       │         │       │
          └───────┼─────────┼───────┘
                  │
              Evaluation
                  │
             ┌────┴────┐
             │         │
          Metrics    Results
             │         │
             └────┬────┘
                  │
             MCP Interface
                  │
                  ▼
            Claude Desktop
```

**The project turns LLM evaluation into a reusable, measurable, and AI-accessible workflow through MCP.**
