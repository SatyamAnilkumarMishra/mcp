"""
Persists raw per-sample results to a JSONL file.

FIXED BUG (from the original version): results used to be buffered in
memory and only written to disk on an explicit `.flush()` call at the
very end of a run. If a 200-sample run crashed on sample 150 — a real
possibility with flaky network calls — every one of those 150 completed
results was lost, because nothing had touched disk yet.

The fix: open the output file once, in append mode, at construction
time, and write each result to disk immediately in `save()`. `flush()`
still exists (for the return-path filename main.py prints), but it's no
longer load-bearing for correctness — you can `tail -f` the run file
mid-run, and a crash only loses the *in-flight* sample, not everything
before it.

LEARNING POINT: this is a general principle for anything long-running —
prefer "write as you go" over "buffer then write" whenever a partial
result still has value. Buffering is fine for reports (report.csv is
still built at the end from an in-memory `results` list, and that's
okay — reports need the *whole* run to be meaningful anyway).
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List


# Absolute path to the llm_eval_harness package directory.
# This prevents Claude Desktop's working directory from affecting
# where evaluation results are written.
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# All raw evaluation results will be stored here:
# D:\mcp\llm_eval_harness\reports\results
_DEFAULT_OUTPUT_DIR = os.path.join(
    _HARNESS_ROOT,
    "reports",
    "results",
)


class ResultRecorder:
    def __init__(
        self,
        output_dir: str = _DEFAULT_OUTPUT_DIR,
        run_id: str = None,
    ):
        # If a custom relative path is supplied, resolve it relative
        # to the harness package instead of the current working directory.
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(_HARNESS_ROOT, output_dir)

        self.output_dir = os.path.abspath(output_dir)

        # Create the directory safely.
        os.makedirs(self.output_dir, exist_ok=True)

        # Generate a unique run ID if one wasn't supplied.
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        self.path = os.path.join(
            self.output_dir,
            f"run_{self.run_id}.jsonl",
        )

        # Append mode + line buffering so each result is written
        # immediately instead of remaining only in memory.
        self._file = open(
            self.path,
            "a",
            encoding="utf-8",
            buffering=1,
        )

        # Keep an in-memory copy for callers that need it.
        self.buffer: List[Dict[str, Any]] = []

    def save(self, result: Dict[str, Any]):
        """Save one evaluation result immediately to disk."""
        self.buffer.append(result)

        self._file.write(
            json.dumps(
                result,
                ensure_ascii=False,
            )
            + "\n"
        )

        # Explicitly flush after every result.
        self._file.flush()

    def flush(self, run_id: str = None) -> str:
        """
        Ensure everything is written to disk and return the
        absolute path to the JSONL run file.
        """
        self._file.flush()
        return self.path

    def close(self):
        """Close the result file safely."""
        if not self._file.closed:
            self._file.flush()
            self._file.close()
