# System Architecture

This document describes the internal architecture, execution flow, component responsibilities, and design decisions of the MCP LLM Evaluation Harness.

---

# 1. High-Level Architecture

The system consists of two primary layers:

1. **MCP Interface Layer**
2. **LLM Evaluation Harness**

The MCP layer exposes the evaluation capabilities to MCP-compatible clients such as Claude Desktop.

```text
                    ┌──────────────────────┐
                    │    Claude Desktop    │
                    └──────────┬───────────┘
                               │
                               │ MCP / STDIO
                               ▼
                    ┌──────────────────────┐
                    │      server.py       │
                    │      MCP Server      │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │      harness.py      │
                    │ Evaluation Orchestrator
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
       ┌────────────┐   ┌──────────────┐  ┌────────────┐
       │  Dataset   │   │ Model Factory│  │ Evaluators │
       │   Loader   │   │              │  │            │
       └────────────┘   └──────┬───────┘  └────────────┘
                               │
                     ┌─────────┴─────────┐
                     │                   │
                     ▼                   ▼
                ┌──────────┐       ┌──────────┐
                │  Gemini  │       │   Groq   │
                └──────────┘       └──────────┘
                     │                   │
                     └─────────┬─────────┘
                               ▼
                    ┌──────────────────────┐
                    │   Metrics Tracker   │
                    │   Result Recorder    │
                    └──────────────────────┘
```

---

# 2. Request Flow

A typical MCP evaluation request follows this path:

```text
Claude Desktop
      │
      │ Tool Call
      ▼
server.py
      │
      ▼
harness.run_eval()
      │
      ├── Resolve Dataset
      │
      ├── Load Samples
      │
      ├── Create Model Target
      │
      ├── Build Evaluators
      │
      └── Start EvaluationRunner
                  │
                  ▼
             Model API
                  │
                  ▼
             Prediction
                  │
                  ▼
              Evaluator
                  │
          ┌───────┴────────┐
          ▼                ▼
       Metrics          Recorder
          │                │
          └───────┬────────┘
                  ▼
             Run Summary
                  │
                  ▼
             MCP Response
```

---

# 3. MCP Server

`server.py` is the entry point for MCP communication.

It implements the MCP server interface and exposes evaluation functionality as tools.

The server is intentionally kept separate from the evaluation logic.

```text
MCP Protocol
     ↓
server.py
     ↓
harness.py
     ↓
Evaluation Framework
```

This separation means the underlying evaluation framework can be used independently from MCP.

---

# 4. MCP Tools

The server exposes four primary tools.

---

## 4.1 `list_datasets`

### Responsibility

Discovers available JSON evaluation datasets.

### Flow

```text
list_datasets
      ↓
Dataset Directory
      ↓
Find *.json
      ↓
DatasetLoader
      ↓
Count Samples
      ↓
Return Dataset Metadata
```

### Output

Each dataset provides metadata such as:

* Dataset name
* Number of samples
* Loading errors when applicable

### Design Purpose

The tool allows an MCP client to discover evaluation resources dynamically rather than requiring dataset names to be hard-coded into the client.

---

## 4.2 `run_eval`

### Responsibility

Runs a complete evaluation against a selected dataset and model.

### Inputs

```text
dataset
model
provider
system_prompt
max_concurrent
```

### Execution

```text
run_eval
   │
   ▼
Resolve Dataset
   │
   ▼
Load Eval Samples
   │
   ▼
Create Model Target
   │
   ▼
Create Evaluators
   │
   ▼
EvaluationRunner
   │
   ├── Sample 1 → Model → Evaluator
   ├── Sample 2 → Model → Evaluator
   ├── Sample 3 → Model → Evaluator
   └── ...
   │
   ▼
MetricsTracker
   │
   ▼
ResultRecorder
   │
   ▼
Generate Run ID
   │
   ▼
Return Summary
```

### Run Identification

Each completed evaluation receives a run ID such as:

```text
run-1
run-2
run-3
```

The run ID can later be passed to `get_results`.

---

## 4.3 `get_results`

### Responsibility

Retrieves information from a completed evaluation run.

### Flow

```text
run_id
   ↓
Run Registry
   ↓
Locate Run
   ↓
Return Summary
   │
   └── detail=true
          ↓
      Per-Sample Results
```

The normal response contains run metadata and summary metrics.

When `detail=true`, the individual evaluation results are also returned.

---

## 4.4 `list_run_history`

### Responsibility

Provides a high-level view of evaluation runs completed during the current server session.

### Flow

```text
list_run_history
       ↓
Run Registry
       ↓
Iterate Completed Runs
       ↓
Return:
  - run_id
  - dataset
  - provider
  - model
  - pass_rate
```

This creates a lightweight experiment history layer.

---

# 5. Evaluation Harness

The evaluation harness is responsible for orchestrating the complete evaluation lifecycle.

The primary orchestration flow is:

```text
Dataset
   ↓
Evaluation Samples
   ↓
Model Target
   ↓
Model Generation
   ↓
Evaluator
   ↓
Metrics
   ↓
Result Recording
```

The MCP layer does not implement these operations itself. It delegates them to the harness.

---

# 6. Dataset Layer

Evaluation datasets are stored as JSON files.

The dataset loader converts JSON data into evaluation samples.

Conceptually:

```text
JSON Dataset
     ↓
DatasetLoader
     ↓
EvalSample
     ↓
EvaluationRunner
```

An evaluation sample contains information such as:

* Question
* Expected answer
* Optional context
* Evaluator configuration

---

# 7. Prompt Construction

The evaluation runner constructs prompts from each evaluation sample.

When context exists:

```text
Use the following context to answer the question.

Context:
<retrieved/provided context>

Question:
<question>

Answer:
```

Without context:

```text
Question:
<question>

Answer:
```

A system prompt can additionally be supplied to the model.

---

# 8. Model Abstraction

The project separates model execution from evaluation logic through a target abstraction.

```text
BaseTarget
    │
    ├── GeminiTarget
    │
    └── OpenAICompatibleTarget
```

The evaluation runner interacts with the target through a common interface rather than directly calling provider-specific APIs.

This makes provider integration modular.

---

# 9. Model Factory

`target/factory.py` determines which target implementation should be created.

```text
Provider
   │
   ├── gemini
   │      ↓
   │  GeminiTarget
   │
   ├── openai-compatible
   │      ↓
   │  OpenAICompatibleTarget
   │      ↓
   │     Groq
   │
   └── openai
          ↓
      OpenAICompatibleTarget
```

This provider routing allows the same evaluation runner to work with different LLM APIs.

---

# 10. Provider Implementations

## Gemini

The Gemini target uses Google's GenAI client.

```text
GeminiTarget
     ↓
Google GenAI API
     ↓
Gemini Model
     ↓
TargetResponse
```

---

## Groq

Groq is accessed through its OpenAI-compatible API.

```text
OpenAICompatibleTarget
       ↓
OpenAI-compatible client
       ↓
Groq API
       ↓
GPT Model
       ↓
TargetResponse
```

The provider factory routes:

```text
provider = "openai-compatible"
```

to Groq-specific configuration:

```text
GROQ_API_KEY
GROQ_BASE_URL
```

This allows Groq models to be used without implementing a completely separate client abstraction.

---

# 11. Evaluation Layer

The framework separates evaluation logic from model generation.

The model produces a prediction:

```text
Question
   ↓
LLM
   ↓
Prediction
```

The evaluator then analyzes:

```text
Prediction
    +
Reference Answer
    +
Question / Context
        ↓
     Evaluator
        ↓
 Evaluation Result
```

This separation makes evaluators interchangeable.

---

# 12. Evaluator Types

## Exact Match

Used when the expected output is deterministic.

```text
Prediction
     │
     ▼
Compare with Reference
     │
     ▼
Pass / Fail
```

---

## Keyword Match

Checks whether configured keywords appear in the response.

This is useful when multiple valid answers can exist but specific concepts must be present.

---

## Rubric

Evaluates the response against configurable criteria.

The current implementation includes a basic substance criterion and provides an architecture that can be extended with additional criteria.

---

## LLM-as-a-Judge

Uses another LLM to evaluate the generated response.

```text
Generated Response
       │
       ▼
Judge Model
       │
       ▼
Evaluation Score
       │
       ▼
Pass / Fail
```

The current harness uses Gemini as the judge when the Gemini API key is configured.

This is particularly useful for semantic evaluation where exact string matching is insufficient.

---

# 13. Evaluation Runner

`core/runner.py` coordinates sample-level evaluation.

For every sample:

```text
Sample
  ↓
Build Prompt
  ↓
Generate Response
  ↓
Select Evaluator
  ↓
Evaluate Response
  ↓
Create Result
  ↓
Update Metrics
  ↓
Record Result
```

The runner uses asynchronous execution.

---

# 14. Concurrency

The runner supports configurable concurrency using an asynchronous semaphore.

Conceptually:

```text
max_concurrent = 1

Sample 1 → Model → Evaluation
Sample 2 → Model → Evaluation
Sample 3 → Model → Evaluation
```

With:

```text
max_concurrent = 4
```

multiple samples can execute concurrently:

```text
Sample 1 ──→ Model
Sample 2 ──→ Model
Sample 3 ──→ Model
Sample 4 ──→ Model
```

Concurrency can improve throughput, but excessive concurrency can increase API rate-limit errors and resource pressure.

For debugging or rate-limited environments, a lower concurrency value is safer.

---

# 15. Retry and Backoff

The provider layer includes shared retry handling.

The retry mechanism:

1. Executes the API request.
2. Catches exceptions.
3. Checks whether the error provides a retry delay.
4. Uses the server-provided delay when available.
5. Otherwise uses exponential backoff.
6. Retries until the maximum retry count is reached.

Conceptually:

```text
API Request
     │
     ├── Success ──────────→ Continue
     │
     └── Failure
           │
           ▼
      Retry Delay
           │
           ▼
        Retry
           │
           ├── Success
           │
           └── Failure → Retry
```

This improves resilience against transient failures and rate limits.

---

# 16. Metrics

`core/metrics.py` tracks evaluation-level statistics.

Important metrics include:

### Pass Rate

Percentage of samples that passed evaluation.

### Average Score

Mean evaluation score across samples.

### Average Latency

Average model response latency in milliseconds.

### Token Usage

Tracks prompt and completion token usage when provided by the provider.

---

# 17. Result Recording

`core/recorder.py` persists per-sample evaluation results.

Results are stored as JSONL:

```text
reports/
└── results/
    ├── run_<timestamp>.jsonl
    ├── run_<timestamp>.jsonl
    └── ...
```

Each line represents one evaluation result.

This provides a lightweight and machine-readable persistence format.

---

# 18. Run Lifecycle

A complete run follows:

```text
RUN START
    ↓
Load Dataset
    ↓
Initialize Model
    ↓
Initialize Evaluators
    ↓
Execute Samples
    ↓
Evaluate Predictions
    ↓
Track Metrics
    ↓
Record Results
    ↓
Generate Run ID
    ↓
Store Run Metadata
    ↓
RUN COMPLETE
```

The in-memory run registry allows MCP tools to retrieve results during the server session.

---

# 19. Model Comparison

The project provides a CLI comparison workflow.

The same dataset can be evaluated against multiple models:

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
          ┌─────────┼─────────┐
          ▼         ▼         ▼
       Accuracy   Latency   Tokens
```

The comparison process helps answer questions such as:

* Which model has the highest pass rate?
* Which model has the highest average score?
* Which model is fastest?
* Which model uses fewer tokens?
* Which model provides the best overall trade-off?

The CLI comparison is separate from the MCP tool interface in the current implementation.

---

# 20. MCP vs CLI

The project intentionally provides two ways to interact with the evaluation system.

### MCP

```text
Claude Desktop
      ↓
MCP
      ↓
server.py
      ↓
Evaluation Harness
```

Useful for AI-native interaction and tool-based workflows.

### CLI

```text
Terminal
   ↓
main.py
   ↓
Evaluation Harness
```

Useful for scripting, automation, benchmarking, and direct developer workflows.

---

# 21. MCP Inspector Architecture

MCP Inspector provides an independent testing path.

```text
MCP Inspector
      │
      │ STDIO
      ▼
Python MCP Server
      │
      ▼
Evaluation Harness
```

This is useful because it separates:

**MCP/server problems**

from:

**Claude Desktop configuration problems**

For example:

```text
Claude Desktop fails
       │
       ▼
Test with Inspector
       │
       ├── Works → investigate Claude configuration
       │
       └── Fails → investigate MCP/Python implementation
```

---

# 22. Configuration Flow

Environment variables provide provider credentials and runtime configuration.

```text
Environment
    │
    ▼
settings.py
    │
    ├── Gemini configuration
    │
    ├── Groq configuration
    │
    ├── OpenAI configuration
    │
    └── Runtime configuration
           │
           ▼
       Model Factory
           │
           ▼
       Model Target
```

Provider-specific credentials remain outside the source code.

---

# 23. Design Principles

## Separation of Concerns

MCP communication, orchestration, model execution, evaluation, metrics, and persistence are separated.

## Modularity

New providers and evaluators can be added without rewriting the entire evaluation runner.

## Provider Agnosticism

The evaluation pipeline operates against a common model target abstraction.

## Reproducibility

The same dataset can be evaluated against different models using the same evaluation logic.

## Observability

Latency, scores, pass rates, and token usage provide measurable model performance information.

## Extensibility

The architecture provides a foundation for additional evaluation strategies, providers, persistence systems, dashboards, and deployment infrastructure.

---

# 24. Future Architecture

The planned evolution of the system is:

```text
Current
   │
   ├── MCP
   ├── Multi-provider LLMs
   ├── Evaluation
   ├── Metrics
   └── JSONL Results
        │
        ▼
Future
   │
   ├── Background Evaluation Jobs
   ├── Persistent Experiment Tracking
   ├── Evaluation Dashboard
   ├── Advanced RAG Evaluation
   ├── Guardrails
   ├── Docker
   ├── CI/CD
   ├── Monitoring
   └── Kubernetes
```

The long-term goal is to evolve the project from a local evaluation harness into a more complete **LLM evaluation and experimentation platform**.

---

# 25. Complete System Summary

```text
                         ┌─────────────────┐
                         │ Claude Desktop  │
                         └────────┬────────┘
                                  │
                                  │ MCP
                                  ▼
                         ┌─────────────────┐
                         │    server.py    │
                         │   MCP Server    │
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │    harness.py   │
                         │   Orchestrator  │
                         └────────┬────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼
        ┌───────────┐       ┌────────────┐      ┌────────────┐
        │  Dataset  │       │   Model    │      │ Evaluators │
        │   Loader  │       │   Factory  │      │            │
        └───────────┘       └─────┬──────┘      └────────────┘
                                  │
                         ┌────────┴────────┐
                         │                 │
                         ▼                 ▼
                    ┌──────────┐      ┌──────────┐
                    │  Gemini  │      │   Groq   │
                    └──────────┘      └──────────┘
                         │                 │
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                         │ EvaluationRunner│
                         └────────┬────────┘
                                  │
                         ┌────────┴────────┐
                         ▼                 ▼
                    ┌──────────┐      ┌──────────┐
                    │ Metrics  │      │ Recorder │
                    └──────────┘      └──────────┘
                         │                 │
                         └────────┬────────┘
                                  ▼
                           Evaluation Run
                                  │
                                  ▼
                           Model Comparison
```

The architecture is designed around one central idea:

> **LLM systems should be evaluated systematically rather than judged only by whether a response "looks good."**

The MCP layer makes that evaluation infrastructure accessible to AI assistants, while the underlying modular architecture keeps the system extensible for future experimentation, deployment, and MLOps workflows.
