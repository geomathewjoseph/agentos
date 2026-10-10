"""Fixer Agent — Targeted debugging expert with stuck-loop detection.

Uses Qwen2.5-Coder to fix test failures. Only sends failing files
to keep prompts small. Detects stuck loops where the same error
repeats and breaks early to avoid wasting API quota.
"""

from __future__ import annotations

import os
import json
import re
import yaml
from router.fallback_chain import with_fallback
from tools.error_handler import (
    repair_json,
    extract_code_from_markdown,
    safe_dict_merge,
    clean_llm_output,
    escape_unescaped_newlines,
)
from tools.checkpoint import save_checkpoint
from tools.token_counter import truncate_to_fit
from tools.logger import log, print_stage_banner

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
with open(os.path.join(_CONFIG_DIR, "thresholds.yaml")) as f:
    _T = yaml.safe_load(f)

STUCK_THRESHOLD = _T["loop"]["stuck_fixer_repeats"]

PROMPT = """
You are a debugging expert. Fix ALL listed errors in the code.

Errors to fix (these are test failures — fixing them is your only goal):
{errors}

Review issues to also address:
{feedback}

Files that contain the errors (fix only what's needed, return ALL files):
{code}

Rules:
- Format each file using a filename annotation followed by a code block:
**filename**
```python
...complete fixed content...
```
- Return every file, not just changed ones
- ZERO PLACEHOLDERS: Implement real logic. Never add "pass", "...", or "# TODO".
- Do NOT output any tool calls, function calls, XML tags, or conversational banter. Output ONLY the files in the specified format.
"""



def _is_stuck(current_errors: list, prev_errors: list) -> bool:
    """Return True if the exact same errors are repeating."""
    if not prev_errors:
        return False
    # Normalize errors for comparison: strip timestamps, paths, line numbers
    import re

    def normalize(err):
        # Remove file paths, line numbers, timestamps
        err = re.sub(r"\b\d{1,2}:\d{2}:\d{2}\b", "", err)  # timestamps
        err = re.sub(r"[A-Za-z]:\\[^:\n]*", "", err)  # Windows paths
        err = re.sub(r"/[^:\n]*", "", err)  # Unix paths
        err = re.sub(r"\bline\s+\d+\b", "", err, flags=re.IGNORECASE)
        err = re.sub(r"\s+", " ", err).strip()
        return err[:500]  # Compare first 500 chars

    curr_set = set(normalize(e) for e in current_errors)
    prev_set = set(normalize(e) for e in prev_errors)
    return curr_set == prev_set and len(curr_set) > 0


def _identify_failing_files(errors: list, code: dict) -> list:
    """Return filenames mentioned in error output."""
    mentioned = []
    for fname in code:
        bare = fname.split("/")[-1]
        if any(bare in e or fname in e for e in errors):
            mentioned.append(fname)
    return mentioned


def run_fixer(state: dict) -> dict:
    """Execute the fix phase."""
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 4)
    print_stage_banner("Fixer", iteration, max_iter)
    log("fixer", f"Fixing — iteration {iteration}/{max_iter}")
    state["last_stage"] = "fixer"

    errors = (state.get("test_results") or {}).get("errors") or []
    feedback = "\n".join(state.get("review_feedback") or [])

    # Stuck-loop detection
    prev = state.get("prev_test_errors") or []
    if _is_stuck(errors, prev):
        log(
            "fixer",
            f"Same errors repeated {STUCK_THRESHOLD} times — breaking loop early "
            f"to avoid wasting API quota. Will trigger restart.",
            "warning",
        )
        state["iteration"] = state["max_iterations"]
        return state

    state["prev_test_errors"] = errors

    if not state.get("code"):
        return state

    # Send only failing files to keep prompt small
    failing_files = _identify_failing_files(errors, state["code"])
    code_to_send = (
        {k: v for k, v in state["code"].items() if k in failing_files}
        if failing_files
        else state["code"]
    )

    errors_str = truncate_to_fit("\n\n".join(errors), 700)
    code_str = truncate_to_fit(json.dumps(code_to_send, indent=2), 1200)
    prompt = PROMPT.format(errors=errors_str, feedback=feedback, code=code_str)
    prompt = truncate_to_fit(prompt, 2200)

    try:
        raw = with_fallback("fixing", prompt)
        cleaned = clean_llm_output(raw)
        log(
            "fixer",
            f"LLM output ({len(raw)} chars), first 200: {raw[:200]!r}",
        )
        fixed = None
        if cleaned.startswith("{"):
            try:
                fixed = json.loads(cleaned)
            except Exception:
                try:
                    fixed = json.loads(escape_unescaped_newlines(cleaned))
                except Exception:
                    fixed = repair_json(cleaned) or repair_json(raw)

        if not fixed:
            fixed = extract_code_from_markdown(raw)

        if not fixed:
            fixed = repair_json(cleaned) or repair_json(raw) or extract_code_from_markdown(cleaned)

        if not isinstance(fixed, dict):
            raise ValueError(f"Fixer output is not a dict: {type(fixed)}")

        # Merge fixes back — don't lose files the fixer didn't touch
        state["code"] = safe_dict_merge(state["code"], fixed)
        save_checkpoint(state, "post_fixer")
        log("fixer", f"Applied fixes to: {list(fixed.keys())} ✓", "success")

    except Exception as e:
        err = f"[fixer] failed: {e}"
        log("fixer", err, "error")
        state["error_log"] = ((state.get("error_log") or []) + [err])[-20:]
        if "exhausted" in str(e):
            state["fatal_error"] = True

    # Always increment iteration to prevent infinite tester⇆fixer loops
    state["iteration"] = state.get("iteration", 0) + 1

    return state
