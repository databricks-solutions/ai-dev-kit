#!/usr/bin/env python3
"""
Fetch a Databricks Genie Space's serialized configuration.

Usage: python fetch_space.py <space_id>
Output: JSON to stdout
Exit codes: 0 success, 1 error (message to stderr)

Requires:
  - databricks-sdk >= 0.85 (pip install "databricks-sdk>=0.85")
  - Databricks CLI profile configured (databricks configure)
  - CAN EDIT permission on the target Genie Space
"""

import json
import sys


def fetch_space(space_id: str) -> dict:
    """Fetch a Genie Space with its serialized configuration."""
    try:
        from databricks.sdk import WorkspaceClient
    except ImportError:
        print(
            'Error: databricks-sdk is not installed. Run: pip install "databricks-sdk>=0.85"',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        client = WorkspaceClient()
    except Exception as e:
        print(
            f"Error: Failed to initialize Databricks client. "
            f"Ensure your CLI profile is configured (databricks configure).\n{e}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        space = client.genie.get_space(
            space_id=space_id,
            include_serialized_space=True,
        )
    except Exception as e:
        error_msg = str(e)
        if "PERMISSION_DENIED" in error_msg or "403" in error_msg:
            print(
                f"Error: Permission denied. You need CAN EDIT permission on space '{space_id}'.",
                file=sys.stderr,
            )
        elif "NOT_FOUND" in error_msg or "404" in error_msg:
            print(
                f"Error: Genie Space '{space_id}' not found. Check the space ID.",
                file=sys.stderr,
            )
        else:
            print(f"Error: Failed to fetch space '{space_id}': {e}", file=sys.stderr)
        sys.exit(1)

    if not space.serialized_space:
        print(
            "Error: Could not retrieve serialized_space. "
            "Ensure you have CAN EDIT permission on the Genie Space.",
            file=sys.stderr,
        )
        sys.exit(1)

    return {
        "title": space.title,
        "description": space.description,
        "space_id": space_id,
        "warehouse_id": space.warehouse_id,
        "serialized_space": json.loads(space.serialized_space),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fetch_space.py <space_id>", file=sys.stderr)
        sys.exit(1)

    result = fetch_space(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
