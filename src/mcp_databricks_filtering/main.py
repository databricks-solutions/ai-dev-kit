"""Entry point for the MCP table filter — prints the current allowlist."""

import argparse
import re
import sys

from mcp_databricks_filtering.table_filter import TableTagFilter


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(value: str) -> str:
    """Reject anything that isn't a simple SQL identifier."""
    if not _IDENTIFIER_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"Invalid identifier: {value!r}. Only alphanumerics and underscores allowed."
        )
    return value


def main():
    parser = argparse.ArgumentParser(description="MCP Databricks table filter utility")
    parser.add_argument(
        "--tag-name",
        default=None,
        help="UC tag key to filter on (overrides MCP_TABLE_FILTER_TAG_NAME env var)",
    )
    parser.add_argument(
        "--tag-value",
        default=None,
        help="Required tag value (overrides MCP_TABLE_FILTER_TAG_VALUE env var)",
    )
    args = parser.parse_args()

    import os
    if args.tag_name:
        os.environ["MCP_TABLE_FILTER_TAG_NAME"] = args.tag_name
    if args.tag_value:
        os.environ["MCP_TABLE_FILTER_TAG_VALUE"] = args.tag_value

    f = TableTagFilter()

    if not f.is_enabled:
        print("Table filter is DISABLED (MCP_TABLE_FILTER_TAG_NAME not set)", file=sys.stderr)
        sys.exit(1)

    print(f"Filter: {f.tag_name}={f.tag_value}")
    print(f"Cache TTL: {f.cache_ttl}s")
    print()

    try:
        allowed = f.get_allowed_tables()
    except Exception as e:
        print(f"ERROR querying allowed tables: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(allowed)} allowed table(s):")
    for cat, sch, tbl in sorted(allowed):
        print(f"  {cat}.{sch}.{tbl}")


if __name__ == "__main__":
    main()
