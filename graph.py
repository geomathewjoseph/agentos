"""LangGraph State Machine — Core orchestration for AgentOS.

Defines the multi-agent pipeline as a compiled LangGraph state machine
with conditional routing based on review scores and test results.

Pipeline: planner → architect → test_writer → coder → reviewer → tester → fixer
With restart, escalation, and human approval gates.
"""

from __future__ import annotations

import os
import sys
import shutil
import yaml

from typing import TypedDict, List, Optional, Literal
from langgraph.graph import StateGraph, START, END
from agents.planner import run_planner
from agents.architect import run_architect
from agents.test_writer import run_test_writer
from agents.coder import run_coder
from agents.reviewer import run_reviewer
from agents.tester import run_tester
from agents.fixer import run_fixer
from tools.checkpoint import save_checkpoint
from tools.logger import log

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
with open(os.path.join(_CONFIG_DIR, "thresholds.yaml")) as f:
    _T = yaml.safe_load(f)

MIN_SCORE = _T["review"]["min_score"]
LOW_SCORE_ARCH = _T["review"]["low_score_arch"]


class AgentState(TypedDict):
    """Full pipeline state passed between all agents."""

    goal: str
    sanitised_goal: str
    plan: Optional[str]
    architecture: Optional[str]
    test_spec: Optional[dict]
    code: Optional[dict]
    review_scores: Optional[dict]
    review_feedback: Optional[List[str]]
    test_results: Optional[dict]
    prev_test_errors: List[str]
    iteration: int
    global_iteration: int
    max_iterations: int
    max_global_iterations: int
    last_stage: Optional[str]
    error_log: List[str]
    fatal_error: bool
    status: str


# ── Routing functions ─────────────────────────────────────────────────────────────


def route_after_plan(state: AgentState) -> Literal["architect", "restart", "escalate"]:
    """Route after planning: proceed, restart, or escalate."""
    if state.get("fatal_error"):
        return "escalate"
    if not state.get("plan"):
        if state["global_iteration"] < state["max_global_iterations"]:
            return "restart"
        return "escalate"
    return "architect"


def route_after_review(
    state: AgentState,
) -> Literal["rearchitect", "recode", "test", "restart", "escalate"]:
    """Route after review: rearchitect, recode, or proceed to test."""
    if state.get("fatal_error"):
        return "escalate"
    if not state.get("architecture"):
        log("graph", "Architecture missing — restarting", "warning")
        if state["global_iteration"] < state["max_global_iterations"]:
            return "restart"
        return "escalate"

    scores = state.get("review_scores") or {}
    if not scores:
        if state["iteration"] < state["max_iterations"]:
            return "recode"
        elif state["global_iteration"] < state["max_global_iterations"]:
            return "restart"
        return "escalate"

    min_s = min(scores.values())

    if min_s < LOW_SCORE_ARCH:
        log("graph", f"Score {min_s} < {LOW_SCORE_ARCH} — back to architect", "warning")
        # run_architect now increments state["iteration"], so this guard terminates
        if state["iteration"] < state["max_iterations"]:
            return "rearchitect"
        elif state["global_iteration"] < state["max_global_iterations"]:
            return "restart"
        return "escalate"

    if min_s < MIN_SCORE:
        if state["iteration"] < state["max_iterations"]:
            return "recode"
        elif state["global_iteration"] < state["max_global_iterations"]:
            return "restart"
        return "escalate"

    return "test"


def route_after_test(
    state: AgentState,
) -> Literal["fix", "approve", "restart", "escalate"]:
    """Route after testing: fix, approve, restart, or escalate."""
    if state.get("fatal_error"):
        return "escalate"
    results = state.get("test_results") or {}
    if results.get("passed"):
        return "approve"
    if state["iteration"] < state["max_iterations"]:
        return "fix"
    if state["global_iteration"] < state["max_global_iterations"]:
        return "restart"
    return "escalate"


# ── Special nodes ────────────────────────────────────────────────────────────────


def restart_pipeline(state: AgentState) -> AgentState:
    """Reset pipeline state for a fresh run, preserving error history."""
    state["global_iteration"] += 1
    state["iteration"] = 0
    state["plan"] = None
    state["architecture"] = None
    state["test_spec"] = None
    state["code"] = None
    state["review_scores"] = None
    state["review_feedback"] = None
    state["test_results"] = None
    state["prev_test_errors"] = []
    state["status"] = "planning"
    state["fatal_error"] = False
    log(
        "graph",
        f"=== RESTART {state['global_iteration']}/{state['max_global_iterations']} ===",
        "warning",
    )
    save_checkpoint(state, "restart")
    return state


def escalate_to_human(state: AgentState) -> AgentState:
    """Escalate to human when all recovery options are exhausted."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    errors = (state.get("error_log") or [])[-10:]
    console.print(
        Panel.fit(
            f"[bold red]ESCALATION — pipeline exhausted all recovery options.[/bold red]\n\n"
            f"[yellow]Goal:[/yellow] {state['goal']}\n"
            f"[yellow]Global iterations:[/yellow] {state['global_iteration']}\n"
            f"[yellow]Last stage:[/yellow] {state.get('last_stage', 'unknown')}\n\n"
            f"[yellow]Last errors:[/yellow]\n"
            + "\n".join(f"  • {e[:120]}" for e in errors)
            + "\n\n[cyan]State saved to: checkpoints/escalation_state.json[/cyan]",
            title="🚨 Human Intervention Required",
        )
    )
    save_checkpoint(state, "escalation")
    state["status"] = "escalated"
    return state


def human_approval_gate(state: AgentState) -> AgentState:
    """Interactive human approval before writing output files."""
    from rich.console import Console

    console = Console()
    scores = state.get("review_scores") or {}
    console.print(f"\n[bold green]✓ Tests passed.[/bold green] Scores: {scores}")
    console.print(f"  Files: {list((state.get('code') or {}).keys())}")

    # Auto-approve in web mode, non-interactive mode, or when explicitly set
    auto_approve = (
        os.environ.get("AGENTOS_WEB_MODE") == "1"
        or os.environ.get("AGENTOS_AUTO_APPROVE") == "1"
        or not sys.stdin.isatty()
    )

    if auto_approve:
        console.print("[cyan]Auto-approving output (non-interactive mode)[/cyan]")
        _write_output(state["code"])
        state["status"] = "done"
        save_checkpoint(state, "final")
        return state

    decision = input("\nApprove and write to ./output/? (yes/no): ").strip().lower()
    if decision == "yes":
        _write_output(state["code"])
        state["status"] = "done"
    else:
        state["status"] = "rejected"
    save_checkpoint(state, "final")
    return state


def _write_output(code: dict):
    """Write all generated code files to the output directory, cleaning stale files first."""
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

    # Clean old run files from output directory (preserving .git if present)
    if os.path.exists(output_dir):
        for item in os.listdir(output_dir):
            if item in (".git", ".gitignore"):
                continue
            item_path = os.path.join(output_dir, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)
                else:
                    os.remove(item_path)
            except Exception:
                pass
    os.makedirs(output_dir, exist_ok=True)

    ignored_patterns = {
        "dockerfile", "docker-compose", "mkdocs", "license",
        "codeowners", ".flake8", "pull_request_template",
        ".github", ".vscode"
    }

    written_count = 0
    for fname, content in code.items():
        base = os.path.basename(fname).lower()
        if any(ign in base for ign in ignored_patterns):
            continue
        path = os.path.join(output_dir, fname)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written_count += 1
    log("graph", f"Output written to ./output/ ({written_count} files)", "success")



# ── Graph assembly ──────────────────────────────────────────────────────────────


def build_graph():
    """Assemble and compile the LangGraph state machine."""
    g = StateGraph(AgentState)

    # Add all nodes
    g.add_node("planner", run_planner)
    g.add_node("architect", run_architect)
    g.add_node("test_writer", run_test_writer)
    g.add_node("coder", run_coder)
    g.add_node("reviewer", run_reviewer)
    g.add_node("tester", run_tester)
    g.add_node("fixer", run_fixer)
    g.add_node("restart", restart_pipeline)
    g.add_node("escalate", escalate_to_human)
    g.add_node("human_approval", human_approval_gate)

    # Entry point
    g.add_edge(START, "planner")

    # Conditional routing after planner
    g.add_conditional_edges(
        "planner",
        route_after_plan,
        {
            "architect": "architect",
            "restart": "restart",
            "escalate": "escalate",
        },
    )

    # Linear edges
    g.add_edge("architect", "test_writer")
    g.add_edge("test_writer", "coder")
    g.add_edge("coder", "reviewer")

    # Conditional routing after reviewer
    g.add_conditional_edges(
        "reviewer",
        route_after_review,
        {
            "rearchitect": "architect",
            "recode": "coder",
            "test": "tester",
            "restart": "restart",
            "escalate": "escalate",
        },
    )

    # Conditional routing after tester
    g.add_conditional_edges(
        "tester",
        route_after_test,
        {
            "fix": "fixer",
            "approve": "human_approval",
            "restart": "restart",
            "escalate": "escalate",
        },
    )

    # Fixer always goes back to tester
    g.add_edge("fixer", "tester")

    # Restart goes back to planner
    g.add_edge("restart", "planner")

    # Terminal nodes
    g.add_edge("escalate", END)
    g.add_edge("human_approval", END)

    return g.compile()
