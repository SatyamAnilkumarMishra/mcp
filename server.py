"""
MCP server built from scratch in vanilla Python - no `mcp` SDK.

Implements:
  - stdio JSON-RPC 2.0 transport (read/write loop)
  - the MCP `initialize` / `notifications/initialized` handshake
  - the `tools` capability: `tools/list` and `tools/call`
  - wiring of tools/call into harness.py, which calls the real
    llm_eval_harness codebase (./llm_eval_harness/)

Run standalone for manual testing:
    python server.py
Then paste JSON-RPC messages, one per line, on stdin.

Run the scripted test suite:
    python test_server.py

Connect to a real client (Claude Desktop, MCP Inspector, etc.) over stdio.
"""

import sys
import json
import traceback

import harness

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "eval-harness-mcp", "version": "0.2.0"}

# JSON-RPC standard error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# ---------------------------------------------------------------------------
# Tool registry: maps a tool name to (description, input schema, handler fn)
# These map directly onto harness.py's real functions, which in turn call
# the actual llm_eval_harness codebase (DatasetLoader, EvaluationRunner,
# get_model_target, evaluators, MetricsTracker).
# ---------------------------------------------------------------------------

def _tool_list_datasets(args: dict) -> list:
    return harness.list_datasets()


def _tool_run_eval(args: dict) -> dict:
    dataset = args.get("dataset")
    model = args.get("model")
    if not dataset or not model:
        raise ValueError("'dataset' and 'model' are required")
    provider = args.get("provider", "gemini")
    system_prompt = args.get("system_prompt")
    max_concurrent = args.get("max_concurrent")
    return harness.run_eval(
        dataset=dataset,
        model=model,
        provider=provider,
        system_prompt=system_prompt,
        max_concurrent=max_concurrent,
    )


def _tool_get_results(args: dict) -> dict:
    run_id = args.get("run_id")
    if not run_id:
        raise ValueError("'run_id' is required")
    detail = bool(args.get("detail", False))
    return harness.get_results(run_id, detail=detail)


def _tool_list_run_history(args: dict) -> list:
    return harness.list_run_history()


TOOLS = {
    "list_datasets": {
        "description": "List eval dataset files available in the harness's dataset/ directory, with sample counts.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": _tool_list_datasets,
    },
    "run_eval": {
        "description": "Run an eval dataset against a model using the real eval harness pipeline (dataset loader, target, evaluators, metrics). Returns a run_id and summary metrics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset": {"type": "string", "description": "Dataset filename (e.g. 'sample_eval.json') or path"},
                "model": {"type": "string", "description": "Model name to evaluate (e.g. 'gemini-flash-latest')"},
                "provider": {"type": "string", "description": "API provider: 'gemini', 'openai', or 'openai-compatible'", "default": "gemini"},
                "system_prompt": {"type": "string", "description": "Optional system prompt override"},
                "max_concurrent": {"type": "integer", "description": "Max concurrent API calls"},
            },
            "required": ["dataset", "model"],
        },
        "handler": _tool_run_eval,
    },
    "get_results": {
        "description": "Retrieve summary (and optionally full per-sample) results for a previously completed eval run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "The run_id returned by run_eval"},
                "detail": {"type": "boolean", "description": "If true, include full per-sample results", "default": False},
            },
            "required": ["run_id"],
        },
        "handler": _tool_get_results,
    },
    "list_run_history": {
        "description": "List all eval runs completed so far in this server session.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": _tool_list_run_history,
    },
}
