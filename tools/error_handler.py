"""Error Handler — Multi-tier JSON repair and sanitisation.

Provides robust parsing for LLM outputs that may contain malformed JSON,
markdown fences, <think> reasoning blocks, or other formatting issues.

Tier chain:
  1. Strip known wrappers (<think>, markdown fences, preamble)
  2. jsonrepair library
  3. Regex JSON extraction
  4. Markdown code block extraction
"""

from __future__ import annotations

import re
import json
from tools.logger import log

try:
    from jsonrepair import repair_json as _jsonrepair

    HAS_JSONREPAIR = True
except ImportError:
    HAS_JSONREPAIR = False


def clean_llm_output(raw: str) -> str:
    """Strip common LLM wrapper noise from a raw response.

    Handles:
      - <think>...</think> reasoning blocks (Qwen, DeepSeek-R1)
      - Markdown fences (```json, ```python, ```JSON, etc.)
      - Leading preamble text before the first {
      - Trailing text after the last }

    Args:
        raw: Raw LLM response string

    Returns:
        Cleaned string with wrapper noise removed
    """
    if not raw:
        return ""

    text = raw.strip()

    # 1. Strip <think>...</think> blocks (greedy — remove ALL think blocks)
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()

    # 2. Strip markdown fences — handle ```json, ```JSON, ```python, ``` etc.
    text = re.sub(r"```\w*\s*\n?", "", text).strip()

    # 3. Remove trailing backticks left over from fence stripping
    text = text.rstrip("`").strip()

    return text


def escape_unescaped_newlines(s: str) -> str:
    """Escape actual newlines inside JSON string values.

    Traverses the string, tracking if we are inside quotes (single, double, or triple).
    When inside quotes, any raw control character is replaced with its escape sequence.
    """
    parts = []
    in_string = False
    escaped = False
    quote_char = None  # Track which quote started the string
    quote_count = 0  # Track consecutive quotes for triple-quote detection
    i = 0
    while i < len(s):
        char = s[i]
        # Check for triple quotes
        if i + 2 < len(s) and s[i : i + 3] in ('"""', "'''") and not escaped:
            triple_quote = s[i : i + 3]
            if not in_string:
                in_string = True
                quote_char = triple_quote
                quote_count = 3
                parts.append(triple_quote)
                i += 3
                continue
            elif in_string and quote_char == triple_quote:
                in_string = False
                quote_char = None
                quote_count = 0
                parts.append(triple_quote)
                i += 3
                continue

        if char in ('"', "'") and not escaped:
            if not in_string:
                in_string = True
                quote_char = char
                quote_count = 1
            elif char == quote_char and quote_count == 1:
                in_string = False
                quote_char = None
                quote_count = 0
            elif char == quote_char and quote_count >= 2:
                # Multiple consecutive quotes - just append
                quote_count += 1
            parts.append(char)
        elif char == "\\" and in_string and not escaped:
            escaped = True
            parts.append(char)
        elif in_string and char in "\n\r\t\b\f":
            # Escape all control characters inside strings
            escape_map = {
                "\n": "\\n",
                "\r": "\\r",
                "\t": "\\t",
                "\b": "\\b",
                "\f": "\\f",
            }
            parts.append(escape_map[char])
            escaped = False
            i += 1
            continue
        else:
            escaped = False
            parts.append(char)
        i += 1
    return "".join(parts)


def _convert_triple_quotes_to_json(s: str) -> str:
    """Convert Python triple-quoted strings in JSON-like content to valid JSON strings."""
    import re

    # Pattern to find triple-quoted strings in what looks like JSON values
    # Matches: "key": """content""" or 'key': '''content'''
    def replace_triple_quotes(match):
        prefix = match.group(1)
        quote_type = match.group(2)
        content = match.group(3)
        escaped = (
            content.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'{prefix} "{escaped}"'

    pattern = r'(\s*"[^"]+"\s*:\s*)("""|\'\'\')([\s\S]*?)\2'
    return re.sub(pattern, replace_triple_quotes, s)


def _fix_triple_quotes_in_json_strings(s: str) -> str:
    """Fix triple quotes that appear inside JSON string values.

    When LLMs output JSON with Python-style docstrings (triple quotes inside strings),
    this converts them to valid JSON by replacing them with escaped double quotes.
    Only processes triple quotes that are inside JSON string values.
    """
    # Use a state machine to track when we're inside a JSON string value
    result = []
    i = 0
    in_string = False
    string_delimiter = None  # The quote character that started the string ('"' or "'")
    escaped = False

    while i < len(s):
        char = s[i]

        # Check for triple quotes
        if i + 2 < len(s) and s[i : i + 3] in ('"""', "'''"):
            triple_quote = s[i : i + 3]

            if in_string and triple_quote[0] == string_delimiter:
                # We're inside a string and found matching triple quotes
                # Replace with escaped double quotes (valid JSON escape)
                result.append('\\"\\"\\"')
                i += 3
                continue
            elif not in_string:
                # This might be the start of a triple-quoted string value
                # But in JSON, strings are delimited by single/double quotes, not triple quotes
                # So this is likely a malformed JSON - treat as regular quote
                result.append(triple_quote[0])  # Just use single quote
                i += 3
                continue

        # Track string state
        if char in ('"', "'") and not escaped:
            if not in_string:
                in_string = True
                string_delimiter = char
            elif char == string_delimiter:
                in_string = False
                string_delimiter = None

        # Handle escaped characters
        if char == "\\" and in_string and not escaped:
            escaped = True
        else:
            escaped = False

        result.append(char)
        i += 1

    return "".join(result)


def _escape_unescaped_double_quotes(s: str) -> str:
    """Escape unescaped double quotes inside JSON string values.

    When LLMs output JSON with double quotes inside string values (e.g.,
    Python code with double-quoted strings), those inner quotes need to be escaped.

    This function parses the JSON object structure and only escapes double quotes
    that appear inside string VALUES (not keys, not structural quotes).
    """
    # First, extract the outermost JSON object
    obj_match = re.search(r"\{[\s\S]*\}", s)
    if not obj_match:
        return s

    obj_str = obj_match.group(0)

    # Parse the object key-value pairs
    result = "{"
    i = 1  # Skip opening {
    first = True

    while i < len(obj_str) - 1:  # Stop before closing }
        # Skip whitespace
        while i < len(obj_str) and obj_str[i] in " \t\n\r":
            result += obj_str[i]
            i += 1

        if i >= len(obj_str) - 1:
            break

        if not first:
            result += ","
        first = False

        # Parse key
        if obj_str[i] == '"':
            # Quoted key
            result += '"'
            i += 1
            key_start = i
            while i < len(obj_str) and obj_str[i] != '"':
                if obj_str[i] == "\\":
                    result += "\\\\"
                    i += 1
                    if i < len(obj_str):
                        result += obj_str[i]
                        i += 1
                else:
                    result += obj_str[i]
                    i += 1
            result += '"'
            i += 1  # Skip closing "
        else:
            # Unquoted key (shouldn't happen in valid JSON but handle anyway)
            key_start = i
            while i < len(obj_str) and obj_str[i] not in " \t\n\r:":
                result += obj_str[i]
                i += 1

        # Skip whitespace
        while i < len(obj_str) and obj_str[i] in " \t\n\r":
            result += obj_str[i]
            i += 1

        # Skip colon
        if i < len(obj_str) and obj_str[i] == ":":
            result += ":"
            i += 1

        # Skip whitespace
        while i < len(obj_str) and obj_str[i] in " \t\n\r":
            result += obj_str[i]
            i += 1

        if i >= len(obj_str):
            break

        # Parse value
        if obj_str[i] == '"':
            # String value - fix unescaped quotes inside
            result += '"'
            i += 1
            val_start = i
            val_content = []
            while i < len(obj_str):
                if obj_str[i] == "\\":
                    val_content.append(obj_str[i])
                    i += 1
                    if i < len(obj_str):
                        val_content.append(obj_str[i])
                        i += 1
                elif obj_str[i] == '"':
                    # Check if this is the end of the string value
                    # Look ahead for structural chars
                    next_i = i + 1
                    while next_i < len(obj_str) and obj_str[next_i] in " \t\n\r":
                        next_i += 1
                    if next_i < len(obj_str) and obj_str[next_i] in ",}]":
                        # This is the end of the value
                        break
                    else:
                        # Unescaped quote inside content - escape it
                        val_content.append('\\"')
                        i += 1
                        continue
                else:
                    val_content.append(obj_str[i])
                    i += 1

            result += "".join(val_content)
            result += '"'
            if i < len(obj_str) and obj_str[i] == '"':
                i += 1
        elif obj_str[i] in "{[":
            # Nested object/array - copy as-is (simplified)
            bracket_stack = [obj_str[i]]
            result += obj_str[i]
            i += 1
            while i < len(obj_str) and bracket_stack:
                if obj_str[i] in "{[":
                    bracket_stack.append(obj_str[i])
                elif obj_str[i] in "}]":
                    bracket_stack.pop()
                result += obj_str[i]
                i += 1
        else:
            # Number, boolean, null - copy as-is
            val_start = i
            while i < len(obj_str) and obj_str[i] not in " \t\n\r,}]":
                result += obj_str[i]
                i += 1

    result += "}"
    return s[: obj_match.start()] + result + s[obj_match.end() :]


def repair_json(raw: str) -> dict | None:
    """Attempt to repair malformed JSON using multiple strategies.

    Args:
        raw: Raw string that should contain JSON

    Returns:
        Parsed dict if successful, None if all strategies fail
    """
    if not raw or not raw.strip():
        log("error_handler", "Empty input to repair_json", "warning")
        return None

    # Pre-clean: strip LLM wrapper noise and escape unescaped newlines in strings
    cleaned = clean_llm_output(raw)
    # Convert triple-quoted strings to valid JSON
    cleaned = _convert_triple_quotes_to_json(cleaned)
    # Fix triple quotes inside JSON string values (Python docstrings)
    cleaned = _fix_triple_quotes_in_json_strings(cleaned)
    # Escape unescaped double quotes inside JSON string values
    cleaned = _escape_unescaped_double_quotes(cleaned)
    cleaned = escape_unescaped_newlines(cleaned)

    # Strategy 0: Direct parse of cleaned output
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            log("error_handler", "JSON parsed after cleaning", "success")
            return result
    except (json.JSONDecodeError, Exception):
        pass

    # Strategy 1: jsonrepair library
    if HAS_JSONREPAIR:
        try:
            repaired = _jsonrepair(cleaned)
            result = json.loads(repaired)
            if isinstance(result, dict):
                log("error_handler", "JSON repaired via jsonrepair library", "success")
                return result
        except Exception:
            pass

    # Strategy 2: Regex — find the outermost { ... }
    try:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            result = json.loads(match.group())
            if isinstance(result, dict):
                log("error_handler", "JSON extracted via regex", "success")
                return result
    except (json.JSONDecodeError, Exception):
        pass

    # Strategy 3: Fix common issues then regex extract
    try:
        fixed = cleaned
        # Remove trailing commas before } or ]
        fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
        # Fix double commas
        fixed = re.sub(r",\s*,+", ",", fixed)
        # Fix unquoted string values (e.g. "quality": thirty,)
        fixed = re.sub(r':\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*([,}])', r': "\1"\2', fixed)
        # Remove single-line comments
        fixed = re.sub(r"//.*$", "", fixed, flags=re.MULTILINE)
        # Remove Python-style comments that aren't inside strings
        fixed = re.sub(r"#.*$", "", fixed, flags=re.MULTILINE)
        match = re.search(r"\{[\s\S]*\}", fixed)
        if match:
            result = json.loads(match.group())
            if isinstance(result, dict):
                log("error_handler", "JSON extracted after cleanup", "success")
                return result
    except Exception:
        pass

    # Strategy 4: Try jsonrepair on the raw outermost { ... } match
    if HAS_JSONREPAIR:
        try:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                repaired = _jsonrepair(match.group())
                result = json.loads(repaired)
                if isinstance(result, dict):
                    log(
                        "error_handler",
                        "JSON repaired via regex + jsonrepair",
                        "success",
                    )
                    return result
        except Exception:
            pass

    # Strategy 5: Extract review scores from plain-text / markdown responses.
    # LLM reviewers often ignore the JSON-only instruction and return prose like:
    #   "**Quality:** 80\n**Security:** 90\n**Performance:** 75"
    # or "Quality (80/100)" etc.
    try:
        score_patterns = [
            # "quality": 80  or  "quality" : 80  (unquoted JSON-like)
            r'"?(quality|security|performance)"?\s*[:=]\s*(\d+)',
            # **Quality:** 80  or  **Quality**: 80  (colon inside or outside **)
            r'\*{0,2}(quality|security|performance)\*{0,2}\s*:?\s*\*{0,2}\s*(\d+)',
            # Quality (80/100)
            r'(quality|security|performance)\s*\((\d+)/\d+\)',
            # General fallback: "Quality" ... number (within 20 chars)
            r'(quality|security|performance)\D{0,20}?(\d{1,3})(?!\d)',
        ]
        scores = {}
        for pattern in score_patterns:
            for match in re.finditer(pattern, cleaned, re.IGNORECASE):
                key = match.group(1).lower()
                val = int(match.group(2))
                if 0 <= val <= 100 and key not in scores:
                    scores[key] = val

        if len(scores) >= 2:  # At least 2 of 3 score fields found
            # Fill missing fields with 50
            for k in ("quality", "security", "performance"):
                scores.setdefault(k, 50)

            # Try to extract issues list from bullet points
            issues = []
            for m in re.finditer(r'[•\-\*]\s*(.+?)(?:\n|$)', cleaned):
                issue = m.group(1).strip()
                # Skip short items, score lines, and asterisk-only fragments
                if (len(issue) > 15
                    and not re.match(r'^[\*\s]*(quality|security|performance)', issue, re.I)
                    and not re.search(r'(quality|security|performance)\D{0,10}\d', issue, re.I)):
                    issues.append(issue)
            scores["issues"] = issues[:10]

            log("error_handler", f"Extracted review scores from prose: {scores}", "success")
            return scores
    except Exception:
        pass

    # Log a snippet of what we couldn't parse for debugging
    snippet = cleaned[:300] if cleaned else raw[:300]
    log(
        "error_handler",
        f"All JSON repair strategies failed. First 300 chars: {snippet!r}",
        "error",
    )
    return None


def extract_code_from_markdown(raw: str) -> dict | None:
    """Extract code blocks from markdown and return as a file dict.

    Looks for patterns like:
    ```python
    # filename.py
    content...
    ```

    Also handles filename annotations like:
    **filename.py**
    ```python
    content...
    ```

    Also handles descriptive text followed by annotated blocks.

    Args:
        raw: Raw markdown string with code blocks

    Returns:
        Dict mapping filenames to content, or None if extraction fails
    """
    if not raw:
        return None

    # First, try to find annotated blocks: filename before a fence
    annotated_pattern = re.compile(
        r"(?:\*\*|`)?([a-zA-Z0-9_/.-]+\.\w+)(?:\*\*|`)?\s*\n"
        r"```\w*\n(.*?)```",
        re.DOTALL,
    )
    annotated_matches = annotated_pattern.findall(raw)
    if annotated_matches:
        files = {fname.strip(): content.strip() for fname, content in annotated_matches}
        if files:
            return files

    # Second, try more flexible pattern: filename annotation followed by content then code fence
    # Handles: **filename.py**\n\ncontent...\n```python\ncode\n```
    flex_pattern = re.compile(
        r"(?:\*\*|`)?([a-zA-Z0-9_/.-]+\.\w+)(?:\*\*|`)?\s*\n"
        r"(.*?)\n```\w*\n(.*?)```",
        re.DOTALL,
    )
    flex_matches = flex_pattern.findall(raw)
    if flex_matches:
        files = {}
        for fname, _, content in flex_matches:
            files[fname.strip()] = content.strip()
        if files:
            log(
                "error_handler",
                f"Extracted {len(files)} files from flexible annotated markdown blocks",
                "success",
            )
            return files

    # Third: filename annotation followed directly by JSON object (no code fence)
    # Pattern: **filename.py**\n{...}
    json_annotated_pattern = re.compile(
        r"(?:\*\*|`)?([a-zA-Z0-9_/.-]+\.\w+)(?:\*\*|`)?\s*\n"
        r"(\{[\s\S]*?\})(?=\n\s*(?:\*\*|`)[a-zA-Z0-9_/.-]+\.\w+|\Z)",
        re.DOTALL,
    )
    json_matches = json_annotated_pattern.findall(raw)
    if json_matches:
        files = {}
        for fname, json_str in json_matches:
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, dict):
                    # This is a file dict, merge it
                    files.update(parsed)
                else:
                    files[fname.strip()] = json_str.strip()
            except json.JSONDecodeError:
                files[fname.strip()] = json_str.strip()
        if files:
            log(
                "error_handler",
                f"Extracted {len(files)} files from JSON-annotated markdown blocks",
                "success",
            )
            return files

    # Fourth: JSON object with backtick-wrapped string values
    # Pattern: {"key": `value`, "key2": `value2`}
    backtick_json_pattern = re.compile(
        r'\{\s*(?:"[^"]+"\s*:\s*`[^`]*`\s*(?:,\s*)?)+\s*\}',
        re.DOTALL,
    )
    backtick_matches = backtick_json_pattern.findall(raw)
    if backtick_matches:
        for match in backtick_matches:
            # Replace backticks with quotes to make valid JSON
            fixed = match.replace("`", '"')
            try:
                parsed = json.loads(fixed)
                if isinstance(parsed, dict):
                    log(
                        "error_handler",
                        f"Extracted {len(parsed)} files from backtick-wrapped JSON",
                        "success",
                    )
                    return parsed
            except json.JSONDecodeError:
                pass

    # Fifth: filename annotation followed by raw code (no code fence)
    # Pattern: **filename.py**\ncode...\n**filename2.py**
    # We look for a filename line, and grab everything until the next filename line or EOF.
    # A filename line is something like `#### **file.py**` or `**file.py**` or just `file.py`.
    raw_code_pattern = re.compile(
        r"(?:^|\n)(?:\s*#+\s*)?(?:\*\*|`)?([a-zA-Z0-9_/.-]+\.\w+)(?:\*\*|`)?\s*\n"
        r"(.*?)(?=\n(?:\s*#+\s*)?(?:\*\*|`)?[a-zA-Z0-9_/.-]+\.\w+(?:\*\*|`)?\s*\n|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    raw_matches = raw_code_pattern.findall(raw)
    if raw_matches:
        files = {}
        for fname, content in raw_matches:
            # Avoid matching random prose that happens to look like a filename at the end of a sentence
            if "." in fname and len(fname) > 3 and not " " in fname:
                # Strip leading/trailing whitespace and ignore empty files
                c = content.strip()
                if c:
                    files[fname.strip()] = c
        if files:
            log(
                "error_handler",
                f"Extracted {len(files)} files from raw un-fenced markdown",
                "success",
            )
            return files

    # Fallback: unnamed code blocks
    blocks = re.findall(
        r"```(?:python|javascript|js|typescript|ts|py)?\n(.*?)```", raw, re.DOTALL
    )
    if not blocks:
        return None

    files = {}
    for i, block in enumerate(blocks):
        # Try to extract filename from first comment line
        first_line = block.strip().split("\n")[0]
        fname_match = re.match(r"^#\s*(.+\.[a-z]+)", first_line)
        if fname_match:
            fname = fname_match.group(1).strip()
            content = "\n".join(block.strip().split("\n")[1:])
        else:
            fname = f"file_{i}.py"
            content = block.strip()
        files[fname] = content

    if files:
        log(
            "error_handler",
            f"Extracted {len(files)} files from markdown blocks",
            "success",
        )
    return files if files else None


def safe_dict_merge(base: dict, updates: dict) -> dict:
    """Safely merge updates into a base dict without losing keys.

    Args:
        base: Original dictionary
        updates: New key-value pairs to merge in

    Returns:
        Merged dictionary with updates applied
    """
    result = dict(base)
    for key, value in updates.items():
        if isinstance(value, str) and len(value.strip()) > 10:
            result[key] = value
        elif key not in result:
            result[key] = value
        # Skip suspiciously short replacements for existing files
        elif isinstance(value, str) and len(value.strip()) < 10:
            log(
                "error_handler",
                f"Skipping suspiciously short replacement for '{key}' "
                f"({len(value)} chars)",
                "warning",
            )
        else:
            result[key] = value
    return result
