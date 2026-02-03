#!/usr/bin/env python3
"""Validate MCP tool modules are registered in server.py.

Checks:
1. Every .py file in tools/ (except __init__.py) is imported in server.py
2. Reports any tool modules that exist but aren't registered
"""

import re
import sys
from pathlib import Path

TOOLS_DIR = Path("databricks-mcp-server/databricks_mcp_server/tools")
SERVER_PY = Path("databricks-mcp-server/databricks_mcp_server/server.py")
SKIP_FILES = {"__init__.py"}


def main() -> int:
    errors = []

    # Get all tool module files
    tool_modules = {
        f.stem for f in TOOLS_DIR.glob("*.py") if f.name not in SKIP_FILES
    }

    if not tool_modules:
        print(f"::error::No tool modules found in {TOOLS_DIR}")
        return 1

    # Parse server.py for tool imports
    server_content = SERVER_PY.read_text()

    # Find all 'from .tools import X' statements (handles both single and multiple lines)
    import_pattern = r"from \.tools import\s+([a-zA-Z_][a-zA-Z0-9_]*)"
    import_matches = re.findall(import_pattern, server_content)

    if not import_matches:
        errors.append("No 'from .tools import ...' statement found in server.py")
    else:
        # Collect all imported modules
        imported = set(import_matches)

        # Check for unregistered tools
        unregistered = tool_modules - imported
        if unregistered:
            errors.append(
                f"Tool modules not imported in server.py: {sorted(unregistered)}\n"
                f"    Add them to the 'from .tools import ...' statement"
            )

        # Check for imports that don't exist (optional warning)
        nonexistent = imported - tool_modules
        if nonexistent:
            errors.append(
                f"Imports in server.py but no module file: {sorted(nonexistent)}"
            )

    # Report results
    if errors:
        print("MCP tool validation failed:\n")
        for error in errors:
            # GitHub Actions annotation format - shows as error in UI
            print(f"::error::{error}")
        print()
        print(f"Found {len(errors)} error(s)")
        return 1

    print(f"All {len(tool_modules)} MCP tool modules are registered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
