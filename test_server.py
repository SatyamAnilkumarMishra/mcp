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
