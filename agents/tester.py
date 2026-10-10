"""Tester Agent — Docker-sandboxed test execution.

Runs the generated code and tests in a Docker container.
Falls back to host execution if Docker is unavailable.
"""
from __future__ import annotations

import os
import yaml
from tools.docker_sandbox import run_tests_in_sandbox
from tools.checkpoint import save_checkpoint
from tools.logger import log, print_stage_banner

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
with open(os.path.join(_CONFIG_DIR, "thresholds.yaml")) as f:
    _T = yaml.safe_load(f)


def run_tester(state: dict) -> dict:
    """Execute the testing phase."""
    print_stage_banner("Tester")
    log("tester", "Running tests in Docker sandbox")
    state["last_stage"] = "tester"

    if not state.get("code"):
        state["test_results"] = {"passed": False, "errors": ["No code to test"]}
        return state

    timeout = _T["docker"]["timeout_seconds"]

    try:
        passed, errors = run_tests_in_sandbox(state["code"], timeout=timeout)
    except RuntimeError as e:
        # Docker not available — fallback to unsandboxed with warning
        log("tester",
            f"Docker unavailable: {e}. Falling back to host execution.",
            "warning")
        log("tester",
            "WARNING: Running generated code directly on host. Use a VM.",
            "warning")
        from tools._host_runner import run_tests_on_host
        passed, errors = run_tests_on_host(state["code"], timeout=timeout)

    state["test_results"] = {"passed": passed, "errors": errors}
    if errors:
        state["error_log"] = ((state.get("error_log") or []) + errors)[-20:]

    save_checkpoint(state, "post_tester")
    if passed:
        log("tester", "All tests passed ✓", "success")
    else:
        log("tester",
            f"FAILED — {len(errors)} error group(s)",
            "error")
    return state
