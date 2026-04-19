"""
Manual smoke-test of the MCP table filter against a live Databricks workspace.

This is NOT a pytest test — run it directly:

    # Ensure auth is valid
    databricks auth login --profile stg-bi

    # Run with env vars
    MCP_TABLE_FILTER_TAG_NAME=mcp-ready MCP_TABLE_FILTER_TAG_VALUE=yes \
        uv run python scripts/test_mcp_live.py
"""

import json
import os
import sys

os.environ.setdefault("MCP_TABLE_FILTER_TAG_NAME", "mcp-ready")
os.environ.setdefault("MCP_TABLE_FILTER_TAG_VALUE", "yes")
os.environ.setdefault("MCP_TABLE_FILTER_CACHE_TTL", "60")

from mcp_databricks_filtering.table_filter import TableTagFilter


def pp(label, obj=None):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if obj is not None:
        if isinstance(obj, (dict, list)):
            print(json.dumps(obj, indent=2, default=str))
        elif isinstance(obj, set):
            print(json.dumps(sorted(str(x) for x in obj), indent=2))
        else:
            print(obj)


def main():
    f = TableTagFilter()
    print(f"Filter enabled: {f.is_enabled}")
    print(f"Tag filter:     {f.tag_name} = {f.tag_value}")
    print(f"Cache TTL:      {f.cache_ttl}s")

    # 1. Query allowed tables
    pp("1. ALLOWED TABLES (from system.information_schema.table_tags)")
    try:
        allowed = f.get_allowed_tables()
        print(f"\nFound {len(allowed)} table(s) tagged with {f.tag_name}={f.tag_value}:\n")
        for cat, sch, tbl in sorted(allowed):
            print(f"  - {cat}.{sch}.{tbl}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("\nCheck your Databricks auth configuration.", file=sys.stderr)
        sys.exit(1)

    # 2. Filter a table list
    pp("2. FILTER TABLE LIST (main.eod)")
    fake_tables = [
        {"name": "delta_bronze_analystratings"},
        {"name": "delta_bronze_price"},
        {"name": "delta_bronze_dividends"},
        {"name": "some_secret_table"},
    ]
    filtered = f.filter_table_list(fake_tables, "main", "eod")
    print(f"\nInput tables:    {[t['name'] for t in fake_tables]}")
    print(f"Filtered result: {[t['name'] for t in filtered]}")

    # 3. SQL validation
    pp("3. SQL VALIDATION TESTS")
    test_queries = [
        ("SELECT from allowed table", "SELECT * FROM main.eod.delta_bronze_analystratings"),
        ("SELECT from blocked table", "SELECT * FROM main.eod.some_secret_table"),
        ("System table (should pass)", "SELECT * FROM system.information_schema.table_tags"),
        ("USE CATALOG (should pass)", "USE CATALOG main"),
        ("SHOW TABLES (should pass)", "SHOW TABLES IN main.eod"),
        ("JOIN: allowed + blocked", "SELECT a.* FROM main.eod.delta_bronze_analystratings a JOIN main.eod.secret b ON a.id = b.id"),
        ("CTE referencing allowed", "WITH t AS (SELECT * FROM main.eod.delta_bronze_analystratings) SELECT * FROM t"),
    ]

    for label, sql in test_queries:
        try:
            f.validate_sql(sql)
            result = "ALLOWED"
        except PermissionError as e:
            result = f"BLOCKED - {e}"
        print(f"\n  [{result.split(' -')[0]:>7}] {label}")
        print(f"           SQL: {sql[:80]}")
        if "BLOCKED" in result:
            print(f"           Reason: {result.split(' - ', 1)[1][:100]}")

    print(f"\n{'='*60}")
    print("  DONE - All tests completed")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
