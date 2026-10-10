"""Host Runner — Fallback test execution when Docker is unavailable.

Runs generated code directly on the host using subprocess with timeouts.
This is a last resort — Docker sandbox is strongly preferred.

WARNING: Running untrusted generated code on the host is dangerous.
         Use a VM or container environment when possible.
"""

from __future__ import annotations

import os
import sys
import subprocess
import tempfile
import shutil
from tools.logger import log


def run_tests_on_host(code: dict, timeout: int = 120) -> tuple[bool, list[str]]:
    """Run tests directly on the host (fallback when Docker unavailable).

    Args:
        code: Dict mapping filenames to file contents
        timeout: Maximum execution time in seconds

    Returns:
        Tuple of (all_passed: bool, errors: list[str])
    """
    log(
        "host_runner",
        "⚠️  WARNING: Running generated code directly on host! "
        "Docker is strongly recommended for sandboxed execution.",
        "warning",
    )

    tmpdir = tempfile.mkdtemp(prefix="agentos_test_")
    errors = []
    passed = True

    try:
        # Write files
        for filename, content in code.items():
            try:
                path = os.path.join(tmpdir, filename)
                dirname = os.path.dirname(path)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)
                # Normalize path for Windows
                path = os.path.normpath(path)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                log("host_runner", f"Failed to write file {filename}: {e}", "warning")
                errors.append(f"Write error for {filename}: {e}")
                passed = False

        keys = set(code.keys())
        py_files = [k for k in keys if k.endswith(".py")]
        has_tests = any("test_" in k or "_test.py" in k for k in py_files)

        # Fast in-memory Python syntax check (<1ms)
        if py_files:
            import ast
            for pyf in py_files:
                content = code.get(pyf, "")
                try:
                    ast.parse(content, filename=pyf)
                except SyntaxError as e:
                    passed = False
                    errors.append(
                        f"Syntax error in {pyf} (line {e.lineno}, col {e.offset}):\n{e.text or ''}\n{e.msg}"
                    )
                except Exception as e:
                    passed = False
                    errors.append(f"Parse error in {pyf}: {e}")

        # Run pytest if tests exist and syntax is OK
        if has_tests and passed:
            try:
                # Install deps if requirements.txt exists
                if "requirements.txt" in keys:
                    subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pip",
                            "install",
                            "-q",
                            "-r",
                            "requirements.txt",
                        ],
                        cwd=tmpdir,
                        capture_output=True,
                        timeout=60,
                    )

                # Configure pytest with automatic module resolution
                ini_path = os.path.join(tmpdir, "agentos_pytest.ini")
                with open(ini_path, "w", encoding="utf-8") as f:
                    f.write("[pytest]\npythonpath = . src\ntestpaths = . tests\n")

                # Ensure PYTHONPATH contains tmpdir and tmpdir/src
                test_env = os.environ.copy()
                src_path = os.path.join(tmpdir, "src")
                existing_pp = test_env.get("PYTHONPATH", "")
                test_env["PYTHONPATH"] = f"{tmpdir}{os.pathsep}{src_path}{os.pathsep}{existing_pp}"

                result = subprocess.run(
                    [sys.executable, "-m", "pytest", ".", "-v", "--tb=short", "--no-header", "-c", "agentos_pytest.ini"],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=test_env,
                )
                if result.returncode != 0:
                    passed = False
                    output = (result.stdout + "\n" + result.stderr)[-4000:]
                    errors.append(f"pytest failures:\n{output}")
                else:
                    log("host_runner", "pytest passed ✓", "success")


            except subprocess.TimeoutExpired:
                passed = False
                errors.append(f"pytest timed out after {timeout}s")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return passed, errors
