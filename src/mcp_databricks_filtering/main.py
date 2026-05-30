"""CLI entry point — prints the current allowlist."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from mcp_databricks_filtering.config import FilterConfig
from mcp_databricks_filtering.table_filter import TableTagFilter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MCP Databricks table filter utility")
    parser.add_argument(
        "--tag-name",
        default=None,
        help="UC tag key to filter on (overrides MCP_TABLE_FILTER_TAG_NAME)",
    )
    parser.add_argument(
        "--tag-value",
        default=None,
        help="Required tag value (overrides MCP_TABLE_FILTER_TAG_VALUE)",
    )
    args = parser.parse_args(argv)

    config = FilterConfig.from_env()
    if args.tag_name is not None or args.tag_value is not None:
        config = replace(
            config,
            tag_name=args.tag_name if args.tag_name is not None else config.tag_name,
            tag_value=args.tag_value if args.tag_value is not None else config.tag_value,
        )

    if not config.is_enabled:
        print(
            "Table filter is DISABLED (set MCP_TABLE_FILTER_TAG_NAME or use --tag-name)",
            file=sys.stderr,
        )
        return 1

    f = TableTagFilter(config=config)
    print(f"Filter:    {config.tag_name}={config.tag_value or '<any>'}")
    print(f"Cache TTL: {config.cache_ttl_seconds}s")
    print()

    try:
        allowed = f.get_allowed_tables()
    except Exception as exc:
        print(f"ERROR querying allowed tables: {exc}", file=sys.stderr)
        return 2

    print(f"Found {len(allowed)} allowed table(s):")
    for cat, sch, tbl in sorted(allowed):
        print(f"  {cat}.{sch}.{tbl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
