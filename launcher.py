#!/usr/bin/env python3
"""
AgentOS Launcher - Simple entry point that starts the server and opens the browser.
Works in both development and frozen (PyInstaller) modes.
"""

import os
import sys
import time
import webbrowser
import threading
import subprocess
import socket
import atexit
import signal


def get_base_path():
    """Get the base path for the application."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_free_port(start_port=8000, max_port=8100):
    """Find a free port to run the server on."""
    for port in range(start_port, max_port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start_port  # fallback


def wait_for_server(port, timeout=30):
    """Wait for the server to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(("127.0.0.1", port))
                return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            time.sleep(0.5)
    return False


def open_browser(port):
    """Open the browser to the AgentOS UI."""
    url = f"http://127.0.0.1:{port}"
    print(f"Opening {url} in your default browser...")
    webbrowser.open(url)


def run_server(port):
    """Run the uvicorn server."""
    base_path = get_base_path()
    os.chdir(base_path)

    import subprocess
    cmd = [
        sys.executable, "-m", "uvicorn", 
        "api:app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--log-level", "warning"
    ]
    subprocess.run(cmd)


def main():
    print("=" * 50)
    print("  AgentOS - Multi-Agent AI Software Company")
    print("=" * 50)
    print()

    # Find a free port
    port = find_free_port()
    print(f"Starting server on port {port}...")

    # Start server in a separate thread
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    # Wait for server to be ready
    print("Waiting for server to start...")
    if not wait_for_server(port):
        print("ERROR: Server failed to start within timeout")
        return 1

    print("Server is ready!")

    # Open browser
    open_browser(port)

    print()
    print("AgentOS is running!")
    print(f"  Local URL: http://127.0.0.1:{port}")
    print()
    print("Press Ctrl+C to stop the server")
    print()

    try:
        # Keep the main thread alive
        while server_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
