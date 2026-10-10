"""Architect Agent — Senior software architect.

Uses Llama 3.3 70B to design full system architecture including
file structure, tech stack, data models, API contracts, and security.
"""

from __future__ import annotations

from router.fallback_chain import with_fallback
from memory.context_builder import get_context, save_context
from tools.checkpoint import save_checkpoint
from tools.token_counter import truncate_to_fit
from tools.logger import log, print_stage_banner

PROMPT = """
You are a pragmatic, senior software architect adhering strictly to KISS and YAGNI principles.

Design a clean, minimal system architecture for the plan below.

STRICT ARCHITECTURAL RULES:
1. MINIMAL VIABLE ARCHITECTURE: Keep the project to the absolute minimum number of files (typically 1 to 3 core files + 1 test file). Consolidate related logic rather than creating micro-files. Do NOT split a small feature across 10 folders.
2. ZERO BOILERPLATE: STRICTLY FORBIDDEN to include:
   - CI/CD files (.github/, actions, etc.)
   - Documentation frameworks (mkdocs, sphinx, docs/ directory)
   - Repository templates (CODEOWNERS, LICENSE, PULL_REQUEST_TEMPLATE, etc.)
   - Containerization or orchestration (Dockerfile, docker-compose, helm) unless EXPLICITLY requested in the plan.
   - Micro-file fragmentation: Do NOT create separate files for trivial constants, helpers, utils, or config if they can live directly in the module that uses them.
3. CLEAR FILE MANIFEST: You MUST include a "## File Manifest" section listing ONLY the essential files with markdown backticks. The coder will ONLY generate files in this list.

Required output format:
## Architecture Overview
(Brief, practical explanation of the system design)

## Tech Stack & Dependencies
(Minimal libraries and requirements)

## File Manifest
(Bullet list of ONLY the core files in markdown backticks, e.g.:
- `main.py`
- `tests/test_main.py`
)

Plan:
{plan}

Previous architecture context:
{context}
"""



def run_architect(state: dict) -> dict:
    """Execute the architecture design phase."""
    print_stage_banner("Architect")
    log("architect", "Designing architecture")

    # Save previous stage before overwriting
    prev_stage = state.get("last_stage")

    if not state.get("plan"):
        state["architecture"] = None
        state["last_stage"] = "architect"
        return state

    context = get_context("architecture", state["plan"])
    prompt = PROMPT.format(plan=state["plan"], context=context)
    prompt = truncate_to_fit(prompt, 2500)

    try:
        result = with_fallback("architecture", prompt)
        if len(result.strip()) < 50:
            raise ValueError("Architecture output too short")
        state["architecture"] = result
        save_context("architecture", result, {"goal": state.get("sanitised_goal", "")})
        save_checkpoint(state, "post_architect")
        log("architect", "Architecture ready ✓", "success")
    except Exception as e:
        err = f"[architect] failed: {e}"
        log("architect", err, "error")
        state["error_log"] = ((state.get("error_log") or []) + [err])[-20:]
        if "exhausted" in str(e):
            state["fatal_error"] = True
        state["architecture"] = None

    # Only increment iteration when re-entering architect from reviewer (not on first run from planner),
    # so the rearchitect loop guard in route_after_review eventually trips.
    state["last_stage"] = "architect"
    if prev_stage != "planner":
        state["iteration"] = state.get("iteration", 0) + 1

    return state
