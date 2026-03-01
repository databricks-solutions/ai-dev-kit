#!/usr/bin/env python3
"""
Compare Power BI model JSON against Databricks schema JSON.
Classifies the migration scenario (A, B, C, or D) and generates a comparison report.

Usage:
    python compare_schemas.py <pbi_model.json> <dbx_schema.json> [-o report.md] [--json]
        [--mapping intermediate_mapping.json]
        [--gap-analysis reference/column_gap_analysis.md]

Inputs are the JSON outputs of parse_pbi_model.py and extract_dbx_schema.py.
No external dependencies required (stdlib only).
"""

import argparse
import json
import os
import re
import sys
from difflib import SequenceMatcher


_DISCRIMINATOR_PATTERNS = [
    r"status", r"type", r"category", r"code", r"flag", r"class",
    r"kind", r"tier", r"level", r"group",
]
_DISCRIMINATOR_PREFIXES = ("is_", "has_", "can_")
_DISCRIMINATOR_SUFFIXES = ("_type", "_status", "_code", "_flag", "_category", "_class")


def _is_discriminator(col_name: str) -> bool:
    """Heuristic check: does the column name suggest a low-cardinality discriminator?"""
    lower = col_name.lower()
    if lower.startswith(_DISCRIMINATOR_PREFIXES):
        return True
    if lower.endswith(_DISCRIMINATOR_SUFFIXES):
        return True
    for pat in _DISCRIMINATOR_PATTERNS:
        if re.search(rf"\b{pat}\b", lower):
            return True
    return False


def _load_mapping(mapping_path: str) -> dict[str, dict[str, str]]:
    """Load an intermediate mapping file and return a lookup: (pbi_table_lower, pbi_col_lower) -> dbx_col."""
    with open(mapping_path) as f:
        data = json.load(f)
    lookup: dict[str, dict[str, str]] = {}
    for m in data.get("mappings", []):
        pbi_table = m.get("pbi_table", "").lower()
        col_map: dict[str, str] = {}
        for c in m.get("columns", []):
            pbi_col = c.get("pbi_column", "").lower()
            dbx_col = c.get("dbx_column", "")
            if pbi_col and dbx_col:
                col_map[pbi_col] = dbx_col
        if pbi_table and col_map:
            lookup[pbi_table] = col_map
    return lookup


def compare(pbi: dict, dbx: dict, mapping: dict[str, dict[str, str]] | None = None) -> dict:
    pbi_tables = {t["name"].lower(): t for t in pbi["tables"]}
    dbx_tables = {t["name"].lower(): t for t in dbx["tables"]}

    report = {
        "scenario": None,
        "table_matches": [],
        "table_pbi_only": [],
        "table_dbx_only": [],
        "suggested_mappings": [],
        "summary": {},
    }

    matched = 0
    name_differs = 0
    mapping_used = 0
    matched_dbx_keys = set()

    for pbi_name, pbi_table in pbi_tables.items():
        table_mapping = mapping.get(pbi_name) if mapping else None

        if pbi_name in dbx_tables:
            col_report = _compare_columns(pbi_table, dbx_tables[pbi_name], table_mapping)
            report["table_matches"].append({
                "pbi_table": pbi_table["name"],
                "dbx_table": dbx_tables[pbi_name]["name"],
                "dbx_fqn": dbx_tables[pbi_name].get("fqn", ""),
                "match_type": "mapped" if table_mapping else "exact",
                "column_comparison": col_report,
            })
            matched_dbx_keys.add(pbi_name)
            if table_mapping:
                mapping_used += 1
            elif col_report["exact_matches"] == col_report["total_pbi_columns"]:
                matched += 1
            else:
                name_differs += 1
        else:
            best_match, score = _fuzzy_match(pbi_name, list(dbx_tables.keys()))
            if score >= 0.6:
                col_report = _compare_columns(pbi_table, dbx_tables[best_match], table_mapping)
                report["table_matches"].append({
                    "pbi_table": pbi_table["name"],
                    "dbx_table": dbx_tables[best_match]["name"],
                    "dbx_fqn": dbx_tables[best_match].get("fqn", ""),
                    "match_type": "fuzzy",
                    "similarity": round(score, 2),
                    "column_comparison": col_report,
                })
                matched_dbx_keys.add(best_match)
                name_differs += 1
            else:
                report["table_pbi_only"].append(pbi_table["name"])

    for dbx_name, dbx_table in dbx_tables.items():
        if dbx_name not in matched_dbx_keys:
            report["table_dbx_only"].append(dbx_table.get("fqn", dbx_table["name"]))

    total_pbi = len(pbi_tables)
    if total_pbi == 0:
        report["scenario"] = "EMPTY"
    elif mapping_used > 0:
        report["scenario"] = "D"
    elif matched == total_pbi:
        report["scenario"] = "A"
    elif (matched + name_differs) >= total_pbi * 0.8 and not report["table_pbi_only"]:
        report["scenario"] = "B"
    else:
        report["scenario"] = "C"

    if report["scenario"] in ("B", "C", "D"):
        report["suggested_mappings"] = _generate_mapping(report["table_matches"])

    all_measures = []
    for t in pbi["tables"]:
        for m in t.get("measures", []):
            all_measures.append({
                "table": t["name"],
                "name": m["name"],
                "expression": m.get("expression", ""),
                "displayFolder": m.get("displayFolder", ""),
            })

    report["summary"] = {
        "total_pbi_tables": total_pbi,
        "total_dbx_tables": len(dbx_tables),
        "exact_table_matches": matched,
        "fuzzy_table_matches": name_differs,
        "mapped_table_matches": mapping_used,
        "pbi_only_tables": len(report["table_pbi_only"]),
        "dbx_only_tables": len(report["table_dbx_only"]),
        "total_pbi_measures": len(all_measures),
        "scenario": report["scenario"],
    }
    report["measures"] = all_measures

    return report


def _compare_columns(
    pbi_table: dict,
    dbx_table: dict,
    col_mapping: dict[str, str] | None = None,
) -> dict:
    pbi_cols = {}
    for c in pbi_table.get("columns", []):
        pbi_cols[c["name"].lower()] = c["name"]

    dbx_cols = {}
    for c in dbx_table.get("columns", []):
        dbx_cols[c["name"].lower()] = c

    exact = []
    mapped = []
    fuzzy = []
    pbi_only = []

    for pbi_lower, pbi_name in pbi_cols.items():
        if col_mapping and pbi_lower in col_mapping:
            dbx_target = col_mapping[pbi_lower].lower()
            if dbx_target in dbx_cols:
                mapped.append({
                    "pbi": pbi_name,
                    "dbx": dbx_cols[dbx_target]["name"],
                    "via": "mapping",
                })
                continue

        if pbi_lower in dbx_cols:
            exact.append({"pbi": pbi_name, "dbx": dbx_cols[pbi_lower]["name"]})
        else:
            best, score = _fuzzy_match(pbi_lower, list(dbx_cols.keys()))
            if score >= 0.6:
                fuzzy.append({
                    "pbi": pbi_name,
                    "dbx": dbx_cols[best]["name"],
                    "similarity": round(score, 2),
                })
            else:
                pbi_only.append(pbi_name)

    dbx_matched = {m["dbx"].lower() for m in exact + fuzzy + mapped}
    dbx_only_cols = []
    for c in dbx_table.get("columns", []):
        if c["name"].lower() not in dbx_matched:
            entry = {"name": c["name"], "data_type": c.get("data_type", c.get("dataType", ""))}
            entry["is_discriminator"] = _is_discriminator(c["name"])
            dbx_only_cols.append(entry)

    return {
        "total_pbi_columns": len(pbi_cols),
        "total_dbx_columns": len(dbx_cols),
        "exact_matches": len(exact),
        "mapped_matches": len(mapped),
        "fuzzy_matches": len(fuzzy),
        "pbi_only": pbi_only,
        "dbx_only": [c["name"] for c in dbx_only_cols],
        "dbx_only_details": dbx_only_cols,
        "fuzzy_details": fuzzy,
        "mapped_details": mapped,
    }


def _fuzzy_match(name: str, candidates: list[str]) -> tuple[str, float]:
    best = ""
    best_score = 0.0
    for c in candidates:
        score = SequenceMatcher(None, name, c).ratio()
        if score > best_score:
            best = c
            best_score = score
    return best, best_score


def _generate_mapping(matches: list) -> list:
    mappings = []
    for m in matches:
        cc = m["column_comparison"]
        columns = []
        for fm in cc.get("fuzzy_details", []):
            columns.append({
                "powerbi_column": fm["pbi"],
                "databricks_column": fm["dbx"],
                "transform": None,
            })
        for po in cc.get("pbi_only", []):
            columns.append({
                "powerbi_column": po,
                "databricks_column": "???",
                "transform": "NEEDS_MAPPING",
            })
        if columns:
            mappings.append({
                "powerbi_table": m["pbi_table"],
                "databricks_table": m.get("dbx_fqn", m["dbx_table"]),
                "columns": columns,
            })
    return mappings


def render_markdown(report: dict) -> str:
    lines = ["# Schema Comparison Report\n"]

    s = report["summary"]
    lines.append(f"**Scenario: {s['scenario']}**\n")
    scenario_desc = {
        "A": "Direct repoint -- table and column names match.",
        "B": "View layer needed -- names differ but model structure is the same.",
        "C": "Mapping document needed -- names and/or model structure differ significantly.",
        "D": "Intermediate mapping layer -- Power Query M renames resolved via mapping file.",
    }
    lines.append(f"> {scenario_desc.get(s['scenario'], 'Unknown')}\n")

    lines.append("## Summary\n")
    lines.append("| Metric | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| Power BI tables | {s['total_pbi_tables']} |")
    lines.append(f"| Databricks tables | {s['total_dbx_tables']} |")
    lines.append(f"| Exact table matches | {s['exact_table_matches']} |")
    lines.append(f"| Fuzzy table matches | {s['fuzzy_table_matches']} |")
    if s.get('mapped_table_matches', 0) > 0:
        lines.append(f"| Mapped table matches | {s['mapped_table_matches']} |")
    lines.append(f"| Power BI only | {s['pbi_only_tables']} |")
    lines.append(f"| Databricks only | {s['dbx_only_tables']} |")
    lines.append(f"| Power BI measures | {s['total_pbi_measures']} |")
    lines.append("")

    if report["table_matches"]:
        lines.append("## Table Matches\n")
        for m in report["table_matches"]:
            match_type = m["match_type"]
            if match_type == "exact":
                label = "(exact)"
            elif match_type == "mapped":
                label = "(mapped via intermediate layer)"
            else:
                label = f"(fuzzy, {m.get('similarity', '')})"
            lines.append(f"### {m['pbi_table']} -> {m['dbx_table']} {label}\n")
            cc = m["column_comparison"]
            parts = [f"{cc['exact_matches']} exact"]
            if cc.get('mapped_matches', 0) > 0:
                parts.append(f"{cc['mapped_matches']} mapped")
            parts.append(f"{cc['fuzzy_matches']} fuzzy")
            parts.append(f"{len(cc['pbi_only'])} PBI-only")
            parts.append(f"{len(cc['dbx_only'])} DBX-only")
            lines.append(f"- Columns: {', '.join(parts)}")
            if cc.get("mapped_details"):
                lines.append("- Mapped column matches (via intermediate mapping):")
                for mm in cc["mapped_details"]:
                    lines.append(f"  - `{mm['pbi']}` -> `{mm['dbx']}`")
            if cc["fuzzy_details"]:
                lines.append("- Fuzzy column matches:")
                for fm in cc["fuzzy_details"]:
                    lines.append(f"  - `{fm['pbi']}` ~ `{fm['dbx']}` ({fm['similarity']})")
            if cc["pbi_only"]:
                lines.append(f"- PBI-only columns: {', '.join(f'`{c}`' for c in cc['pbi_only'])}")
            if cc["dbx_only"]:
                lines.append(f"- DBX-only columns: {', '.join(f'`{c}`' for c in cc['dbx_only'])}")
            lines.append("")

    if report["table_pbi_only"]:
        lines.append("## Power BI Only Tables (no Databricks match)\n")
        for t in report["table_pbi_only"]:
            lines.append(f"- `{t}`")
        lines.append("")

    if report["table_dbx_only"]:
        lines.append("## Databricks Only Tables (not referenced in Power BI)\n")
        for t in report["table_dbx_only"]:
            lines.append(f"- `{t}`")
        lines.append("")

    if report.get("measures"):
        lines.append("## Power BI Measures Inventory\n")
        lines.append("| Table | Measure | Display Folder |")
        lines.append("|-------|---------|----------------|")
        for m in report["measures"]:
            folder = m["displayFolder"] or "-"
            lines.append(f"| {m['table']} | {m['name']} | {folder} |")
        lines.append("")

    if report["suggested_mappings"]:
        lines.append("## Suggested Mapping Document\n")
        lines.append("Save this to `models/mapping_documents/mapping.json` and edit as needed:\n")
        lines.append("```json")
        lines.append(json.dumps({"mappings": report["suggested_mappings"]}, indent=2))
        lines.append("```\n")

    return "\n".join(lines)


def render_column_gap_analysis(report: dict) -> str:
    """Produce a dedicated Column Gap Analysis markdown from the comparison report."""
    lines = ["# Column Gap Analysis\n"]
    lines.append("Columns present in Databricks but not referenced in the Power BI model.\n")
    lines.append("Columns flagged as **discriminators** may be essential for filters, partitions, or report subsets.\n")

    has_gaps = False
    for m in report.get("table_matches", []):
        cc = m["column_comparison"]
        dbx_details = cc.get("dbx_only_details", [])
        if not dbx_details:
            continue
        has_gaps = True
        table_label = m.get("dbx_fqn") or m["dbx_table"]
        lines.append(f"## Table: {table_label}\n")
        lines.append("| Column | Data Type | Discriminator? | Suggested Action |")
        lines.append("|--------|-----------|----------------|------------------|")
        for col in dbx_details:
            disc = "Yes" if col.get("is_discriminator") else "No"
            action = "May filter report subsets -- run data discovery" if col.get("is_discriminator") else "Review if needed in reports"
            lines.append(f"| {col['name']} | {col.get('data_type', '')} | {disc} | {action} |")
        lines.append("")

    if not has_gaps:
        lines.append("No DBX-only columns detected. All Databricks columns are referenced in the Power BI model.\n")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Compare Power BI model vs Databricks schema"
    )
    parser.add_argument("pbi_json", help="Power BI model JSON (from parse_pbi_model.py)")
    parser.add_argument("dbx_json", help="Databricks schema JSON (from extract_dbx_schema.py)")
    parser.add_argument("-o", "--output", default=None, help="Output report path (.md)")
    parser.add_argument("--json", action="store_true", help="Also output raw JSON report")
    parser.add_argument(
        "--mapping", default=None,
        help="Intermediate mapping JSON (Scenario D). Maps pbi_column -> dbx_column via M renames.",
    )
    parser.add_argument(
        "--gap-analysis", default=None,
        help="Output path for column gap analysis (.md). Defaults to reference/column_gap_analysis.md.",
    )
    args = parser.parse_args()

    with open(args.pbi_json) as f:
        pbi = json.load(f)
    with open(args.dbx_json) as f:
        dbx = json.load(f)

    mapping = _load_mapping(args.mapping) if args.mapping else None
    report = compare(pbi, dbx, mapping)
    md = render_markdown(report)

    output_path = args.output or "schema_comparison.md"
    with open(output_path, "w") as f:
        f.write(md)

    print(f"Scenario: {report['summary']['scenario']}")
    print(f"Report: {output_path}")

    if args.json:
        json_path = output_path.replace(".md", ".json")
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"JSON: {json_path}")

    gap_path = args.gap_analysis or "reference/column_gap_analysis.md"
    gap_md = render_column_gap_analysis(report)
    os.makedirs(os.path.dirname(gap_path) or ".", exist_ok=True)
    with open(gap_path, "w") as f:
        f.write(gap_md)
    print(f"Column gap analysis: {gap_path}")


if __name__ == "__main__":
    main()
