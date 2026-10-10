"""LLM Router — Provider registry and LLM factory for AgentOS.

Supports 8 free cloud providers with OpenAI-compatible APIs.
"""
from __future__ import annotations

import os
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

from config.loader import get_model_config

load_dotenv()

# All OpenAI-compatible providers — only base_url + env key differ
COMPAT_PROVIDERS = {
    "openrouter":  {"base_url": "https://openrouter.ai/api/v1",            "env": "OPENROUTER_API_KEY"},
    "cerebras":    {"base_url": "https://api.cerebras.ai/v1",              "env": "CEREBRAS_API_KEY"},
    "sambanova":   {"base_url": "https://api.sambanova.ai/v1",             "env": "SAMBANOVA_API_KEY"},
    "fireworks":   {"base_url": "https://api.fireworks.ai/inference/v1",   "env": "FIREWORKS_API_KEY"},
    "novita":      {"base_url": "https://api.novita.ai/v3/openai",         "env": "NOVITA_API_KEY"},
    "huggingface": {"base_url": "https://api-inference.huggingface.co/v1", "env": "HF_API_KEY"},
}


TASK_MAX_TOKENS = {
    "review": 1024,
    "planning": 2048,
    "architecture": 2048,
    "coding": 4096,
    "fixing": 4096,
    "documentation": 2048,
}



def get_llm(task: str, attempt: int = 0):
    """Create an LLM instance for the given task and attempt index."""
    cfg = get_model_config()
    chain = cfg["models"][task]["chain"]
    if attempt >= len(chain):
        raise RuntimeError(f"All {len(chain)} providers exhausted for task '{task}'")

    entry    = chain[attempt]
    provider = entry["provider"]
    model    = entry["model"]
    max_tokens = TASK_MAX_TOKENS.get(task, 2048)

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("Missing env var GROQ_API_KEY for provider 'groq'")
        extra_kwargs = {}
        if "gpt-oss" in model:
            extra_kwargs["reasoning_format"] = "parsed"
        return ChatGroq(model=model, api_key=api_key, temperature=0.2, max_retries=0, timeout=45, max_tokens=max_tokens, **extra_kwargs)

    if provider == "google":
        api_key = os.getenv("GOOGLE_AI_API_KEY")
        if not api_key:
            raise ValueError("Missing env var GOOGLE_AI_API_KEY for provider 'google'")
        return ChatGoogleGenerativeAI(
            model=model, google_api_key=api_key, temperature=0.2, max_retries=0, timeout=45, max_tokens=max_tokens
        )

    if provider in COMPAT_PROVIDERS:
        compat_cfg = COMPAT_PROVIDERS[provider]
        key = os.getenv(compat_cfg["env"])
        if not key:
            raise ValueError(f"Missing env var {compat_cfg['env']} for provider '{provider}'")
        return ChatOpenAI(
            model=model, api_key=key, base_url=compat_cfg["base_url"], temperature=0.2, max_retries=0, timeout=45, max_tokens=max_tokens
        )

    raise ValueError(f"Unknown provider: '{provider}'")


def get_chain_length(task: str) -> int:
    """Return the number of providers available for a given task."""
    cfg = get_model_config()
    return len(cfg["models"][task]["chain"])
