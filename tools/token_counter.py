"""Token Budget Guard — tiktoken-based prompt size management.

Ensures prompts fit within model context windows and provides
truncation utilities when they don't.
"""
from __future__ import annotations

import os
import yaml
import tiktoken
from tools.logger import log

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
with open(os.path.join(_CONFIG_DIR, "thresholds.yaml")) as f:
    _THR = yaml.safe_load(f)

_WINDOWS  = _THR["tokens"]["model_context_windows"]
_FRACTION = _THR["tokens"]["max_prompt_fraction"]
_ENC      = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string."""
    return len(_ENC.encode(text))


def get_context_limit(model: str) -> int:
    """Get the context window size for a model."""
    return _WINDOWS.get(model, _WINDOWS["default"])


def fits_in_context(prompt: str, model: str, reserve_for_output: int = 4096) -> bool:
    """Check if a prompt fits within a model's safe context limit.
    
    Args:
        prompt: The prompt text to check
        model: Model name (used to look up context window)
        reserve_for_output: Tokens to reserve for the model's response
    
    Returns:
        True if the prompt fits, False if it needs splitting/truncation
    """
    limit    = get_context_limit(model)
    safe_max = int(limit * _FRACTION) - reserve_for_output
    tokens   = count_tokens(prompt)
    if tokens > safe_max:
        log("token_counter",
            f"Prompt is {tokens} tokens, safe max is {safe_max} for '{model}'. Will split.",
            "warning")
        return False
    return True


def truncate_to_fit(text: str, max_tokens: int) -> str:
    """Hard-truncate a block of text to fit within max_tokens."""
    tokens = _ENC.encode(text)
    if len(tokens) <= max_tokens:
        return text
    log("token_counter", f"Truncating {len(tokens)} → {max_tokens} tokens", "warning")
    return _ENC.decode(tokens[:max_tokens])
