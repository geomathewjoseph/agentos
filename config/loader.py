"""Configuration loader for AgentOS model registry."""
from __future__ import annotations

import os
import yaml

_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_CONFIG_DIR, "thresholds.yaml")) as f:
    THRESHOLDS = yaml.safe_load(f)

# Cache models config — only loaded once per process
_MODEL_CONFIG: dict | None = None


def _load_models() -> dict:
    global _MODEL_CONFIG
    if _MODEL_CONFIG is None:
        with open(os.path.join(_CONFIG_DIR, "models.yaml")) as f:
            _MODEL_CONFIG = yaml.safe_load(f)
    return _MODEL_CONFIG


def reload_models() -> dict:
    """Force-reload models.yaml from disk (used after UI config updates)."""
    global _MODEL_CONFIG
    with open(os.path.join(_CONFIG_DIR, "models.yaml")) as f:
        _MODEL_CONFIG = yaml.safe_load(f)
    return _MODEL_CONFIG


def get_provider_name(task: str, attempt: int) -> str:
    """Get the provider name for a given task and attempt index."""
    cfg = _load_models()
    chain = cfg["models"][task]["chain"]
    if attempt < len(chain):
        return chain[attempt]["provider"]
    return "unknown"


def get_model_config() -> dict:
    """Return the full models configuration."""
    return _load_models()


def get_thresholds() -> dict:
    """Return the full thresholds configuration."""
    return THRESHOLDS
