#!/usr/bin/env python3
"""
AgentOS Build Script - Builds the standalone executable using PyInstaller.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def run_cmd(cmd, cwd=None):
    """Run a command and return success status."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    return result.returncode == 0


def main():
    project_dir = Path(__file__).parent.absolute()
    dist_dir = project_dir / "dist"
    build_dir = project_dir / "build"

    print("=" * 60)
    print("  AgentOS Build Script")
    print("=" * 60)
    print()

    # Clean previous builds
    print("Cleaning previous builds...")
    for d in [dist_dir, build_dir]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  Removed {d}")

    # Check PyInstaller
    print("\nChecking PyInstaller...")
    if not run_cmd("pyinstaller --version"):
        print("PyInstaller not found. Installing...")
        if not run_cmd(f"{sys.executable} -m pip install pyinstaller"):
            print("ERROR: Failed to install PyInstaller")
            return 1

    # Check for icon
    icon_path = project_dir / "static" / "icon.ico"
    if not icon_path.exists():
        print("Note: No icon.ico found in static/, using default icon")

    # Build the executable
    print("\nBuilding AgentOS executable...")
    print("This may take a few minutes...")

    spec_file = project_dir / "AgentOS.spec"
    if not spec_file.exists():
        print("ERROR: AgentOS.spec not found!")
        return 1

    cmd = f"pyinstaller --clean --noconfirm {spec_file}"
    if not run_cmd(cmd, cwd=project_dir):
        print("ERROR: Build failed!")
        return 1

    # Check if build succeeded
    exe_path = dist_dir / "AgentOS.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n✓ Build successful!")
        print(f"  Executable: {exe_path}")
        print(f"  Size: {size_mb:.1f} MB")
        print()
        print("To run: ./dist/AgentOS.exe")
        print("Or double-click the .exe in the dist/ folder")
        return 0
    else:
        print("ERROR: Executable not found after build!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
