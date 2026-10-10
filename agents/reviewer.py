"""Reviewer Panel — Unified multi-perspective code review.

Evaluates code across Security, Code Quality, and Performance dimensions
in a single consolidated LLM call to conserve API tokens and prevent quota exhaustion.
"""

from __future__ import annotations

import json
from router.fallback_chain import with_fallback
from tools.error_handler import repair_json, clean_llm_output, escape_unescaped_newlines
from tools.checkpoint import save_checkpoint
from tools.token_counter import truncate_to_fit
from tools.logger import log, print_stage_banner

PROMPT = """
You are a senior code review panel combining three perspectives: Security Auditor, Code Quality Expert, and Performance Engineer.

Code under review:
{code}

Evaluate the code thoroughly across quality, security, and performance.
CRITICAL CHECKS:
1. Completeness: Are there any placeholders, TODOs, pass statements, or unfinished logic? If yes, score quality < 50 and report in issues.
2. Bloat: Are there unnecessary boilerplate files, dummy helper wrappers, or redundant scaffolding?
3. Robustness: Are edge cases and error handling properly implemented? Do imports match across files?

Return ONLY this JSON — no preamble, no markdown fences:
{{
  "quality":     <int 0-100>,
  "security":    <int 0-100>,
  "performance": <int 0-100>,
  "issues":      ["specific issue 1", "specific issue 2"]
}}
"""

ROLES = ["Security Auditor", "Code Quality Expert", "Performance Engineer"]


def run_reviewer(state: dict) -> dict:
    """Execute the review panel in a single combined call to save API tokens."""
    print_stage_banner("Reviewer Panel")
    log("reviewer", "Combined review panel starting (Security, Quality, Performance)")
    state["last_stage"] = "reviewer"

    if not state.get("code"):
        state["review_scores"] = None
        state["review_feedback"] = ["No code produced"]
        return state

    code_str = "\n\n".join(f"### {k}\n```\n{v}\n```" for k, v in state["code"].items())
    code_str = truncate_to_fit(code_str, 3500)

    prompt = PROMPT.format(code=code_str)


    try:
        raw = with_fallback("review", prompt)
        raw = clean_llm_output(raw)
        raw = escape_unescaped_newlines(raw)
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = repair_json(raw) or {}

        consensus = {}
        for key in ("quality", "security", "performance"):
            val = result.get(key)
            if isinstance(val, (int, float)) and 0 <= val <= 100:
                consensus[key] = int(val)
            else:
                consensus[key] = 75

        issues = result.get("issues", [])
        if not isinstance(issues, list):
            issues = [str(issues)] if issues else []

        state["review_scores"] = consensus
        state["review_feedback"] = list(dict.fromkeys(issues))
        save_checkpoint(state, "post_review")
        log("reviewer", f"Consensus scores: {consensus} ✓", "success")
    except Exception as e:
        err = f"[reviewer] failed: {e}"
        log("reviewer", err, "error")
        state["error_log"] = ((state.get("error_log") or []) + [err])[-20:]
        if "exhausted" in str(e):
            state["fatal_error"] = True
        state["review_scores"] = {"quality": 50, "security": 50, "performance": 50}
        state["review_feedback"] = [f"Review error: {e}"]
        raise

    return state

