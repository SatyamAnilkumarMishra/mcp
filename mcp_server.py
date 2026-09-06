"""
Custom Model Context Protocol (MCP) server implementation.
Handles JSON-RPC 2.0 requests over stdio using standard Python modules.
"""

import sys
import json
import traceback

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "custom-mcp-server",
    "version": "1.0.0"
}

# Standard JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# --- Tool Handlers ---

def tool_add_numbers(args: dict) -> dict:
    a = args.get("a", 0)
    b = args.get("b", 0)
    return {"sum": a + b}


def tool_compute_average(args: dict) -> dict:
    values = args.get("values", [])
    if not values:
        raise ValueError("values parameter cannot be empty")
    return {"count": len(values), "average": sum(values) / len(values)}


TOOLS = {
    "add_numbers": {
        "description": "Add two numbers together.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"}
            },
            "required": ["a", "b"]
        },
        "handler": tool_add_numbers
    },
    "compute_average": {
        "description": "Calculate the arithmetic mean for a list of values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "List of numeric values"
                }
            },
            "required": ["values"]
        },
        "handler": tool_compute_average
    }
}

# --- Resources ---

RESOURCES = {
    "file://config/default.json": {
        "name": "Default Configuration",
        "description": "Application default settings",
        "mimeType": "application/json",
        "content": json.dumps({"mode": "production", "timeout": 30}, indent=2)
    },
    "file://docs/readme.txt": {
        "name": "Server Documentation",
        "description": "Basic server usage instructions",
        "mimeType": "text/plain",
        "content": "MCP server running over stdio without third-party frameworks."
    }
}

# --- Prompts ---

PROMPTS = {
    "summarize_data": {
        "description": "Generate a concise summary of the provided data points.",
        "arguments": [
            {"name": "dataset_name", "description": "Name of the target dataset", "required": True},
            {"name": "focus_area", "description": "Key attribute to emphasize", "required": False}
        ],
        "template": "Please summarize the findings from '{dataset_name}' with a focus on {focus_area}."
    }
}


# --- Protocol Transport Helpers ---

def write_message(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def success_response(msg_id, result_data) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result_data}


def error_response(msg_id, code: int, message: str, data=None) -> dict:
    error_obj = {"code": code, "message": message}
    if data is not None:
        error_obj["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error_obj}


# --- Request Handlers ---

def handle_initialize(msg_id, params: dict) -> dict:
    return success_response(msg_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {
            "tools": {},
            "resources": {},
            "prompts": {}
        },
        "serverInfo": SERVER_INFO
    })


def handle_initialized(params: dict) -> None:
    return None


def handle_tools_list(msg_id, params: dict) -> dict:
    tool_list = [
        {
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["inputSchema"]
        }
        for name, spec in TOOLS.items()
    ]
    return success_response(msg_id, {"tools": tool_list})


def handle_tools_call(msg_id, params: dict) -> dict:
    tool_name = params.get("name")
    args = params.get("arguments", {}) or {}

    if tool_name not in TOOLS:
        return error_response(msg_id, INVALID_PARAMS, f"Unknown tool: {tool_name}")

    try:
        result = TOOLS[tool_name]["handler"](args)
        return success_response(msg_id, {
            "content": [{"type": "text", "text": json.dumps(result, default=str)}],
            "isError": False
        })
    except Exception as exc:
        return success_response(msg_id, {
            "content": [{"type": "text", "text": f"Error: {exc}"}],
            "isError": True
        })


def handle_resources_list(msg_id, params: dict) -> dict:
    resource_list = [
        {
            "uri": uri,
            "name": item["name"],
            "description": item["description"],
            "mimeType": item["mimeType"]
        }
        for uri, item in RESOURCES.items()
    ]
    return success_response(msg_id, {"resources": resource_list})


def handle_resources_read(msg_id, params: dict) -> dict:
    uri = params.get("uri")
    if not uri or uri not in RESOURCES:
        return error_response(msg_id, INVALID_PARAMS, f"Resource not found: {uri}")

    item = RESOURCES[uri]
    return success_response(msg_id, {
        "contents": [
            {
                "uri": uri,
                "mimeType": item["mimeType"],
                "text": item["content"]
            }
        ]
    })


def handle_prompts_list(msg_id, params: dict) -> dict:
    prompt_list = [
        {
            "name": name,
            "description": spec["description"],
            "arguments": spec.get("arguments", [])
        }
        for name, spec in PROMPTS.items()
    ]
    return success_response(msg_id, {"prompts": prompt_list})


def handle_prompts_get(msg_id, params: dict) -> dict:
    name = params.get("name")
    args = params.get("arguments", {}) or {}

    if not name or name not in PROMPTS:
        return error_response(msg_id, INVALID_PARAMS, f"Prompt not found: {name}")

    spec = PROMPTS[name]
    dataset = args.get("dataset_name", "dataset")
    focus = args.get("focus_area", "key metrics")
    formatted = spec["template"].format(dataset_name=dataset, focus_area=focus)

    return success_response(msg_id, {
        "description": spec["description"],
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": formatted}
            }
        ]
    })


METHOD_ROUTER = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "resources/list": handle_resources_list,
    "resources/read": handle_resources_read,
    "prompts/list": handle_prompts_list,
    "prompts/get": handle_prompts_get,
}

NOTIFICATION_ROUTER = {
    "notifications/initialized": handle_initialized,
}


def process_message(msg: dict):
    method = msg.get("method")
    msg_id = msg.get("id")

    if not method:
        if msg_id is None:
            return None
        return error_response(msg_id, INVALID_REQUEST, "Missing method")

    # Notifications do not have an id field
    if msg_id is None:
        handler = NOTIFICATION_ROUTER.get(method)
        if handler:
            handler(msg.get("params", {}) or {})
        return None

    handler = METHOD_ROUTER.get(method)
    if not handler:
        return error_response(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")

    try:
        return handler(msg_id, msg.get("params", {}) or {})
    except Exception:
        return error_response(msg_id, INTERNAL_ERROR, "Internal server error", data=traceback.format_exc())


def run():
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            write_message(error_response(None, PARSE_ERROR, "Parse error"))
            continue

        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            bad_id = msg.get("id") if isinstance(msg, dict) else None
            write_message(error_response(bad_id, INVALID_REQUEST, "Invalid JSON-RPC 2.0 request"))
            continue

        resp = process_message(msg)
        if resp is not None:
            write_message(resp)


if __name__ == "__main__":
    run()
