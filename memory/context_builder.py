"""Context Builder — Phase-aware RAG context retrieval for AgentOS agents.

Retrieves relevant past context for each agent phase from ChromaDB
and saves new context after each phase completes.
"""
from __future__ import annotations

from memory.chroma_store import store, query
from tools.logger import log


def get_context(phase: str, current_input: str, n_results: int = 3) -> str:
    """Retrieve relevant context for a pipeline phase.
    
    Args:
        phase: Pipeline phase name (e.g., 'planning', 'architecture', 'coding')
        current_input: Current input text to find similar past context for
        n_results: Number of past contexts to retrieve
    
    Returns:
        Formatted string of relevant past contexts, or empty string
    """
    try:
        results = query(phase, current_input, n=n_results)
        if not results:
            return ""

        context_parts = []
        for i, doc in enumerate(results, 1):
            # Truncate each result to avoid overwhelming the prompt
            truncated = doc[:2000] if len(doc) > 2000 else doc
            context_parts.append(f"--- Past Context {i} ---\n{truncated}")

        context = "\n\n".join(context_parts)
        log("context_builder",
            f"Retrieved {len(results)} past contexts for '{phase}'",
            "info")
        return context

    except Exception as e:
        log("context_builder",
            f"Failed to retrieve context for '{phase}': {e}",
            "warning")
        return ""


def save_context(phase: str, content: str, metadata: dict | None = None):
    """Save context from a completed phase for future retrieval.
    
    Args:
        phase: Pipeline phase name
        content: Content to store (e.g., a plan, architecture doc, code listing)
        metadata: Optional metadata (e.g., goal, iteration)
    """
    if metadata is None:
        metadata = {}

    try:
        # Truncate very long content to keep storage manageable
        if len(content) > 10000:
            content = content[:10000] + "\n... [truncated for storage]"

        metadata["phase"] = phase
        store(phase, content, metadata)
        log("context_builder",
            f"Saved context for '{phase}' ({len(content)} chars)",
            "info")

    except Exception as e:
        log("context_builder",
            f"Failed to save context for '{phase}': {e}",
            "warning")
