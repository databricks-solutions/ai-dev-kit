"""
Manual smoke-check of the MCP table filter against a live Databricks workspace.

This is NOT a pytest test — run it directly:

    databricks auth login --profile <profile>

    MCP_TABLE_FILTER_TAG_NAME=mcp-ready MCP_TABLE_FILTER_TAG_VALUE=yes \\
        uv run python scripts/smoke_check.py
"""

from __future__ import annotations

import json
import sys

from mcp_databricks_filtering.config import FilterConfig
from mcp_databricks_filtering.table_filter import TableTagFilter


def banner(label: str) -> None:
    bar = "=" * 60
    print(f"\n{bar}\n  {label}\n{bar}")


def main() -> int:
    config = FilterConfig.from_env()
    if not config.is_enabled:
        print("Set MCP_TABLE_FILTER_TAG_NAME first (or use --tag-name).", file=sys.stderr)
        return 1

    f = TableTagFilter(config=config)
    print(f"Filter:    {config.tag_name}={config.tag_value or '<any>'}")
    print(f"Cache TTL: {config.cache_ttl_seconds}s")

    banner("1. Allowed tables")
    try:
        allowed = f.get_allowed_tables()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"\nFound {len(allowed)} allowed table(s):\n")
    for cat, sch, tbl in sorted(allowed):
        print(f"  - {cat}.{sch}.{tbl}")

    banner("2. Filter a fake table list")
    fake = [
        {"name": "delta_bronze_analystratings"},
        {"name": "delta_bronze_price"},
        {"name": "delta_bronze_dividends"},
        {"name": "some_secret_table"},
    ]
    filtered = f.filter_table_list(fake, "main", "eod")
    print(json.dumps({
        "input": [t["name"] for t in fake],
        "filtered": [t["name"] for t in filtered],
    }, indent=2))

    banner("3. SQL validation cases")
    cases = [
        ("Allowed table", "SELECT * FROM main.eod.delta_bronze_analystratings"),
        ("Blocked table", "SELECT * FROM main.eod.some_secret_table"),
        ("System table",  "SELECT * FROM system.information_schema.table_tags"),
        ("USE CATALOG",   "USE CATALOG main"),
        ("SHOW TABLES",   "SHOW TABLES IN main.eod"),
        ("Join blocked",  "SELECT a.* FROM main.eod.delta_bronze_analystratings a "
                          "JOIN main.eod.secret b ON a.id = b.id"),
        ("CTE allowed",   "WITH t AS (SELECT * FROM main.eod.delta_bronze_analystratings) "
                          "SELECT * FROM t"),
        ("Garbage SQL",   "THIS IS NOT VALID @@@@"),
    ]
    for label, sql in cases:
        try:
            f.validate_sql(sql)
            print(f"  [ALLOWED] {label}")
        except PermissionError as exc:
            print(f"  [BLOCKED] {label}: {exc}")

    print("\nSmoke check complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
