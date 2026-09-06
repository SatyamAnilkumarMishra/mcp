"""
MCP server built from scratch in vanilla Python - no `mcp` SDK.

Implements full MCP Core Capabilities:
  - stdio JSON-RPC 2.0 transport (read/write loop)
  - the MCP `initialize` / `notifications/initialized` handshake
  - the `tools` capability: `tools/list` and `tools/call`
  - the `resources` capability: `resources/list` and `resources/read`
  - the `prompts` capability: `prompts/list` and `prompts/get`
  - wiring into harness.py and llm_eval_harness

Run standalone for manual testing:
    python server.py
Then paste JSON-RPC messages, one per line, on stdin.

Run the scripted test suite:
    python test_server.py
"""

import sys
import json
import traceback
import os
import glob
import warnings

# Suppress library deprecation warnings so stdio stdout is purely JSON-RPC
warnings.filterwarnings("ignore")
os.environ["GRPC_VERBOSITY"] = "NONE"

import harness

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "eval-harness-mcp", "version": "0.3.0"}

# JSON-RPC standard error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# ---------------------------------------------------------------------------
# 1. Tool Registry
# ---------------------------------------------------------------------------

def _tool_list_datasets(args: dict) -> list:
    return harness.list_datasets()


def _tool_run_eval(args: dict) -> dict:
    dataset = args.get("dataset")
    model = args.get("model")
    if not dataset or not model:
        raise ValueError("'dataset' and 'model' are required")
    # Normalize deprecated alias names
    if model in ("gemini-flash-latest", "gemini-flash", "gemini-2.5-flash"):
        model = "gemini-3.6-flash"
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
# 2. Prompts Registry
# ---------------------------------------------------------------------------

PROMPTS = {
    "evaluate_career_advisor": {
        "description": "Prompt template to evaluate the Career Advisor response quality against domain criteria.",
        "arguments": [
            {"name": "user_query", "description": "User question submitted to Career Advisor", "required": True},
            {"name": "advisor_response", "description": "Generated career advisor response", "required": True}
        ],
        "template": (
            "Evaluate the following Career Advisor response for domain accuracy, actionable tone, formatting, and lack of boilerplate emojis:\n\n"
            "USER QUERY:\n{user_query}\n\n"
            "ADVISOR RESPONSE:\n{advisor_response}\n\n"
            "Provide scoring against exactness, clarity, and structured table usage where appropriate."
        )
    },
    "analyze_benchmark_report": {
        "description": "Analyze an evaluation run summary and suggest model optimizations.",
        "arguments": [
            {"name": "run_id", "description": "Evaluation run identifier", "required": True}
        ],
        "template": (
            "Analyze the evaluation benchmark results for run '{run_id}'. "
            "Examine failure cases, pass rate, and identify systematic reasoning or extraction errors."
        )
    }
}


# ---------------------------------------------------------------------------
# 3. Transport Helpers
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
# 4. MCP Method Handlers
# ---------------------------------------------------------------------------

_initialized = False


def handle_initialize(id_, params: dict) -> dict:
    result = {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {
            "tools": {},
            "resources": {},
            "prompts": {}
        },
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


def handle_resources_list(id_, params: dict) -> dict:
    """Lists available dataset and report resources."""
    resources = []
    dataset_dir = os.path.join(os.path.dirname(__file__), "llm_eval_harness", "dataset")
    if os.path.exists(dataset_dir):
        for f in sorted(glob.glob(os.path.join(dataset_dir, "*.json"))):
            base = os.path.basename(f)
            resources.append({
                "uri": f"eval://dataset/{base}",
                "name": f"Dataset: {base}",
                "description": f"Evaluation dataset file {base}",
                "mimeType": "application/json"
            })

    # Add dynamic completed runs as resources
    for run in harness.list_run_history():
        run_id = run["run_id"]
        resources.append({
            "uri": f"eval://reports/{run_id}",
            "name": f"Run Report: {run_id}",
            "description": f"Results for run {run_id} ({run['dataset']} on {run['model']})",
            "mimeType": "application/json"
        })

    return result_response(id_, {"resources": resources})


def handle_resources_read(id_, params: dict) -> dict:
    """Reads content for a specific resource URI."""
    uri = params.get("uri", "")
    if not uri:
        return error_response(id_, INVALID_PARAMS, "Missing 'uri' parameter")

    if uri.startswith("eval://dataset/"):
        dataset_name = uri.replace("eval://dataset/", "")
        dataset_path = os.path.join(os.path.dirname(__file__), "llm_eval_harness", "dataset", dataset_name)
        if not os.path.exists(dataset_path):
            return error_response(id_, INVALID_PARAMS, f"Dataset not found: {dataset_name}")
        with open(dataset_path, "r", encoding="utf-8") as f:
            content = f.read()
        return result_response(id_, {
            "contents": [{
                "uri": uri,
                "mimeType": "application/json",
                "text": content
            }]
        })

    if uri.startswith("eval://reports/"):
        run_id = uri.replace("eval://reports/", "")
        try:
            results = harness.get_results(run_id, detail=True)
            return result_response(id_, {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(results, indent=2)
                }]
            })
        except ValueError as e:
            return error_response(id_, INVALID_PARAMS, str(e))

    return error_response(id_, INVALID_PARAMS, f"Unsupported resource URI: {uri}")


def handle_prompts_list(id_, params: dict) -> dict:
    """Lists prompt templates."""
    prompts = []
    for name, spec in PROMPTS.items():
        prompts.append({
            "name": name,
            "description": spec["description"],
            "arguments": spec.get("arguments", [])
        })
    return result_response(id_, {"prompts": prompts})


def handle_prompts_get(id_, params: dict) -> dict:
    """Renders a prompt template."""
    name = params.get("name")
    args = params.get("arguments", {}) or {}

    if not name or name not in PROMPTS:
        return error_response(id_, INVALID_PARAMS, f"Prompt not found: {name}")

    spec = PROMPTS[name]
    template = spec["template"]
    rendered = template.format(**{
        k["name"]: args.get(k["name"], f"<{k['name']}>")
        for k in spec.get("arguments", [])
    })

    return result_response(id_, {
        "description": spec["description"],
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": rendered}
            }
        ]
    })


METHOD_HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "resources/list": handle_resources_list,
    "resources/read": handle_resources_read,
    "prompts/list": handle_prompts_list,
    "prompts/get": handle_prompts_get,
}

NOTIFICATION_HANDLERS = {
    "notifications/initialized": handle_initialized_notification,
}


# ---------------------------------------------------------------------------
# 5. Dispatch
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
