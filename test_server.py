"""
Scripted regression test suite for server.py, wired to the real
llm_eval_harness codebase.

Two tiers:
  1. Protocol-level tests that don't need API keys/network: handshake,
     tools/list, list_datasets, list_run_history, error paths.
  2. run_eval end-to-end - requires a configured API key (GEMINI_API_KEY
     or OPENAI_API_KEY, matching the harness's .env setup) and network
     access. Skipped automatically if no key is present so this suite
     still runs cleanly in environments without one.

Run:
    python test_server.py
"""

import subprocess
import json
import sys
import os


class ServerProcess:
    def __init__(self, cmd):
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )

    def send(self, message: dict, expect_response: bool = True):
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        if not expect_response:
            return None
        line = self.proc.stdout.readline()
        if not line:
            stderr_out = self.proc.stderr.read()
            raise RuntimeError(f"Server produced no output. stderr:\n{stderr_out}")
        return json.loads(line)

    def close(self):
        self.proc.stdin.close()
        self.proc.terminate()
        self.proc.wait(timeout=5)


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def run_tests():
    has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY"))

    server = ServerProcess([sys.executable, "server.py"])
    try:
        # --- 1. initialize ---
        resp = server.send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "test-suite", "version": "1.0"}},
        })
        check(resp.get("id") == 1, "initialize: response id matches request")
        check(resp["result"]["protocolVersion"] == "2024-11-05",
              "initialize: correct protocolVersion returned")
        check("tools" in resp["result"]["capabilities"],
              "initialize: capabilities include 'tools'")

        # --- 2. notifications/initialized ---
        server.send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                     expect_response=False)
        print("[PASS] notifications/initialized: sent, no response expected")

        # --- 3. tools/list ---
        resp = server.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tool_names = {t["name"] for t in resp["result"]["tools"]}
        check({"list_datasets", "run_eval", "get_results", "list_run_history"} <= tool_names,
              f"tools/list: all expected tools present (got {tool_names})")

        # --- 4. tools/call: list_datasets (real harness call, no network needed) ---
        resp = server.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                             "params": {"name": "list_datasets", "arguments": {}}})
        check(resp["result"]["isError"] is False, "tools/call list_datasets: no error")
        datasets = json.loads(resp["result"]["content"][0]["text"])
        check(isinstance(datasets, list) and len(datasets) > 0,
              f"tools/call list_datasets: found datasets ({datasets})")

        # --- 5. tools/call: list_run_history (empty at this point) ---
        resp = server.send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "list_run_history", "arguments": {}}})
        check(resp["result"]["isError"] is False, "tools/call list_run_history: no error")

        # --- 6. tools/call: get_results with unknown run_id -> tool-level error ---
        resp = server.send({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                             "params": {"name": "get_results", "arguments": {"run_id": "run-fake"}}})
        check(resp["result"]["isError"] is True,
              "tools/call get_results unknown run_id: isError=True, not a crash")

        # --- 7. tools/call: run_eval missing required arg -> tool-level error ---
        resp = server.send({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                             "params": {"name": "run_eval", "arguments": {"model": "x"}}})
        check(resp["result"]["isError"] is True,
              "tools/call run_eval missing 'dataset': isError=True, not a crash")

        # --- 8. tools/call: unknown tool -> protocol-level error ---
        resp = server.send({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                             "params": {"name": "not_a_real_tool", "arguments": {}}})
        check(resp.get("error", {}).get("code") == -32602,
              "tools/call unknown tool: returns -32602 invalid params")

        # --- 9. unknown method -> -32601 ---
        resp = server.send({"jsonrpc": "2.0", "id": 8, "method": "totally/unknown"})
        check(resp.get("error", {}).get("code") == -32601,
              "unknown method: returns -32601 method not found")

        # --- 10. malformed JSON -> -32700 ---
        server.proc.stdin.write("{not valid json\n")
        server.proc.stdin.flush()
        resp = json.loads(server.proc.stdout.readline())
        check(resp.get("error", {}).get("code") == -32700,
              "malformed JSON: returns -32700 parse error")

        # --- 11. (optional) real end-to-end run_eval, only if a key is configured ---
        if has_key:
            dataset_name = datasets[0]["dataset"]
            resp = server.send({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                                 "params": {"name": "run_eval",
                                            "arguments": {"dataset": dataset_name,
                                                          "model": "gemini-flash-latest",
                                                          "provider": "gemini"}}})
            check(resp["result"]["isError"] is False,
                  f"tools/call run_eval end-to-end against '{dataset_name}': no error")
            run_out = json.loads(resp["result"]["content"][0]["text"])
            check("run_id" in run_out, "run_eval: response includes run_id")

            resp = server.send({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                                 "params": {"name": "get_results",
                                            "arguments": {"run_id": run_out["run_id"]}}})
            check(resp["result"]["isError"] is False, "get_results after real run: no error")
        else:
            print("[SKIP] run_eval end-to-end test (no GEMINI_API_KEY/OPENAI_API_KEY in environment)")

        print("\nAll tests passed.")
    finally:
        server.close()


if __name__ == "__main__":
    run_tests()

