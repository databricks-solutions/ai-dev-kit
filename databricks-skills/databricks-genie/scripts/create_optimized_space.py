#!/usr/bin/env python3
"""
Create a new optimized Databricks Genie Space from an updated configuration.

Usage: python create_optimized_space.py <original_space_id> <updated_config_path>
Output: JSON to stdout with new_space_id, new_space_title, original_space_id
Exit codes: 0 success, 1 error (message to stderr)

Requires:
  - databricks-sdk >= 0.85 (pip install "databricks-sdk>=0.85")
  - Databricks CLI profile configured (databricks configure)
  - CAN EDIT permission on the original Genie Space
"""

import json
import sys


def create_optimized_space(original_space_id: str, updated_config: dict) -> dict:
    """Create a new Genie Space from an updated serialized config."""
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

    # Fetch original space to get warehouse_id and title
    try:
        original_space = client.genie.get_space(space_id=original_space_id)
    except Exception as e:
        error_msg = str(e)
        if "PERMISSION_DENIED" in error_msg or "403" in error_msg:
            print(
                f"Error: Permission denied. You need CAN EDIT permission on space '{original_space_id}'.",
                file=sys.stderr,
            )
        elif "NOT_FOUND" in error_msg or "404" in error_msg:
            print(
                f"Error: Genie Space '{original_space_id}' not found. Check the space ID.",
                file=sys.stderr,
            )
        else:
            print(f"Error: Failed to fetch space '{original_space_id}': {e}", file=sys.stderr)
        sys.exit(1)

    if not original_space.warehouse_id:
        print(
            f"Error: Original space '{original_space_id}' has no warehouse_id. "
            f"Cannot create a new space without a warehouse.",
            file=sys.stderr,
        )
        sys.exit(1)

    new_title = f"[Optimized] {original_space.title}"

    # Create the new space
    try:
        new_space = client.genie.create_space(
            warehouse_id=original_space.warehouse_id,
            serialized_space=json.dumps(updated_config, ensure_ascii=False),
            title=new_title,
            description=original_space.description,
        )
    except Exception as e:
        error_msg = str(e)
        if "PERMISSION_DENIED" in error_msg or "403" in error_msg:
            print(
                "Error: Permission denied. You may not have permission to create Genie Spaces.",
                file=sys.stderr,
            )
        else:
            print(f"Error: Failed to create new space: {e}", file=sys.stderr)
        sys.exit(1)

    return {
        "new_space_id": new_space.space_id,
        "new_space_title": new_title,
        "original_space_id": original_space_id,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python create_optimized_space.py <original_space_id> <updated_config_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    original_space_id = sys.argv[1]
    config_path = sys.argv[2]

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            updated_config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}", file=sys.stderr)
        sys.exit(1)

    result = create_optimized_space(original_space_id, updated_config)
    print(json.dumps(result, indent=2, ensure_ascii=False))
