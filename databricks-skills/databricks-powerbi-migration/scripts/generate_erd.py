#!/usr/bin/env python3
"""
Generate an ERD (Mermaid + text) and domain groupings from a parsed Power BI model.

Reads the JSON output of parse_pbi_model.py and produces:
  - erd.md      -- Mermaid erDiagram + text-based table/relationship summary
  - domains.md  -- Tables and measures grouped by inferred business domain

Domain inference uses (in priority order):
  1. Measure displayFolder values
  2. Table name prefix patterns (e.g., Sales_*, Fin_*)
  3. Relationship connectivity (connected components)

Usage:
    python generate_erd.py <pbi_model.json> [-o OUTPUT_DIR]

No external dependencies required (stdlib only).
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Mermaid ERD generation
# ---------------------------------------------------------------------------

_MERMAID_TYPE_MAP = {
    "int64": "bigint",
    "int32": "int",
    "double": "double",
    "decimal": "decimal",
    "string": "string",
    "boolean": "bool",
    "dateTime": "datetime",
    "date": "date",
    "binary": "binary",
}


def _sanitize_mermaid_name(name: str) -> str:
    """Strip characters that break Mermaid node names."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def _mermaid_type(data_type: str) -> str:
    return _MERMAID_TYPE_MAP.get(data_type.lower(), data_type or "unknown")


def _build_fk_lookup(relationships: list) -> dict[str, set[str]]:
    """Return {table_lower: {col_lower, ...}} for FK columns."""
    fks: dict[str, set[str]] = defaultdict(set)
    for rel in relationships:
        fks[rel["fromTable"].lower()].add(rel["fromColumn"].lower())
    return fks


def _build_pk_lookup(relationships: list) -> dict[str, set[str]]:
    """Return {table_lower: {col_lower, ...}} for PK (to-side) columns."""
    pks: dict[str, set[str]] = defaultdict(set)
    for rel in relationships:
        pks[rel["toTable"].lower()].add(rel["toColumn"].lower())
    return pks


def generate_mermaid(model: dict) -> str:
    """Return a Mermaid erDiagram string."""
    lines = ["erDiagram"]

    relationships = model.get("relationships", [])
    fk_lookup = _build_fk_lookup(relationships)
    pk_lookup = _build_pk_lookup(relationships)

    for rel in relationships:
        from_t = _sanitize_mermaid_name(rel["fromTable"])
        to_t = _sanitize_mermaid_name(rel["toTable"])
        label = rel.get("fromColumn", "")
        active = rel.get("isActive", True)
        if not active:
            label += " (inactive)"
        lines.append(f'    {from_t} }}o--|| {to_t} : "{label}"')

    for table in model.get("tables", []):
        safe_name = _sanitize_mermaid_name(table["name"])
        tbl_lower = table["name"].lower()
        cols = table.get("columns", []) + table.get("calculated_columns", [])
        if not cols:
            continue
        lines.append(f"    {safe_name} {{")
        for col in cols:
            dtype = _mermaid_type(col.get("dataType", ""))
            col_name = re.sub(r"\s+", "_", col["name"])
            marker = ""
            if col["name"].lower() in pk_lookup.get(tbl_lower, set()):
                marker = " PK"
            elif col["name"].lower() in fk_lookup.get(tbl_lower, set()):
                marker = " FK"
            lines.append(f"        {dtype} {col_name}{marker}")
        lines.append("    }")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Text-based ERD
# ---------------------------------------------------------------------------

def generate_text_erd(model: dict) -> str:
    """Return a human-readable text ERD."""
    relationships = model.get("relationships", [])
    fk_lookup = _build_fk_lookup(relationships)
    pk_lookup = _build_pk_lookup(relationships)
    sections = []

    for table in model.get("tables", []):
        tbl_lower = table["name"].lower()
        cols = table.get("columns", []) + table.get("calculated_columns", [])
        header = f"Table: {table['name']}"
        sections.append(header)
        sections.append("=" * len(header))

        if cols:
            name_w = max(len(c["name"]) for c in cols)
            type_w = max(len(c.get("dataType", "")) for c in cols)
            name_w = max(name_w, 6)
            type_w = max(type_w, 4)

            sections.append(f"  {'Column':<{name_w}}  {'Type':<{type_w}}  Key")
            sections.append(f"  {'-' * name_w}  {'-' * type_w}  ---")
            for col in cols:
                key = ""
                if col["name"].lower() in pk_lookup.get(tbl_lower, set()):
                    key = "PK"
                elif col["name"].lower() in fk_lookup.get(tbl_lower, set()):
                    key = "FK"
                dt = col.get("dataType", "")
                sections.append(f"  {col['name']:<{name_w}}  {dt:<{type_w}}  {key}")

        measures = table.get("measures", [])
        if measures:
            sections.append(f"\n  Measures ({len(measures)}):")
            for m in measures:
                sections.append(f"    - {m['name']}")

        sections.append("")

    if relationships:
        sections.append("Relationships")
        sections.append("=============")
        for rel in relationships:
            active = "" if rel.get("isActive", True) else " [inactive]"
            cf = rel.get("crossFilteringBehavior", "oneDirection")
            sections.append(
                f"  {rel['fromTable']}.{rel['fromColumn']} --> "
                f"{rel['toTable']}.{rel['toColumn']}  "
                f"(crossFilter: {cf}){active}"
            )
        sections.append("")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Domain inference
# ---------------------------------------------------------------------------

def _infer_domains(model: dict) -> dict[str, dict]:
    """
    Return {domain_name: {"tables": [...], "measures": [...], "relationships": [...]}}.

    Inference priority:
      1. Measure displayFolder (most explicit signal from PBI model authors)
      2. Table name prefix (e.g., Sales_Fact -> "Sales")
      3. Relationship connectivity (connected-component grouping)
    """
    tables = model.get("tables", [])
    relationships = model.get("relationships", [])

    table_domain: dict[str, str] = {}
    domain_measures: dict[str, list] = defaultdict(list)

    # --- Pass 1: displayFolder -------------------------------------------------
    folder_to_tables: dict[str, set] = defaultdict(set)
    for table in tables:
        for m in table.get("measures", []):
            folder = (m.get("displayFolder") or "").strip()
            if folder:
                top = folder.split("\\")[0].split("/")[0].strip()
                folder_to_tables[top].add(table["name"])
                domain_measures[top].append(m["name"])

    for domain, tbl_set in folder_to_tables.items():
        for t in tbl_set:
            if t not in table_domain:
                table_domain[t] = domain

    # --- Pass 2: table name prefix ---------------------------------------------
    prefix_groups: dict[str, list] = defaultdict(list)
    for table in tables:
        name = table["name"]
        if name in table_domain:
            continue
        match = re.match(r"^([A-Z][a-z]+|[A-Z]+(?=[A-Z_]))", name)
        if match:
            prefix_groups[match.group(1)].append(name)

    for prefix, tbl_names in prefix_groups.items():
        if len(tbl_names) >= 2:
            for t in tbl_names:
                if t not in table_domain:
                    table_domain[t] = prefix

    # --- Pass 3: relationship connectivity (union-find) ------------------------
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    all_table_names = [t["name"] for t in tables]
    for t in all_table_names:
        parent.setdefault(t, t)

    for rel in relationships:
        ft, tt = rel.get("fromTable", ""), rel.get("toTable", "")
        if ft and tt:
            union(ft, tt)

    component_tables: dict[str, list] = defaultdict(list)
    for t in all_table_names:
        component_tables[find(t)].append(t)

    for root, members in component_tables.items():
        assigned_domain = None
        for m in members:
            if m in table_domain:
                assigned_domain = table_domain[m]
                break
        if assigned_domain:
            for m in members:
                if m not in table_domain:
                    table_domain[m] = assigned_domain

    # --- Remaining tables go to "Unassigned" -----------------------------------
    for table in tables:
        if table["name"] not in table_domain:
            table_domain[table["name"]] = "Unassigned"

    # --- Build result ----------------------------------------------------------
    domains: dict[str, dict] = defaultdict(lambda: {"tables": [], "measures": [], "relationships": []})

    for table in tables:
        d = table_domain[table["name"]]
        domains[d]["tables"].append(table["name"])
        for m in table.get("measures", []):
            domains[d]["measures"].append(m["name"])

    for rel in relationships:
        ft = rel.get("fromTable", "")
        d = table_domain.get(ft, "Unassigned")
        domains[d]["relationships"].append(
            f"{rel['fromTable']}.{rel['fromColumn']} -> {rel['toTable']}.{rel['toColumn']}"
        )

    return dict(domains)


def render_domains_md(domains: dict[str, dict]) -> str:
    lines = ["# Data Domains\n"]
    lines.append("Domains inferred from Power BI measure display folders, table name patterns, and relationship connectivity.\n")

    for name in sorted(domains.keys()):
        info = domains[name]
        lines.append(f"## Domain: {name}\n")
        lines.append(f"**Tables:** {', '.join(info['tables'])}\n")
        if info["measures"]:
            lines.append(f"**Measures ({len(info['measures'])}):**")
            for m in info["measures"]:
                lines.append(f"- {m}")
            lines.append("")
        if info["relationships"]:
            lines.append("**Relationships:**")
            for r in info["relationships"]:
                lines.append(f"- {r}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate ERD and domain analysis from a parsed Power BI model"
    )
    parser.add_argument("pbi_json", help="Path to pbi_model.json (from parse_pbi_model.py)")
    parser.add_argument(
        "-o", "--output-dir",
        default=".",
        help="Directory to write erd.md and domains.md (default: current dir)",
    )
    args = parser.parse_args()

    with open(args.pbi_json) as f:
        model = json.load(f)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- ERD -------------------------------------------------------------------
    mermaid = generate_mermaid(model)
    text_erd = generate_text_erd(model)

    erd_path = out_dir / "erd.md"
    with open(erd_path, "w") as f:
        f.write("# Entity-Relationship Diagram\n\n")
        f.write("## Mermaid ERD\n\n")
        f.write("```mermaid\n")
        f.write(mermaid)
        f.write("\n```\n\n")
        f.write("## Text ERD\n\n")
        f.write("```\n")
        f.write(text_erd)
        f.write("\n```\n")

    table_count = len(model.get("tables", []))
    rel_count = len(model.get("relationships", []))
    print(f"ERD: {table_count} tables, {rel_count} relationships -> {erd_path}")

    # --- Domains ---------------------------------------------------------------
    domains = _infer_domains(model)
    domains_md = render_domains_md(domains)

    domains_path = out_dir / "domains.md"
    with open(domains_path, "w") as f:
        f.write(domains_md)

    print(f"Domains: {len(domains)} domains -> {domains_path}")


if __name__ == "__main__":
    main()
