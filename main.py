"""AgentOS — Entry point for the multi-agent AI software company.

Usage:
    python main.py                    # Start fresh
    python main.py --resume           # Resume from last checkpoint
    python main.py --goal "Build X"   # Start with a specific goal
"""
import sys
import argparse
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from graph import build_graph, AgentState
from tools.checkpoint import load_checkpoint
from tools.logger import log, print_metrics_summary
import yaml
import os

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

console = Console()

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
with open(os.path.join(_CONFIG_DIR, "thresholds.yaml")) as f:
    _T = yaml.safe_load(f)


def _print_banner():
    """Print the AgentOS startup banner."""
    banner = Text()
    banner.append("\n")
    banner.append("  ██████╗  ███████╗███████╗███╗   ██╗████████╗ ██████╗ ███████╗\n", style="bold cyan")
    banner.append("  ██╔═══██╗██╔════╝██╔════╝████╗  ██║╚══██╔══╝██╔═══██╗██╔════╝\n", style="bold cyan")
    banner.append("  ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ██║   ██║███████╗\n", style="bold cyan")
    banner.append("  ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ██║   ██║╚════██║\n", style="bold cyan")
    banner.append("  ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ╚██████╔╝███████║\n", style="bold cyan")
    banner.append("  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚══════╝\n", style="bold cyan")
    banner.append("\n  Multi-Agent AI Software Company in a Box\n", style="dim")
    console.print(banner)


def _create_initial_state(goal: str) -> dict:
    """Create the initial pipeline state."""
    return {
        "goal":                  goal,
        "sanitised_goal":        "",
        "plan":                  None,
        "architecture":          None,
        "test_spec":             None,
        "code":                  None,
        "review_scores":         None,
        "review_feedback":       None,
        "test_results":          None,
        "prev_test_errors":      [],
        "iteration":             0,
        "global_iteration":      0,
        "max_iterations":        _T["loop"]["max_iterations"],
        "max_global_iterations": _T["loop"]["max_global_iterations"],
        "last_stage":            None,
        "error_log":             [],
        "fatal_error":           False,
        "status":                "starting",
    }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AgentOS — Multi-Agent AI Software Company"
    )
    parser.add_argument(
        "--goal", type=str, default=None,
        help="Product goal to build"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from the last checkpoint"
    )
    parser.add_argument(
        "--auto-approve", action="store_true",
        help="Automatically approve and write output files upon passing tests"
    )
    parser.add_argument(
        "--bypass-rate-limits", action="store_true",
        help="Enable emergency bypass mode if cloud API rate limits are saturated"
    )
    args = parser.parse_args()

    if args.auto_approve:
        os.environ["AGENTOS_AUTO_APPROVE"] = "1"
    if args.bypass_rate_limits:
        os.environ["AGENTOS_BYPASS_RATE_LIMIT"] = "1"

    _print_banner()

    # Resume from checkpoint
    if args.resume:
        state = load_checkpoint("latest")
        if state:
            console.print(
                f"[green]✓ Resumed from checkpoint.[/green] "
                f"Last stage: {state.get('last_stage', 'unknown')}, "
                f"Iteration: {state.get('iteration', 0)}, "
                f"Global: {state.get('global_iteration', 0)}"
            )
        else:
            console.print("[red]No checkpoint found. Starting fresh.[/red]")
            args.resume = False

    if not args.resume:
        # Get goal from argument or prompt
        goal = args.goal
        if not goal:
            console.print(
                Panel.fit(
                    "[bold]What would you like to build?[/bold]\n\n"
                    "[dim]Example: Create a REST API for a todo app with "
                    "authentication, CRUD operations, and SQLite storage.[/dim]",
                    title="🎯 Product Goal",
                    border_style="cyan",
                )
            )
            goal = input("\n▶ Goal: ").strip()
            if not goal:
                console.print("[red]No goal provided. Exiting.[/red]")
                sys.exit(1)

        state = _create_initial_state(goal)
        console.print(f"\n[cyan]Goal:[/cyan] {goal}")
        console.print(
            f"[dim]Max iterations: {state['max_iterations']} per pass, "
            f"{state['max_global_iterations']} global restarts[/dim]\n"
        )

    # Build and run the graph
    try:
        graph = build_graph()
        log("main", "LangGraph state machine compiled ✓", "success")

        result = graph.invoke(state)

        # Display final status
        status = result.get("status", "unknown")
        console.print(f"\n{'='*60}")
        if status == "done":
            console.print(
                Panel.fit(
                    f"[bold green]✓ COMPLETE[/bold green]\n\n"
                    f"Files written to ./output/\n"
                    f"Review scores: {result.get('review_scores', {})}\n"
                    f"Total iterations: {result.get('iteration', 0)}\n"
                    f"Global restarts: {result.get('global_iteration', 0)}",
                    title="🎉 Success",
                    border_style="green",
                )
            )
        elif status == "rejected":
            console.print("[yellow]Output rejected by user. State saved.[/yellow]")
        elif status == "escalated":
            console.print("[red]Pipeline escalated. See error report above.[/red]")
        else:
            console.print(f"[yellow]Pipeline ended with status: {status}[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. State auto-saved.[/yellow]")
    except Exception as e:
        log("main", f"Fatal error: {e}", "error")
        console.print(f"\n[red]Fatal error: {e}[/red]")
        console.print("[dim]Try: python main.py --resume[/dim]")
    finally:
        print_metrics_summary()


if __name__ == "__main__":
    main()
