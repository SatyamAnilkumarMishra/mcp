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


# ---------------------------------------------------------------------------
# Transport helpers
# ---------------------------------------------------------------------------

def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def result_response(id_, result) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def error_response(id_, code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": err}


# ---------------------------------------------------------------------------
# MCP method handlers
# ---------------------------------------------------------------------------

_initialized = False


def handle_initialize(id_, params: dict) -> dict:
    result = {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": SERVER_INFO,
    }
    return result_response(id_, result)


def handle_initialized_notification(params: dict):
    global _initialized
    _initialized = True
    return None


def handle_tools_list(id_, params: dict) -> dict:
    tools = []
    for name, spec in TOOLS.items():
        tools.append({
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["inputSchema"],
        })
    return result_response(id_, {"tools": tools})


def handle_tools_call(id_, params: dict) -> dict:
    name = params.get("name")
    arguments = params.get("arguments", {}) or {}

    if name not in TOOLS:
        return error_response(id_, INVALID_PARAMS, f"Unknown tool: {name}")

    handler = TOOLS[name]["handler"]
    try:
        output = handler(arguments)
        return result_response(id_, {
            "content": [{"type": "text", "text": json.dumps(output, default=str)}],
            "isError": False,
        })
    except ValueError as e:
        return result_response(id_, {
            "content": [{"type": "text", "text": f"Tool error: {e}"}],
            "isError": True,
        })
    except Exception:
        return result_response(id_, {
            "content": [{"type": "text", "text": f"Internal tool error:\n{traceback.format_exc()}"}],
            "isError": True,
        })


METHOD_HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}

NOTIFICATION_HANDLERS = {
    "notifications/initialized": handle_initialized_notification,
}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def handle_message(msg: dict):
    method = msg.get("method")

    if method is None:
        if "id" not in msg or msg.get("id") is None:
            return None
        return error_response(msg.get("id"), INVALID_REQUEST, "Missing 'method'")

    if "id" not in msg:
        fn = NOTIFICATION_HANDLERS.get(method)
        if fn:
            fn(msg.get("params", {}) or {})
        return None

    id_ = msg.get("id")
    fn = METHOD_HANDLERS.get(method)
    if fn is None:
        return error_response(id_, METHOD_NOT_FOUND, f"Method not found: {method}")

    try:
        return fn(id_, msg.get("params", {}) or {})
    except Exception:
        return error_response(id_, INTERNAL_ERROR, "Internal error",
                               data=traceback.format_exc())


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send(error_response(None, PARSE_ERROR, "Parse error: invalid JSON"))
            continue

        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            bad_id = msg.get("id") if isinstance(msg, dict) else None
            send(error_response(bad_id, INVALID_REQUEST,
                                 "Invalid Request: not valid JSON-RPC 2.0"))
            continue

        response = handle_message(msg)
        if response is not None:
            send(response)


if __name__ == "__main__":
    main()

