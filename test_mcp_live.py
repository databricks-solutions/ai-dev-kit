"""
Live test of the MCP table filter against real Databricks.

Calls the actual MCP tool functions (same code path as the MCP server)
with tag filtering enabled to verify behavior end-to-end.

Usage:
    databricks auth login --profile stg-bi   # if token expired
    python test_mcp_live.py
"""

import os
import sys
import json

# Add MCP server + core to path
sys.path.insert(0, os.path.expanduser("~/.ai-dev-kit/repo/databricks-mcp-server"))
sys.path.insert(0, os.path.expanduser("~/.ai-dev-kit/repo/databricks-tools-core"))

# Configure filter
os.environ["DATABRICKS_CONFIG_PROFILE"] = "stg-bi"
os.environ["MCP_TABLE_FILTER_TAG_NAME"] = "mcp-ready"
os.environ["MCP_TABLE_FILTER_TAG_VALUE"] = "yes"
os.environ["MCP_TABLE_FILTER_CACHE_TTL"] = "60"

from databricks_mcp_server.table_filter import TableTagFilter


def pp(label, obj):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if isinstance(obj, (dict, list, set)):
        print(json.dumps(obj if not isinstance(obj, set) else sorted(str(x) for x in obj), indent=2, default=str))
    else:
        print(obj)


def main():
    f = TableTagFilter()
    print(f"Filter enabled: {f.is_enabled}")
    print(f"Tag filter:     {f.tag_name} = {f.tag_value}")
    print(f"Cache TTL:      {f.cache_ttl}s")

    # ── 1. Query allowed tables from Databricks ──────────────────────
    pp("1. ALLOWED TABLES (from system.information_schema.table_tags)", None)
    try:
        allowed = f.get_allowed_tables()
        print(f"\nFound {len(allowed)} table(s) tagged with {f.tag_name}={f.tag_value}:\n")
        for cat, sch, tbl in sorted(allowed):
            print(f"  - {cat}.{sch}.{tbl}")
    except Exception as e:
        print(f"ERROR: {e}")
        print("\nDid you run:  databricks auth login --profile stg-bi  ?")
        return

    # ── 2. Filter a table list ───────────────────────────────────────
    pp("2. FILTER TABLE LIST (main.eod)", None)
    fake_tables = [
        {"name": "delta_bronze_analystratings"},
        {"name": "delta_bronze_price"},
        {"name": "delta_bronze_dividends"},
        {"name": "some_secret_table"},
    ]
    filtered = f.filter_table_list(fake_tables, "main", "eod")
    print(f"\nInput tables:    {[t['name'] for t in fake_tables]}")
    print(f"Filtered result: {[t['name'] for t in filtered]}")

    # ── 3. SQL validation tests ──────────────────────────────────────
    pp("3. SQL VALIDATION TESTS", None)

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

    # ── 4. Call actual get_table_stats_and_schema ─────────────────────
    pp("4. ACTUAL get_table_stats_and_schema CALL (main.eod)", None)
    try:
        from databricks_tools_core.sql import (
            get_table_stats_and_schema as _core_get_stats,
            TableStatLevel,
        )
        print("\nCalling core get_table_stats_and_schema (NONE level, fast)...")
        result = _core_get_stats(
            catalog="main",
            schema="eod",
            table_stat_level=TableStatLevel.NONE,
        )
        result_dict = result.model_dump(exclude_none=True) if hasattr(result, "model_dump") else result

        all_tables = [t.get("name", "?") for t in result_dict.get("tables", [])]
        print(f"\nAll tables in main.eod (unfiltered): {len(all_tables)} tables")
        for t in sorted(all_tables):
            print(f"  - {t}")

        # Now apply filter
        if "tables" in result_dict:
            result_dict["tables"] = [
                t for t in result_dict["tables"]
                if ("main", "eod", t.get("name", "").split(".")[-1].lower()) in allowed
            ]
        filtered_tables = [t.get("name", "?") for t in result_dict.get("tables", [])]
        print(f"\nAfter tag filter ({f.tag_name}={f.tag_value}): {len(filtered_tables)} tables")
        for t in sorted(filtered_tables):
            print(f"  - {t}")

    except Exception as e:
        print(f"ERROR: {e}")

    # ── 5. Test execute_sql with blocked table ────────────────────────
    pp("5. EXECUTE_SQL VALIDATION TEST", None)
    print("\nTrying to run SQL against a non-tagged table...")
    try:
        f.validate_sql("SELECT * FROM main.eod.delta_bronze_dividends")
        print("  Result: ALLOWED (table is tagged)")
    except PermissionError as e:
        print(f"  Result: BLOCKED")
        print(f"  Reason: {e}")

    print("\nTrying to run SQL against the tagged table...")
    try:
        f.validate_sql("SELECT * FROM main.eod.delta_bronze_analystratings")
        print("  Result: ALLOWED (table is tagged)")
    except PermissionError as e:
        print(f"  Result: BLOCKED")
        print(f"  Reason: {e}")

    print(f"\n{'='*60}")
    print("  DONE - All tests completed")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
