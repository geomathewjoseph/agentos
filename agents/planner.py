"""Planner Agent — Senior software project planner.

Uses DeepSeek-R1 to produce structured development plans with tasks,
acceptance criteria, dependencies, and risks. Includes prompt-injection
sanitization for user-supplied goals.
"""
from __future__ import annotations

from router.fallback_chain import with_fallback
from memory.context_builder import get_context, save_context
from tools.checkpoint import save_checkpoint
from tools.token_counter import count_tokens, truncate_to_fit
from tools.logger import log, print_stage_banner
import re

PROMPT = """
You are a pragmatic, senior software project planner.

Produce a focused, lean development plan for the goal below.
CRITICAL GUIDELINES:
1. FOCUS ON CORE VALUE: Focus strictly on the core functional code needed to achieve the goal. Do NOT plan multi-sprint enterprise roadmaps, DevOps/CI/CD pipelines, Helm charts, Docker setups, or documentation sites unless explicitly requested in the goal.
2. LEAN SCOPE: Keep tasks (3 to 5 tasks max) and Acceptance Criteria (3 to 5 criteria max) concise, practical, and testable.
3. CONSOLIDATED TESTS: The test engineer will write 1 focused test file covering the criteria.

## Tasks
## Acceptance Criteria
## Dependencies
## Risks

Goal: {goal}

Context from previous runs (learn from these failures):
{context}
"""



def _sanitise(goal: str) -> str:
    """Strip prompt-injection attempts from user-supplied goal."""
    goal = goal.replace("{", "{{").replace("}", "}}")
    for pattern in ("ignore previous", "ignore all", "disregard",
                    "system prompt", "jailbreak"):
        goal = re.sub(pattern, "[removed]", goal, flags=re.IGNORECASE)
    return goal.strip()


def run_planner(state: dict) -> dict:
    """Execute the planning phase."""
    print_stage_banner("Planner", state.get("global_iteration", 0),
                       state.get("max_global_iterations", 3))
    log("planner", f"Planning — global iteration {state['global_iteration']}")
    state["last_stage"]     = "planner"
    state["sanitised_goal"] = _sanitise(state["goal"])

    prev_errors = "\n".join((state.get("error_log") or [])[-5:])
    raw_context = get_context("planning", state["sanitised_goal"])
    context     = (f"Previous errors:\n{prev_errors}\n\n{raw_context}"
                   if prev_errors else raw_context)

    prompt = PROMPT.format(goal=state["sanitised_goal"], context=context)
    prompt = truncate_to_fit(prompt, 1800)

    try:
        result = with_fallback("planning", prompt)
        if len(result.strip()) < 50:
            raise ValueError("Plan too short — likely a model refusal or empty output")
        state["plan"] = result
        save_context("planning", result, {"goal": state["sanitised_goal"]})
        save_checkpoint(state, "post_plan")
        log("planner", "Plan ready ✓", "success")
    except Exception as e:
        err = f"[planner] failed: {e}"
        log("planner", err, "error")
        state["error_log"] = (state.get("error_log") or []) + [err]
        if "exhausted" in str(e):
            state["fatal_error"] = True
        state["plan"] = None

    return state
