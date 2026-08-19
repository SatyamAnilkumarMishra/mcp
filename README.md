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

## Architecture

```
client (Claude Desktop / MCP Inspector / test suite)
        |  JSON-RPC 2.0 over stdio
        v
   server.py   <-- transport, handshake, tool registry, dispatch
        |
        v
   harness.py  <-- adapter: imports the real harness classes directly
        |
        v
   llm_eval_harness/  <-- your actual eval harness (DatasetLoader,
                           EvaluationRunner, evaluators, MetricsTracker...)
```

- **`server.py`** — the MCP server. Reads line-delimited JSON-RPC from
  stdin, dispatches by `method`, writes JSON-RPC responses to stdout.
  Implements `initialize`, `notifications/initialized`, `tools/list`,
  `tools/call`, and standard JSON-RPC error codes.
- **`harness.py`** — imports `DatasetLoader`, `get_model_target`,
  `EvaluationRunner`, the evaluators, and `MetricsTracker` directly from
  `llm_eval_harness/`. No harness logic is duplicated or rewritten — this
  file only adapts the harness's async interface into plain sync
  functions the MCP tool handlers can call.
- **`llm_eval_harness/`** — your actual harness code, unmodified.
- **`test_server.py`** — scripted regression suite. Spawns `server.py` as
  a real subprocess and drives it through the full protocol lifecycle.

## Tools exposed

| Tool | Description |
|---|---|
| `list_datasets` | List dataset files in `llm_eval_harness/dataset/`, with sample counts |
| `run_eval` | Run a dataset against a model through the real pipeline (loader → target → evaluators → metrics) |
| `get_results` | Retrieve summary (or full per-sample, with `detail: true`) results for a past run |
| `list_run_history` | List all runs completed in this server session |

## Setup

```bash
cd llm_eval_harness
pip install -r requirements.txt
# set GEMINI_API_KEY / OPENAI_API_KEY etc. in .env, per the harness's own setup
cd ..
```

## Running it

**Manual stdin testing:**
```bash
python server.py
# then paste, e.g.:
# {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
```

**Scripted test suite:**
```bash
python test_server.py
```
Protocol-level tests (handshake, tool discovery, error paths) always run.
The real end-to-end `run_eval` test only runs if `GEMINI_API_KEY` or
`OPENAI_API_KEY` is set in the environment — otherwise it's skipped
cleanly rather than failing, since it needs live network + a valid key.

**MCP Inspector:**
```bash
npx @modelcontextprotocol/inspector python server.py
```

**Claude Desktop** — add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "eval-harness": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```
Restart Claude Desktop, then ask it to list your datasets or run an eval
— it will discover and call these tools through this server.

