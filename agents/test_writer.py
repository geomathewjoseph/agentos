"""Test Writer Agent — Writes tests BEFORE implementation.

Uses Qwen2.5-Coder to create comprehensive test suites based on
the architecture and acceptance criteria, following TDD principles.
"""

from __future__ import annotations

from router.fallback_chain import with_fallback
from tools.error_handler import (
    repair_json,
    extract_code_from_markdown,
    clean_llm_output,
    escape_unescaped_newlines,
)
from tools.checkpoint import save_checkpoint
from tools.token_counter import truncate_to_fit
from tools.logger import log, print_stage_banner
import json
import re

PROMPT = """
You are a senior test engineer. Write a focused, comprehensive test suite BEFORE the implementation exists.

Architecture:
{architecture}

Acceptance Criteria:
{criteria}

CRITICAL RULES:
- CONSOLIDATE TESTS: Write exactly 1 cohesive test file (e.g., **tests/test_main.py** or **test_main.py**) covering core functionality and edge cases. Do NOT create multiple test files.
- Format the test file using a filename annotation followed by a python code block:
**tests/test_main.py**
```python
import pytest
...complete runnable test code...
```
- EXECUTABLE CODE ONLY: Output real, runnable pytest code. Do NOT output markdown tables, Gherkin docs, or commentary snippets.
- Use mocks/stubs for external network or database services — tests must run locally and self-contained.
- COMPLETE CODE ONLY: Zero placeholders, no ellipses (...), no empty test stubs.
- Do NOT output any tool calls, function calls, XML tags, or conversational banter. Output ONLY the file in the specified format.
"""



def _extract_criteria(plan: str) -> str:
    """Pull the Acceptance Criteria section from the plan."""
    match = re.search(
        r"## Acceptance Criteria(.*?)(?=##|\Z)", plan, re.DOTALL | re.IGNORECASE
    )
    return match.group(1).strip() if match else plan


def run_test_writer(state: dict) -> dict:
    """Execute the test writing phase."""
    print_stage_banner("Test Writer")
    log("test_writer", "Writing test suite")
    state["last_stage"] = "test_writer"

    if not state.get("architecture"):
        state["test_spec"] = {}
        return state

    criteria = _extract_criteria(state.get("plan") or "")
    arch_context = truncate_to_fit(state.get("architecture") or "", 1000)
    prompt = PROMPT.format(architecture=arch_context, criteria=criteria)
    prompt = truncate_to_fit(prompt, 1800)

    try:
        raw = with_fallback("coding", prompt)
        cleaned = clean_llm_output(raw)
        log(
            "test_writer",
            f"LLM output ({len(raw)} chars), first 200: {raw[:200]!r}",
        )
        tests = None
        if cleaned.startswith("{"):
            try:
                tests = json.loads(cleaned)
            except Exception:
                try:
                    tests = json.loads(escape_unescaped_newlines(cleaned))
                except Exception:
                    tests = repair_json(cleaned) or repair_json(raw)

        if not tests:
            tests = extract_code_from_markdown(raw)

        if not tests:
            tests = repair_json(cleaned) or repair_json(raw) or extract_code_from_markdown(cleaned)

        if not tests and ("def test_" in raw or "import pytest" in raw or "import unittest" in raw):
            tests = {"tests/test_main.py": raw}
        if not isinstance(tests, dict):
            raise ValueError(f"test_writer output is not a dict: {type(tests)}")

        # Only keep files that contain actual test logic
        valid_tests = {}
        for fname, content in tests.items():
            if not isinstance(content, str) or len(content.strip()) < 20:
                continue
            if "def " not in content and "import " not in content:
                continue
            valid_tests[fname] = content

        state["test_spec"] = valid_tests if valid_tests else tests
        save_checkpoint(state, "post_test_writer")
        log("test_writer", f"Test spec ready: {list(state['test_spec'].keys())} ✓", "success")

    except Exception as e:
        err = f"[test_writer] failed: {e}"
        log("test_writer", err, "warning")
        state["error_log"] = (state.get("error_log") or []) + [err]
        if "exhausted" in str(e):
            state["fatal_error"] = True
        state["test_spec"] = {}  # non-fatal — coder can still proceed

    return state
