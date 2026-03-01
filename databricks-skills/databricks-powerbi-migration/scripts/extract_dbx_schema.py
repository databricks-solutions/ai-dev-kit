#!/usr/bin/env python3
"""
Extract Databricks schema metadata for all tables in a catalog.schema.
Outputs a JSON file with columns, types, constraints, and table size estimates.

Usage:
    python extract_dbx_schema.py <catalog> <schema> [-o output.json] [--profile PROFILE]

Requires:
    pip install databricks-sdk

Authentication:
    Uses Databricks SDK default auth chain. Preferred: PAT via ~/.databrickscfg
    or DATABRICKS_HOST + DATABRICKS_TOKEN environment variables.
    Use --profile to select a specific CLI profile.
"""

import argparse
import json
import sys
from databricks.sdk import WorkspaceClient


def extract_schema(catalog: str, schema: str, profile: str | None = None) -> dict:
    kwargs = {"profile": profile} if profile else {}
    w = WorkspaceClient(**kwargs)
    warehouse_id = _get_warehouse_id(w)

    result = {"catalog": catalog, "schema": schema, "tables": []}

    tables_result = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=f"SHOW TABLES IN `{catalog}`.`{schema}`",
        wait_timeout="30s",
    )

    if not tables_result.result or not tables_result.result.data_array:
        print(f"No tables found in {catalog}.{schema}", file=sys.stderr)
        return result

    for row in tables_result.result.data_array:
        table_name = row[1]
        fqn = f"`{catalog}`.`{schema}`.`{table_name}`"

        desc = w.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=f"DESCRIBE EXTENDED {fqn}",
            wait_timeout="30s",
        )
        columns, properties = _parse_describe(desc.result.data_array)

        detail = w.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=f"DESCRIBE DETAIL {fqn}",
            wait_timeout="30s",
        )
        size_info = _parse_detail(detail.result)

        constraints = _get_constraints(w, warehouse_id, fqn)

        result["tables"].append({
            "name": table_name,
            "fqn": f"{catalog}.{schema}.{table_name}",
            "columns": columns,
            "properties": properties,
            "size": size_info,
            "constraints": constraints,
        })

    return result


def _get_warehouse_id(w: WorkspaceClient) -> str:
    warehouses = list(w.warehouses.list())
    if not warehouses:
        raise RuntimeError("No SQL warehouses found. Create one or specify warehouse_id.")
    for wh in warehouses:
        if wh.state and wh.state.value == "RUNNING":
            if getattr(wh, "enable_serverless_compute", False):
                return wh.id
    for wh in warehouses:
        if wh.state and wh.state.value == "RUNNING":
            return wh.id
    return warehouses[0].id


def _parse_describe(data_array: list) -> tuple[list, dict]:
    columns = []
    properties = {}
    in_columns = True

    for row in data_array:
        col_name = row[0] if row[0] else ""
        col_type = row[1] if len(row) > 1 and row[1] else ""
        comment = row[2] if len(row) > 2 and row[2] else ""

        if col_name.strip() == "" or col_name.startswith("#"):
            in_columns = False
            continue

        if in_columns and col_type:
            columns.append({
                "name": col_name.strip(),
                "type": col_type.strip(),
                "comment": comment.strip(),
            })
        elif not in_columns and col_name.strip() and col_type:
            properties[col_name.strip()] = col_type.strip()

    return columns, properties


def _parse_detail(result) -> dict:
    if not result or not result.data_array:
        return {}
    headers = [col.name for col in result.manifest.schema.columns]
    row = result.data_array[0]
    detail = dict(zip(headers, row))
    return {
        "num_files": detail.get("numFiles"),
        "size_bytes": detail.get("sizeInBytes"),
        "num_rows": detail.get("numRows"),
        "format": detail.get("format"),
    }


def _get_constraints(w: WorkspaceClient, warehouse_id: str, fqn: str) -> list:
    try:
        result = w.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=f"SHOW CONSTRAINTS ON {fqn}",
            wait_timeout="30s",
        )
        if result.result and result.result.data_array:
            return result.result.data_array
        return []
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Extract Databricks schema metadata to JSON"
    )
    parser.add_argument("catalog", help="Unity Catalog name")
    parser.add_argument("schema", help="Schema name")
    parser.add_argument("-o", "--output", default=None, help="Output JSON file path")
    parser.add_argument("--profile", default=None, help="Databricks CLI profile name")
    args = parser.parse_args()

    schema_data = extract_schema(args.catalog, args.schema, args.profile)

    output_path = args.output or f"{args.catalog}_{args.schema}_schema.json"
    with open(output_path, "w") as f:
        json.dump(schema_data, f, indent=2)

    table_count = len(schema_data["tables"])
    total_cols = sum(len(t["columns"]) for t in schema_data["tables"])
    print(f"Extracted {table_count} tables, {total_cols} columns -> {output_path}")


if __name__ == "__main__":
    main()
