#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "httpx",
# ]
# ///
"""
AI Dev Kit Installer - Cross-platform bootstrap script

Usage:
    curl -LsSf https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.py | uv run -

Or download and run directly:
    uv run install.py
    uv run install.py install --help
    uv run install.py install --skills-only
"""

import httpx
import os
import platform
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


# GitHub raw URL for cli/releases binaries
GITHUB_REPO = "databricks-solutions/ai-dev-kit"
RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/cli/releases"


def get_platform_info() -> tuple[str, str]:
    """Detect current OS and architecture."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize OS
    if system == "darwin":
        os_name = "macos"
    elif system == "linux":
        os_name = "linux"
    elif system == "windows":
        os_name = "windows"
    else:
        raise RuntimeError(f"Unsupported operating system: {system}")

    # Normalize architecture
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        raise RuntimeError(f"Unsupported architecture: {machine}")

    return os_name, arch


def get_binary_path(os_name: str, arch: str) -> str:
    """Get the binary path for the platform."""
    if os_name == "macos":
        # Universal binary - no arch needed
        return "macos/aidevkit"
    elif os_name == "windows":
        return f"windows/{arch}/aidevkit.exe"
    else:
        return f"linux/{arch}/aidevkit"


def download_binary(url: str, dest: Path) -> None:
    """Download a file from URL to destination."""
    print(f"  Downloading from GitHub releases...")

    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
        if response.status_code == 404:
            raise RuntimeError(
                f"Binary not found. Make sure a release exists at:\n  {url}"
            )
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))

        with open(dest, "wb") as f:
            downloaded = 0
            for chunk in response.iter_bytes(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = (downloaded / total) * 100
                    bar_len = 30
                    filled = int(bar_len * downloaded / total)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    print(f"\r  [{bar}] {pct:.0f}%", end="", flush=True)
        print()  # newline after progress


def main():
    print()
    print("  ┌─────────────────────────────────────────────┐")
    print("  │       Databricks AI Dev Kit Installer       │")
    print("  └─────────────────────────────────────────────┘")
    print()

    # Detect platform
    try:
        os_name, arch = get_platform_info()
        print(f"  Platform: {os_name}/{arch}")
    except RuntimeError as e:
        print(f"  Error: {e}")
        sys.exit(1)

    # Build download URL
    binary_path = get_binary_path(os_name, arch)
    download_url = f"{RAW_URL}/{binary_path}"

    # Create temp directory for binary
    with tempfile.TemporaryDirectory() as tmpdir:
        binary_name = "aidevkit.exe" if os_name == "windows" else "aidevkit"
        local_path = Path(tmpdir) / binary_name

        # Download binary
        print()
        try:
            download_binary(download_url, local_path)
        except httpx.HTTPStatusError as e:
            print(f"  Error downloading: HTTP {e.response.status_code}")
            sys.exit(1)
        except RuntimeError as e:
            print(f"  Error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"  Error downloading: {e}")
            sys.exit(1)

        # Make executable (Unix)
        if os_name != "windows":
            local_path.chmod(local_path.stat().st_mode | stat.S_IEXEC)

        # Run the installer with any passed arguments
        print()
        print("  Running aidevkit installer...")
        print("  " + "─" * 43)
        print()

        # Pass through any command line arguments, default to "install"
        args = sys.argv[1:] if len(sys.argv) > 1 else ["install"]
        result = subprocess.run([str(local_path)] + args)
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()

