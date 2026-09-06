# Model Context Protocol

A Model Context Protocol (MCP) server implemented **entirely from scratch
in vanilla Python** — no `mcp` SDK, no framework, standard library only.
It speaks raw JSON-RPC 2.0 over stdio, implements the MCP `initialize`
handshake and the `tools` capability, and is wired directly into the real
`llm_eval_harness` codebase (included in `llm_eval_harness/`).

## Why from scratch

The goal was to understand MCP at the protocol level — the exact JSON-RPC
message shapes, the initialization lifecycle, capability negotiation, and
error semantics — rather than relying on the official SDK's abstractions.

# MCP LLM Evaluation Harness

A **custom LLM evaluation and benchmarking system written from scratch in vanilla Python and exposed through the Model Context Protocol (MCP)**.

The system allows AI assistants such as Claude Desktop to interact with an LLM evaluation pipeline through MCP tools.

It supports multiple LLM providers, four evaluation strategies, evaluation metrics, result persistence, retry handling, asynchronous execution, and model comparison.

The evaluation logic, execution pipeline, provider abstraction, metrics tracking, and result recording were implemented directly in Python rather than relying on an existing LLM evaluation framework.

---

## 🚀 What This Project Does

The system provides a reusable pipeline for evaluating and benchmarking LLMs against structured datasets.

It can:

* Discover evaluation datasets
* Run evaluations against different LLM providers
* Evaluate responses using **four evaluation methods**
* Track pass rate, score, latency, and token usage
* Persist per-sample results as JSONL
* Maintain evaluation run history
* Compare models using the same evaluation dataset
* Handle asynchronous evaluation
* Handle API failures using retry and backoff logic
* Expose the evaluation system through MCP
* Integrate with Claude Desktop
* Be tested independently using MCP Inspector

### Core Workflow

```text
Dataset
   ↓
LLM
   ↓
Generated Response
   ↓
Evaluation
   ↓
Metrics
   ↓
Results
   ↓
Model Comparison
```

---

# 🧠 Built From Scratch

This project was implemented in **vanilla Python** to understand the internal mechanics of an LLM evaluation system rather than simply using an existing evaluation framework.

The major components were implemented directly:

```text
Dataset Loading
      ↓
Prompt Construction
      ↓
Model Provider Abstraction
      ↓
LLM Generation
      ↓
Evaluation
      ↓
Metrics Tracking
      ↓
Result Recording
      ↓
Run History
      ↓
Model Comparison
```

The system uses Python's built-in `asyncio` for asynchronous execution and implements its own concurrency control, retry handling, metrics tracking, and JSONL result persistence.

---

# 🔌 MCP Integration

After building the evaluation system, I exposed it through the **Model Context Protocol (MCP)**.

This allows MCP-compatible AI assistants to interact with the evaluation system through tools instead of manually executing Python commands.

The MCP server currently provides four primary tools:

| Tool               | Purpose                                               |
| ------------------ | ----------------------------------------------------- |
| `list_datasets`    | Discover available evaluation datasets                |
| `run_eval`         | Execute an evaluation against a selected model        |
| `get_results`      | Retrieve results from a completed evaluation          |
| `list_run_history` | View evaluation runs completed in the current session |

The architecture and internal data flow are documented in [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

# 🧪 Four Evaluation Methods

The system implements four different evaluation approaches.

### 1. Exact Match

Checks whether the generated response exactly matches the expected answer.

```text
Prediction == Expected Answer
          ↓
       Pass / Fail
```

Useful for deterministic answers and exact-answer tasks.

---

### 2. Keyword Match

Checks whether required keywords are present in the generated response.

It can be configured to require:

* Any matching keyword
* All required keywords

```text
Model Response
      ↓
Keyword Detection
      ↓
Pass / Fail
```

This is useful when multiple valid responses can contain the same important concepts.

---

### 3. Rubric Evaluation

Evaluates the generated response against configurable criteria.

```text
Response
   ↓
Evaluation Criteria
   ↓
Individual Checks
   ↓
Weighted Score
```

This allows responses to be evaluated using defined quality criteria rather than simple string matching.

---

### 4. LLM-as-a-Judge

Uses another LLM to evaluate the generated response.

```text
                  ┌───────────────┐
Question ────────►│ Target LLM    │
                  └───────┬───────┘
                          ↓
                   Generated Answer
                          ↓
                  ┌───────────────┐
Answer + Criteria ►│ Judge LLM    │
                  └───────┬───────┘
                          ↓
                     Score / Result
```

This allows more semantic evaluation when exact matching or keyword-based evaluation is insufficient.

---

# 📊 Evaluation Metrics

The system tracks metrics including:

* **Pass Rate**
* **Average Score**
* **Average Latency**
* **Token Usage**

These metrics allow models to be evaluated not only on response quality but also on performance characteristics.

---

# ⚡ Async Evaluation

The evaluation runner uses Python's `asyncio` to support asynchronous execution.

Configurable concurrency controls how many evaluation requests can execute simultaneously.

```text
Dataset
   │
   ├── Sample 1 ──► LLM ──► Evaluator
   ├── Sample 2 ──► LLM ──► Evaluator
   ├── Sample 3 ──► LLM ──► Evaluator
   └── Sample N ──► LLM ──► Evaluator
```

This makes the evaluation system more efficient while allowing concurrency to be adjusted according to provider limits.

---

# 🔄 Retry & Backoff

The system implements its own retry mechanism for transient API failures and rate-limit responses.

It supports:

* Automatic retries
* Exponential backoff
* Provider/server-provided retry delays when available

This prevents temporary API failures from immediately terminating an evaluation run.

---

# 💾 Result Persistence

Evaluation results are persisted in **JSONL format**.

Per-sample results can contain:

* Input question
* Expected answer
* Model prediction
* Evaluation result
* Score
* Latency
* Token usage
* Evaluation metadata

This allows individual evaluation results to be inspected after execution.

---

# 📈 Model Benchmarking

The system can evaluate different models against the **same dataset and evaluation logic**.

```text
                    Dataset
                       │
              ┌────────┴────────┐
              ↓                 ↓
           Gemini              Groq
              │                 │
              ↓                 ↓
          Evaluation        Evaluation
              │                 │
              └────────┬────────┘
                       ↓
                Metric Comparison
```

Models can be compared using:

* Pass rate
* Average score
* Average latency
* Token usage

---

# 🤖 Claude Desktop

The MCP server can be connected to Claude Desktop through its MCP configuration.

Example:

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

**Never commit real API keys to the repository.**

After restarting Claude Desktop, the MCP evaluation tools become available to the assistant.

---

# 🔍 MCP Inspector

The MCP server can also be tested independently using MCP Inspector.

Launch it with:

```text
npx @modelcontextprotocol/inspector C:\Python313\python.exe D:\mcp\server.py
```

Inspector can be used to:

* Inspect MCP tools
* Inspect tool schemas
* Execute tools manually
* Debug MCP communication
* Verify the MCP server independently of Claude Desktop

---

# 🧪 Example Usage

### Discover datasets

> Use the `list_datasets` tool and show me all available evaluation datasets with their sample counts.

### Run Gemini

> Use the `run_eval` tool to evaluate `sample_eval.json` using the Gemini provider and the `gemini-flash-latest` model. Return the `run_id` and complete evaluation summary.

### Run Groq

> Use the `run_eval` tool to evaluate `sample_eval.json` using the openai-compatible provider and the `openai/gpt-oss-20b` model. Return the `run_id` and complete evaluation summary.

### Retrieve results

> Use the `get_results` tool for `run-1` with `detail=true` and show me the complete per-sample evaluation results.

### View run history

> Use the `list_run_history` tool and show me all evaluation runs completed in this server session.

---

# 📊 Model Comparison

The project also provides a CLI-based model comparison workflow.

Run:

```text
cd D:\mcp\llm_eval_harness
C:\Python313\python.exe main.py --dataset dataset/sample_eval.json --compare
```

The comparison evaluates configured models against the same dataset and compares their evaluation metrics.

---

# 📁 Project Structure

```text
mcp/
│
├── server.py
│
└── llm_eval_harness/
    │
    ├── main.py
    ├── harness.py
    │
    ├── config/
    │   └── settings.py
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
```

---

# 🧩 Technology Stack

* Python
* Model Context Protocol (MCP)
* AsyncIO
* Pydantic
* Google Gemini API
* Groq API
* OpenAI-compatible APIs
* Claude Desktop
* MCP Inspector
* JSONL
* LLM Evaluation
* LLM-as-a-Judge

---

# 🎯 Project Goals

The primary goal is to understand and implement the components required to **measure, evaluate, and benchmark LLM behavior**.

Rather than relying on a pre-built evaluation framework, the core evaluation pipeline was implemented directly in Python.

The system supports four evaluation methods:

```text
Exact Match
     │
Keyword Match
     │
Rubric Evaluation
     │
LLM-as-a-Judge
     ↓
Evaluation Results
     ↓
Metrics
     ↓
Benchmarking
```

MCP was then added as an AI-native interface for interacting with the evaluation system.

---

# 🚧 Future Improvements

Planned improvements include:

* Background/asynchronous evaluation jobs
* Persistent experiment tracking
* Evaluation dashboards
* Advanced RAG evaluation
* Additional model providers
* Improved LLM-as-a-Judge strategies
* Docker containerization
* CI/CD integration
* Automated evaluation pipelines
* Production deployment
* Guardrails and safety evaluation
* Monitoring and observability
* Kubernetes-based deployment

---

# ⭐ Project Objective

Build a **custom LLM evaluation and benchmarking system from scratch in vanilla Python**, implement multiple evaluation strategies and model integrations, and expose the system through MCP so that AI assistants can interact with the evaluation infrastructure.

```text
                    MCP
                     +
              LLM Providers
                     +
        ┌────────────┼────────────┐
        ↓            ↓            ↓
   Exact Match  Keyword Match  Rubric
                     +
               LLM-as-a-Judge
                     ↓
                  Metrics
                     ↓
               Experimentation
                     ↓
                Benchmarking
                     =
          AI Evaluation Infrastructure
```

**The objective is not just to evaluate LLMs, but to understand and implement the engineering behind an LLM evaluation system from the ground up.**
