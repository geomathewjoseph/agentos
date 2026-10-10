"""Structured logging and metrics tracking for AgentOS.

Provides Rich-formatted console output and per-provider success/failure
metrics tracking for monitoring API usage and reliability.
"""
import sys
import time
from collections import defaultdict
import threading
from rich.console import Console
from rich.panel import Panel

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

_console = Console()
_metrics = defaultdict(lambda: {"success": 0, "failure": 0, "total_time": 0.0})
_start_times = {}

_ui_log_queue = []
_ui_log_lock = threading.Lock()

def pop_ui_logs():
    with _ui_log_lock:
        logs = _ui_log_queue[:]
        _ui_log_queue.clear()
        return logs



def log(source: str, message: str, level: str = "info"):
    """Log a message with Rich formatting.
    
    Args:
        source: Component name (e.g., 'planner', 'coder', 'fallback')
        message: Log message
        level: Log level — 'info', 'warning', 'error', 'success'
    """
    colors = {
        "info":    "cyan",
        "warning": "yellow",
        "error":   "red",
        "success": "green",
    }
    color = colors.get(level, "white")
    icon  = {"info": "ℹ", "warning": "⚠", "error": "✗", "success": "✓"}.get(level, "•")
    timestamp = time.strftime("%H:%M:%S")
    _console.print(
        f"[dim]{timestamp}[/dim] [{color}]{icon} [{source}][/{color}] {message}"
    )
    with _ui_log_lock:
        _ui_log_queue.append({
            "source": source,
            "message": message,
            "level": level,
            "timestamp": timestamp
        })


def track_metric(provider: str, task: str, success: bool, attempt: int = 0):
    """Track a provider call metric.
    
    Args:
        provider: Provider name (e.g., 'groq', 'cerebras')
        task: Task type (e.g., 'coding', 'review')
        success: Whether the call succeeded
        attempt: Attempt index in the fallback chain
    """
    key = f"{provider}/{task}"
    if success:
        _metrics[key]["success"] += 1
    else:
        _metrics[key]["failure"] += 1


def get_metrics() -> dict:
    """Return all tracked metrics."""
    return dict(_metrics)


def print_metrics_summary():
    """Print a formatted summary of all provider metrics."""
    if not _metrics:
        log("metrics", "No API calls tracked yet.")
        return

    lines = []
    for key, data in sorted(_metrics.items()):
        total = data["success"] + data["failure"]
        rate  = (data["success"] / total * 100) if total > 0 else 0
        lines.append(
            f"  {key}: {data['success']}/{total} "
            f"({rate:.0f}% success)"
        )

    _console.print(Panel.fit(
        "\n".join(lines),
        title="📊 Provider Metrics",
        border_style="cyan",
    ))


def print_stage_banner(stage: str, iteration: int = 0, max_iter: int = 0):
    """Print a prominent stage banner."""
    iter_str = f" — iteration {iteration}/{max_iter}" if max_iter > 0 else ""
    _console.print(f"\n[bold blue]{'='*60}[/bold blue]")
    _console.print(f"[bold blue]  🔧 {stage.upper()}{iter_str}[/bold blue]")
    _console.print(f"[bold blue]{'='*60}[/bold blue]")
