"""Coder Agent — Senior software engineer.

Uses Qwen2.5-Coder for token-budgeted, per-file code generation.
Automatically splits generation when prompts exceed model context limits.
"""

from __future__ import annotations

import os
import json
import re
import yaml
from router.fallback_chain import with_fallback
from memory.context_builder import save_context
from tools.error_handler import (
    repair_json,
    extract_code_from_markdown,
    clean_llm_output,
    escape_unescaped_newlines,
)
from tools.checkpoint import save_checkpoint
from tools.token_counter import count_tokens, fits_in_context, truncate_to_fit
from tools.logger import log, print_stage_banner

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
with open(os.path.join(_CONFIG_DIR, "models.yaml")) as f:
    _CFG = yaml.safe_load(f)

# Primary model for token-limit check
PRIMARY_MODEL = _CFG["models"]["coding"]["chain"][0]["model"]

PROMPT = """
You are a senior software engineer.

Architecture:
{architecture}

Test files that already exist (your code must make these tests pass):
{test_spec}

Review feedback from previous iteration (fix ALL of these):
{feedback}

CRITICAL RULES FOR HIGH QUALITY:
- Format each file using a filename annotation followed by a code block:
**path/file.py**
```python
...full complete file content...
```
- ONLY generate the core implementation files listed in the File Manifest.
- DO NOT generate boilerplate files: NO Dockerfile, NO docker-compose, NO mkdocs, NO CI/CD, NO CODEOWNERS, NO .flake8.
- COMPLETE CODE ONLY: Zero placeholders. Strictly NO "pass", NO "...", NO "# TODO", and NO dummy/stub functions. Every function and class must be fully and realistically implemented.
- Robust implementation: Include defensive error handling, input validation, proper typing, and docstrings.
- Ensure all imports between files are consistent and actually exist.
- Do NOT output any tool calls, function calls, XML tags, or conversational banter. Output ONLY the files in the specified format.
"""


def _extract_manifest_files(architecture: str) -> list[str]:
    """Extract files strictly from the ## File Manifest section of the architecture."""
    manifest_match = re.search(
        r"##\s*File Manifest(.*?)(?=##|\Z)", architecture, re.DOTALL | re.IGNORECASE
    )
    search_text = manifest_match.group(1) if manifest_match else architecture
    raw_files = re.findall(r"`([a-zA-Z0-9_/.-]+\.\w+)`", search_text)

    ignored_patterns = {
        "dockerfile", "docker-compose", "mkdocs", "license",
        "codeowners", ".gitignore", ".flake8", "pull_request_template",
        ".github", ".vscode", "readme.md", "contributing.md"
    }

    files = []
    for f in dict.fromkeys(raw_files):
        base = os.path.basename(f).lower()
        if "test_" in base or "_test" in base:
            continue
        if any(ign in base for ign in ignored_patterns):
            continue
        files.append(f)
    return files


def _clean_code_content(content: str) -> str:
    """Strip stray LLM artifacts like XML tool-call tags and duplicate outer code fences."""
    if not isinstance(content, str):
        return ""
    # Strip hallucinated tool-call tags
    for tag in ("</parameter>", "</function>", "</tool_call>", "<tool_call>", "<parameter>", "<function>"):
        content = content.replace(tag, "")
    content = content.strip()
    # Strip accidental outer code fences
    if content.startswith("```"):
        first_nl = content.find("\n")
        if first_nl != -1:
            content = content[first_nl + 1:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def _filter_unwanted_files(code_dict: dict) -> dict:
    """Filter out unwanted boilerplate/junk files and sanitize file content."""
    ignored_patterns = {
        "dockerfile", "docker-compose", "mkdocs", "license",
        "codeowners", ".flake8", "pull_request_template",
        ".github", ".vscode"
    }
    filtered = {}
    for fname, content in code_dict.items():
        base = os.path.basename(fname).lower()
        if any(ign in base for ign in ignored_patterns):
            log("coder", f"Skipping boilerplate file: {fname}", "warning")
            continue
        cleaned = _clean_code_content(content)
        if len(cleaned) < 10:
            log("coder", f"Skipping empty or malformed file: {fname}", "warning")
            continue
        filtered[fname] = cleaned
    return filtered



def _split_and_generate(state: dict) -> dict | None:
    """If the full prompt is too large, generate files one at a time."""
    log("coder", "Prompt too large — switching to per-file generation", "warning")
    architecture = state.get("architecture", "")
    impl_files = _extract_manifest_files(architecture)

    if not impl_files:
        return None

    code = {}
    for fname in impl_files:
        single_prompt = f"""
Write ONLY the file `{fname}` for this system.

Architecture context:
{truncate_to_fit(architecture, 3000)}

Format the file using a filename annotation followed by a code block:
**{fname}**
```python
...complete file content with full implementation, no placeholders...
```
Do NOT output any tool calls, function calls, XML tags, or conversational banter. Output ONLY the file content.
"""
        try:
            raw = with_fallback("coding", single_prompt)
            raw = clean_llm_output(raw)
            chunk = extract_code_from_markdown(raw)
            if not chunk:
                raw_esc = escape_unescaped_newlines(raw)
                try:
                    chunk = json.loads(raw_esc)
                except json.JSONDecodeError:
                    chunk = repair_json(raw_esc)

            if isinstance(chunk, dict) and chunk:
                code.update(chunk)
                log("coder", f"Generated {fname} ✓")
            else:
                log("coder", f"Failed to generate {fname}: Output was not a valid dict", "warning")
        except Exception as e:
            log("coder", f"Failed to generate {fname}: {e}", "warning")

    return _filter_unwanted_files(code) if code else None



def run_coder(state: dict) -> dict:
    """Execute the coding phase."""
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 4)
    print_stage_banner("Coder", iteration + 1, max_iter)
    log("coder", f"Coding — iteration {iteration + 1}/{max_iter}")
    state["last_stage"] = "coder"

    if not state.get("architecture"):
        err = "[coder] Architecture missing — cannot code"
        state["error_log"] = (state.get("error_log") or []) + [err]
        state["code"] = None
        return state

    feedback = "\n".join(state.get("review_feedback") or ["No previous feedback."])
    test_spec = json.dumps(state.get("test_spec") or {}, indent=2)
    prompt = PROMPT.format(
        architecture=truncate_to_fit(state["architecture"], 1500),
        test_spec=truncate_to_fit(test_spec, 600),
        feedback=feedback,
    )
    prompt = truncate_to_fit(prompt, 2200)

    code = None

    try:
        if not fits_in_context(prompt, PRIMARY_MODEL, reserve_for_output=8192):
            code = _split_and_generate(state)

        if code is None:
            raw = with_fallback("coding", prompt)
            cleaned = clean_llm_output(raw)
            log(
                "coder",
                f"LLM output ({len(raw)} chars), first 200: {raw[:200]!r}",
            )
            if cleaned.startswith("{"):
                try:
                    code = json.loads(cleaned)
                except Exception:
                    try:
                        code = json.loads(escape_unescaped_newlines(cleaned))
                    except Exception:
                        code = repair_json(cleaned) or repair_json(raw)

            if not code:
                code = extract_code_from_markdown(raw)

            if not code:
                code = repair_json(cleaned) or repair_json(raw) or extract_code_from_markdown(cleaned)

        if not isinstance(code, dict) or not code:
            raise ValueError(f"Code output is not a valid file dict: {type(code)}")

        code = _filter_unwanted_files(code)

        # Merge test_spec into code so the tester can find them
        if state.get("test_spec"):
            code = {**state["test_spec"], **code}


        state["code"] = code
        state["iteration"] = iteration + 1
        save_context(
            "coding", str(list(code.keys())), {"goal": state.get("sanitised_goal", "")}
        )
        save_checkpoint(state, "post_coder")
        log("coder", f"Generated {len(code)} files: {list(code.keys())} ✓", "success")

    except Exception as e:
        err = f"[coder] iteration {iteration + 1} failed: {e}"
        log("coder", err, "error")
        state["error_log"] = ((state.get("error_log") or []) + [err])[-20:]
        if "exhausted" in str(e):
            state["fatal_error"] = True
        state["iteration"] = iteration + 1  # prevent infinite stall

    return state
