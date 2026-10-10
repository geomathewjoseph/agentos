"""Checkpoint Manager — Save/load pipeline state for crash recovery.

All state is serialized to JSON files in the checkpoints/ directory.
Enables resume after crashes and provides state history for debugging.
"""

from __future__ import annotations

import os
import json
import time
from tools.logger import log

CHECKPOINT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "checkpoints"
)

MAX_STATE_SIZE = 500_000  # 500KB per field max
MAX_LIST_SIZE = 100  # Max items in lists


def save_checkpoint(state: dict, label: str = "auto"):
    """Save pipeline state to a JSON checkpoint file.

    Args:
        state: The full AgentState dictionary
        label: Descriptive label for the checkpoint (e.g., 'post_plan', 'post_coder')
    """
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"checkpoint_{label}_{timestamp}.json"
    filepath = os.path.join(CHECKPOINT_DIR, filename)

    # Also save as "latest" for easy resume
    latest_path = os.path.join(CHECKPOINT_DIR, "latest.json")

    try:
        # Make state JSON-serializable with size limits
        serializable = _make_serializable(state)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        log("checkpoint", f"State saved: {filename}")
        prune_old_checkpoints(keep=25)
    except Exception as e:
        log("checkpoint", f"Failed to save checkpoint: {e}", "error")


def prune_old_checkpoints(keep: int = 25) -> int:
    """Keep the latest N timestamped checkpoints and delete older ones to save disk space."""
    if not os.path.exists(CHECKPOINT_DIR):
        return 0

    files = []
    for f in os.listdir(CHECKPOINT_DIR):
        if f.startswith("checkpoint_") and f.endswith(".json") and f != "latest.json":
            path = os.path.join(CHECKPOINT_DIR, f)
            try:
                files.append((os.path.getmtime(path), path))
            except OSError:
                pass

    files.sort(key=lambda x: x[0], reverse=True)
    deleted = 0
    for _, path in files[keep:]:
        try:
            os.remove(path)
            deleted += 1
        except Exception:
            pass
    if deleted > 0:
        log("checkpoint", f"Pruned {deleted} old checkpoint(s) (kept {keep})", "info")
    return deleted



def load_checkpoint(label: str = "latest") -> dict | None:
    """Load a checkpoint file.

    Args:
        label: 'latest' for the most recent, or a specific checkpoint filename

    Returns:
        The state dict if found, None otherwise
    """
    if label == "latest":
        filepath = os.path.join(CHECKPOINT_DIR, "latest.json")
    else:
        filepath = os.path.join(CHECKPOINT_DIR, label)

    if not os.path.exists(filepath):
        log("checkpoint", f"No checkpoint found at {filepath}", "warning")
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            state = json.load(f)
        log("checkpoint", f"State loaded from {os.path.basename(filepath)}")
        return state
    except Exception as e:
        log("checkpoint", f"Failed to load checkpoint: {e}", "error")
        return None


def _make_serializable(obj, _depth=0):
    """Recursively convert an object to JSON-serializable form with size limits."""
    if _depth > 10:
        return "<max_depth>"

    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            # Truncate large fields
            serialized = _make_serializable(v, _depth + 1)
            if isinstance(serialized, str) and len(serialized) > MAX_STATE_SIZE:
                result[k] = (
                    serialized[:MAX_STATE_SIZE]
                    + f"... [truncated {len(serialized)} chars]"
                )
            else:
                result[k] = serialized
        return result
    if isinstance(obj, (list, tuple)):
        return [
            _make_serializable(item, _depth + 1) for item in obj[:MAX_LIST_SIZE]
        ]  # Limit list size
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)
