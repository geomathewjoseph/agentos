"""Docker Sandbox — Isolated test execution environment.

Runs generated code in Docker containers with no network access,
memory limits, and execution timeouts for safe test execution.
"""

from __future__ import annotations

import os
import tempfile
import shutil
from tools.logger import log

_CLIENT = None


def _get_client():
    """Get or create a Docker client."""
    global _CLIENT
    if _CLIENT is None:
        try:
            import docker

            _CLIENT = docker.from_env()
        except Exception as e:
            raise RuntimeError(
                f"Docker not available: {e}\n"
                "Install Docker and ensure the daemon is running."
            )
    return _CLIENT


def run_tests_in_sandbox(code: dict, timeout: int = 120) -> tuple[bool, list[str]]:
    """Run tests in a Docker sandbox.

    Write all code files to a temp directory, mount it into a Docker
    container, run the appropriate test suite, return (passed, errors).
    Network is disabled inside the container.

    Args:
        code: Dict mapping filenames to file contents
        timeout: Maximum execution time in seconds

    Returns:
        Tuple of (all_passed: bool, errors: list[str])
    """
    tmpdir = tempfile.mkdtemp()
    errors = []
    passed = True

    try:
        # Write files
        for filename, content in code.items():
            try:
                path = os.path.join(tmpdir, filename)
                # Guard against empty dirname (file in root)
                dirname = os.path.dirname(path)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)
                # Normalize path for Windows
                path = os.path.normpath(path)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                log(
                    "docker_sandbox", f"Failed to write file {filename}: {e}", "warning"
                )
                errors.append(f"Write error for {filename}: {e}")
                passed = False

        # Detect stack
        keys = set(code.keys())
        py_files = [k for k in keys if k.endswith(".py")]
        has_tests = any("test_" in k or "_test.py" in k for k in py_files)
        has_npm = "package.json" in keys

        import docker

        client = _get_client()

        def _docker_run(image: str, command: str) -> tuple[bool, str]:
            container_obj = None
            try:
                container_obj = client.containers.run(
                    image,
                    command=command,
                    volumes={tmpdir: {"bind": "/app", "mode": "rw"}},
                    working_dir="/app",
                    network_mode="none",
                    mem_limit="512m",
                    detach=True,
                    stdout=True,
                    stderr=True,
                )
                # Wait with a timeout, then kill if needed
                try:
                    exit_code = container_obj.wait(timeout=timeout)["StatusCode"]
                except Exception:
                    # Timeout or other error — kill the container
                    try:
                        container_obj.kill()
                    except Exception:
                        pass
                    return False, f"Docker container timed out after {timeout}s"

                output = container_obj.logs(stdout=True, stderr=True).decode(
                    "utf-8", errors="replace"
                )
                container_obj.remove(force=True)

                if exit_code != 0:
                    return False, output[-4000:]
                return True, output[-4000:]

            except docker.errors.ContainerError as e:
                return False, (e.stderr.decode("utf-8") if e.stderr else str(e))[-4000:]
            except Exception as e:
                if container_obj:
                    try:
                        container_obj.remove(force=True)
                    except Exception:
                        pass
                return False, f"Docker error: {e}"

        # Python: syntax check first, then pytest
        if py_files:
            for pyf in py_files:
                ok, out = _docker_run("python:3.11-slim", f"python -m py_compile {pyf}")
                if not ok:
                    passed = False
                    errors.append(f"Syntax error in {pyf}:\n{out}")

            if has_tests and passed:
                install_cmd = (
                    "pip install -q -r requirements.txt 2>/dev/null; "
                    if "requirements.txt" in keys
                    else ""
                )
                ok, out = _docker_run(
                    "python:3.11-slim",
                    f"sh -c '{install_cmd}python -m pytest . -v --tb=short --no-header'",
                )
                if not ok:
                    passed = False
                    errors.append(f"pytest failures:\n{out}")
                else:
                    log("tester", "pytest passed ✓", "success")

        # Node
        if has_npm:
            ok, out = _docker_run(
                "node:20-slim",
                "sh -c 'npm install --prefer-offline --silent && npm test -- --watchAll=false'",
            )
            if not ok:
                passed = False
                errors.append(f"npm test failures:\n{out}")
            else:
                log("tester", "npm test passed ✓", "success")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return passed, errors
