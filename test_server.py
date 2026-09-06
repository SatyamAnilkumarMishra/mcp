"""
Scripted regression test suite for server.py, testing Tools, Resources, and Prompts capabilities.

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
        check("resources" in resp["result"]["capabilities"],
              "initialize: capabilities include 'resources'")
        check("prompts" in resp["result"]["capabilities"],
              "initialize: capabilities include 'prompts'")

        # --- 2. notifications/initialized ---
        server.send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                     expect_response=False)
        print("[PASS] notifications/initialized: sent, no response expected")

        # --- 3. tools/list ---
        resp = server.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tool_names = {t["name"] for t in resp["result"]["tools"]}
        check({"list_datasets", "run_eval", "get_results", "list_run_history"} <= tool_names,
              f"tools/list: all expected tools present (got {tool_names})")

        # --- 4. tools/call: list_datasets ---
        resp = server.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                             "params": {"name": "list_datasets", "arguments": {}}})
        check(resp["result"]["isError"] is False, "tools/call list_datasets: no error")
        datasets = json.loads(resp["result"]["content"][0]["text"])
        check(isinstance(datasets, list) and len(datasets) > 0,
              f"tools/call list_datasets: found datasets ({datasets})")

        # --- 5. tools/call: list_run_history ---
        resp = server.send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "list_run_history", "arguments": {}}})
        check(resp["result"]["isError"] is False, "tools/call list_run_history: no error")

        # --- 6. tools/call: get_results with unknown run_id -> tool error ---
        resp = server.send({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                             "params": {"name": "get_results", "arguments": {"run_id": "run-fake"}}})
        check(resp["result"]["isError"] is True,
              "tools/call get_results unknown run_id: isError=True, not a crash")

        # --- 7. tools/call: run_eval missing required arg -> tool error ---
        resp = server.send({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                             "params": {"name": "run_eval", "arguments": {"model": "x"}}})
        check(resp["result"]["isError"] is True,
              "tools/call run_eval missing 'dataset': isError=True, not a crash")

        # --- 8. tools/call: unknown tool -> -32602 ---
        resp = server.send({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                             "params": {"name": "not_a_real_tool", "arguments": {}}})
        check(resp.get("error", {}).get("code") == -32602,
              "tools/call unknown tool: returns -32602 invalid params")

        # --- 9. resources/list ---
        resp = server.send({"jsonrpc": "2.0", "id": 8, "method": "resources/list", "params": {}})
        resources = resp["result"]["resources"]
        check(len(resources) > 0, f"resources/list: found {len(resources)} resources")
        uris = [r["uri"] for r in resources]
        check("eval://dataset/sample_eval.json" in uris, "resources/list contains sample_eval.json resource")

        # --- 10. resources/read ---
        resp = server.send({"jsonrpc": "2.0", "id": 9, "method": "resources/read",
                             "params": {"uri": "eval://dataset/sample_eval.json"}})
        check("contents" in resp["result"] and len(resp["result"]["contents"]) > 0,
              "resources/read: successfully read dataset resource")

        # --- 11. prompts/list ---
        resp = server.send({"jsonrpc": "2.0", "id": 10, "method": "prompts/list", "params": {}})
        prompts = resp["result"]["prompts"]
        check(len(prompts) > 0, f"prompts/list: found {len(prompts)} prompts")

        # --- 12. prompts/get ---
        resp = server.send({"jsonrpc": "2.0", "id": 11, "method": "prompts/get",
                             "params": {
                                 "name": "evaluate_career_advisor",
                                 "arguments": {
                                     "user_query": "How to transition to ML?",
                                     "advisor_response": "Focus on Linear Algebra, Python, and PyTorch."
                                 }
                             }})
        rendered_text = resp["result"]["messages"][0]["content"]["text"]
        check("How to transition to ML?" in rendered_text,
              "prompts/get: rendered prompt template correctly")

        # --- 13. unknown method -> -32601 ---
        resp = server.send({"jsonrpc": "2.0", "id": 12, "method": "totally/unknown"})
        check(resp.get("error", {}).get("code") == -32601,
              "unknown method: returns -32601 method not found")

        # --- 14. malformed JSON -> -32700 ---
        server.proc.stdin.write("{not valid json\n")
        server.proc.stdin.flush()
        resp = json.loads(server.proc.stdout.readline())
        check(resp.get("error", {}).get("code") == -32700,
              "malformed JSON: returns -32700 parse error")

        # --- 15. (optional) real end-to-end run_eval ---
        if has_key:
            dataset_name = datasets[0]["dataset"]
            resp = server.send({"jsonrpc": "2.0", "id": 13, "method": "tools/call",
                                 "params": {"name": "run_eval",
                                            "arguments": {"dataset": dataset_name,
                                                          "model": "gemini-flash-latest",
                                                          "provider": "gemini"}}})
            check(resp["result"]["isError"] is False,
                  f"tools/call run_eval end-to-end against '{dataset_name}': no error")
            run_out = json.loads(resp["result"]["content"][0]["text"])
            check("run_id" in run_out, "run_eval: response includes run_id")
        else:
            print("[SKIP] run_eval end-to-end test (no GEMINI_API_KEY/OPENAI_API_KEY in environment)")

        print("\nAll tests passed successfully.")
    finally:
        server.close()


if __name__ == "__main__":
    run_tests()
