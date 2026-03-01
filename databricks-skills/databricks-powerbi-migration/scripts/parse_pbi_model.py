#!/usr/bin/env python3
"""
Parse Power BI semantic model exports into structured JSON.

Detects format by content (not extension), supporting:
  - PBIT / PBIX files (ZIP archives containing DataModelSchema)
  - BIM files (JSON with a model key)
  - TMDL directories or standalone .tmdl files
  - Any file with an unknown extension -- probed as ZIP, then JSON, then TMDL text

Single-file mode:
    python parse_pbi_model.py input/model.pbix -o reference/pbi_model.json

Batch mode (scans a directory for all PBI model files):
    python parse_pbi_model.py input/ -o reference/pbi_model.json

No external dependencies required (stdlib only).
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Format-specific parsers (unchanged)
# ---------------------------------------------------------------------------

def parse_zip_model(zip_path: str) -> dict:
    """Parse a ZIP archive (PBIT or PBIX) containing DataModelSchema."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        schema_name = _find_data_model_schema(zf)
        if not schema_name:
            raise ValueError(
                f"No DataModelSchema found in {zip_path}. "
                f"Contents: {zf.namelist()}"
            )

        raw = zf.read(schema_name)
        for encoding in ("utf-16-le", "utf-8-sig", "utf-8"):
            try:
                text = raw.decode(encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue
        else:
            text = raw.decode("utf-8", errors="replace")

        text = text.lstrip("\ufeff")
        model_json = json.loads(text)

    model = model_json.get("model", model_json)
    result = _parse_model_dict(model)
    result["source"] = str(zip_path)
    ext = Path(zip_path).suffix.lstrip(".").lower() or "zip"
    result["format"] = ext if ext in ("pbit", "pbix") else "pbit"
    return result


def _find_data_model_schema(zf: zipfile.ZipFile) -> str | None:
    for candidate in ("DataModelSchema", "DataModelSchema.json"):
        if candidate in zf.namelist():
            return candidate
    for name in zf.namelist():
        if "datamodelschema" in name.lower():
            return name
    return None


def parse_bim(bim_path: str) -> dict:
    """Parse a model.bim (JSON) file."""
    with open(bim_path, "r", encoding="utf-8-sig") as f:
        model_json = json.load(f)

    model = model_json.get("model", model_json)
    result = _parse_model_dict(model)
    result["source"] = str(bim_path)
    result["format"] = "bim"
    return result


def _parse_model_dict(model: dict) -> dict:
    """Parse a model dictionary (shared by BIM, PBIT, and PBIX formats)."""
    result = {
        "source": "",
        "format": "",
        "tables": [],
        "relationships": [],
        "roles": [],
    }

    for table in model.get("tables", []):
        table_info = {
            "name": table["name"],
            "columns": [],
            "measures": [],
            "calculated_columns": [],
            "partitions": [],
        }

        for col in table.get("columns", []):
            col_info = {
                "name": col["name"],
                "dataType": col.get("dataType", ""),
                "sourceColumn": col.get("sourceColumn", ""),
                "isHidden": col.get("isHidden", False),
                "formatString": col.get("formatString", ""),
            }
            if "expression" in col:
                col_info["expression"] = _normalize_expression(col["expression"])
                table_info["calculated_columns"].append(col_info)
            else:
                table_info["columns"].append(col_info)

        for measure in table.get("measures", []):
            table_info["measures"].append({
                "name": measure["name"],
                "expression": _normalize_expression(measure.get("expression", "")),
                "displayFolder": measure.get("displayFolder", ""),
                "formatString": measure.get("formatString", ""),
                "description": measure.get("description", ""),
            })

        for partition in table.get("partitions", []):
            source = partition.get("source", {})
            table_info["partitions"].append({
                "name": partition.get("name", ""),
                "type": source.get("type", ""),
                "expression": _normalize_expression(source.get("expression", "")),
            })

        result["tables"].append(table_info)

    for rel in model.get("relationships", []):
        result["relationships"].append({
            "fromTable": rel.get("fromTable", ""),
            "fromColumn": rel.get("fromColumn", ""),
            "toTable": rel.get("toTable", ""),
            "toColumn": rel.get("toColumn", ""),
            "crossFilteringBehavior": rel.get("crossFilteringBehavior", "oneDirection"),
            "isActive": rel.get("isActive", True),
        })

    for role in model.get("roles", []):
        role_info = {"name": role["name"], "filters": []}
        for perm in role.get("tablePermissions", []):
            role_info["filters"].append({
                "table": perm.get("name", ""),
                "filterExpression": perm.get("filterExpression", ""),
            })
        result["roles"].append(role_info)

    return result


def parse_tmdl(tmdl_dir: str) -> dict:
    """Parse a TMDL directory export."""
    result = {
        "source": str(tmdl_dir),
        "format": "tmdl",
        "tables": [],
        "relationships": [],
        "roles": [],
    }

    base = Path(tmdl_dir)
    tables_dir = base / "tables"
    if not tables_dir.exists():
        tables_dir = base / "definition" / "tables"

    if tables_dir.exists():
        for tmdl_file in sorted(tables_dir.glob("*.tmdl")):
            table_info = _parse_tmdl_table(tmdl_file)
            if table_info:
                result["tables"].append(table_info)

    rel_file = base / "relationships.tmdl"
    if not rel_file.exists():
        rel_file = base / "definition" / "relationships.tmdl"
    if rel_file.exists():
        result["relationships"] = _parse_tmdl_relationships(rel_file)

    roles_dir = base / "roles"
    if not roles_dir.exists():
        roles_dir = base / "definition" / "roles"
    if roles_dir.exists():
        for role_file in sorted(roles_dir.glob("*.tmdl")):
            role_info = _parse_tmdl_role(role_file)
            if role_info:
                result["roles"].append(role_info)

    return result


def _parse_tmdl_table(filepath: Path) -> dict | None:
    content = filepath.read_text(encoding="utf-8-sig")
    table_match = re.search(r"^table\s+'?([^'\n]+)'?\s*$", content, re.MULTILINE)
    if not table_match:
        return None

    table_info = {
        "name": table_match.group(1).strip(),
        "columns": [],
        "measures": [],
        "calculated_columns": [],
        "partitions": [],
    }

    for m in re.finditer(
        r"column\s+'?([^'\n]+)'?\s*\n((?:\t[^\n]*\n)*)", content
    ):
        col_name = m.group(1).strip()
        col_body = m.group(2)
        col_info = {"name": col_name, "dataType": "", "sourceColumn": ""}

        dt = re.search(r"dataType:\s*(\S+)", col_body)
        if dt:
            col_info["dataType"] = dt.group(1)
        sc = re.search(r"sourceColumn:\s*(.+)", col_body)
        if sc:
            col_info["sourceColumn"] = sc.group(1).strip()

        expr = re.search(r"expression\s*=\s*(.+?)(?=\n\t\w|\Z)", col_body, re.DOTALL)
        if expr:
            col_info["expression"] = _normalize_expression(expr.group(1))
            table_info["calculated_columns"].append(col_info)
        else:
            table_info["columns"].append(col_info)

    for m in re.finditer(
        r"measure\s+'?([^'\n]+)'?\s*=\s*(.*?)(?=\n\tmeasure\s|\n\tcolumn\s|\n\tpartition\s|\nrelationship\s|\Z)",
        content,
        re.DOTALL,
    ):
        measure_name = m.group(1).strip()
        measure_body = m.group(2).strip()
        lines = measure_body.split("\n")
        expr_lines = []
        meta = {}
        for line in lines:
            stripped = line.strip()
            kv = re.match(r"^(displayFolder|formatString|description)\s*:\s*(.*)", stripped)
            if kv:
                meta[kv.group(1)] = kv.group(2).strip()
            else:
                expr_lines.append(stripped)

        table_info["measures"].append({
            "name": measure_name,
            "expression": _normalize_expression("\n".join(expr_lines)),
            "displayFolder": meta.get("displayFolder", ""),
            "formatString": meta.get("formatString", ""),
            "description": meta.get("description", ""),
        })

    return table_info


def _parse_tmdl_relationships(filepath: Path) -> list:
    content = filepath.read_text(encoding="utf-8-sig")
    relationships = []
    for m in re.finditer(r"relationship\s+.*?\n((?:\t[^\n]*\n)*)", content):
        body = m.group(1)
        rel = {}
        ft = re.search(r"fromTable:\s*'?([^'\n]+)", body)
        fc = re.search(r"fromColumn:\s*'?([^'\n]+)", body)
        tt = re.search(r"toTable:\s*'?([^'\n]+)", body)
        tc = re.search(r"toColumn:\s*'?([^'\n]+)", body)
        if ft:
            rel["fromTable"] = ft.group(1).strip()
        if fc:
            rel["fromColumn"] = fc.group(1).strip()
        if tt:
            rel["toTable"] = tt.group(1).strip()
        if tc:
            rel["toColumn"] = tc.group(1).strip()
        cf = re.search(r"crossFilteringBehavior:\s*(\S+)", body)
        if cf:
            rel["crossFilteringBehavior"] = cf.group(1)
        ia = re.search(r"isActive:\s*(\S+)", body)
        if ia:
            rel["isActive"] = ia.group(1).lower() == "true"
        if rel:
            relationships.append(rel)
    return relationships


def _parse_tmdl_role(filepath: Path) -> dict | None:
    content = filepath.read_text(encoding="utf-8-sig")
    role_match = re.search(r"^role\s+'?([^'\n]+)'?\s*$", content, re.MULTILINE)
    if not role_match:
        return None
    return {"name": role_match.group(1).strip(), "filters": []}


def _normalize_expression(expr) -> str:
    if isinstance(expr, list):
        expr = "\n".join(expr)
    if not isinstance(expr, str):
        return str(expr)
    return re.sub(r"\s+", " ", expr).strip()


# ---------------------------------------------------------------------------
# Content-based detection
# ---------------------------------------------------------------------------

def _is_tmdl_directory(path: Path) -> bool:
    """Check if a directory looks like a TMDL export."""
    return (
        (path / "tables").is_dir()
        or (path / "definition" / "tables").is_dir()
    )


def detect_and_parse(path: Path) -> dict | None:
    """Detect the format of a file by probing its content and parse it.

    Returns the parsed model dict, or None if the file is not a
    recognizable Power BI model.
    """
    if path.is_dir():
        if _is_tmdl_directory(path):
            return parse_tmdl(str(path))
        return None

    # 1. Try ZIP (handles .pbit, .pbix, .zip, or any extension)
    if zipfile.is_zipfile(str(path)):
        try:
            with zipfile.ZipFile(str(path), "r") as zf:
                if _find_data_model_schema(zf):
                    return parse_zip_model(str(path))
        except (zipfile.BadZipFile, Exception):
            pass

    # 2. Try JSON (handles .bim, .json, or any extension)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(data, dict):
            model = data.get("model", data)
            if isinstance(model, dict) and "tables" in model:
                result = _parse_model_dict(model)
                result["source"] = str(path)
                result["format"] = "bim"
                return result
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        pass

    # 3. Try TMDL text (handles .tmdl or any text file with TMDL content)
    try:
        text = path.read_text(encoding="utf-8-sig")
        first_line = text.lstrip().split("\n", 1)[0].strip()
        if re.match(r"^(table|relationship)\s+", first_line):
            table_info = _parse_tmdl_table(path)
            if table_info:
                return {
                    "source": str(path),
                    "format": "tmdl",
                    "tables": [table_info],
                    "relationships": [],
                    "roles": [],
                }
    except (UnicodeDecodeError, OSError):
        pass

    return None


def parse_directory(input_dir: Path) -> list[dict]:
    """Parse all recognizable PBI model files/subdirs in a directory."""
    models = []

    for child in sorted(input_dir.iterdir()):
        if child.name.startswith("."):
            continue
        result = detect_and_parse(child)
        if result:
            models.append(result)
            _print_model_summary(result)
        else:
            if child.is_file():
                print(f"  Skipped (not a PBI model): {child.name}", file=sys.stderr)

    return models


def _print_model_summary(model: dict) -> None:
    table_count = len(model["tables"])
    measure_count = sum(len(t["measures"]) for t in model["tables"])
    rel_count = len(model["relationships"])
    fmt = model.get("format", "unknown")
    src = model.get("source", "?")
    print(
        f"  Parsed [{fmt}] {table_count} tables, {measure_count} measures, "
        f"{rel_count} relationships <- {src}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Parse Power BI model(s) to JSON. Detects format by content."
    )
    parser.add_argument(
        "path",
        help="Path to a PBI file (any extension), TMDL directory, or a "
             "directory of input files (batch mode)",
    )
    parser.add_argument("-o", "--output", default=None, help="Output JSON file path")
    args = parser.parse_args()

    path = Path(args.path)

    if path.is_dir() and not _is_tmdl_directory(path):
        # Batch mode: scan directory for all PBI model files
        print(f"Scanning {path} for Power BI models...")
        models = parse_directory(path)
        if not models:
            print("No Power BI model files found.", file=sys.stderr)
            sys.exit(1)

        if len(models) == 1:
            output_data = models[0]
        else:
            output_data = models

        output_path = args.output or "pbi_model.json"
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)

        print(f"\n{len(models)} model(s) -> {output_path}")
    else:
        # Single file/TMDL dir mode
        model = detect_and_parse(path)
        if not model:
            print(
                f"Error: Could not detect a Power BI model in {path}. "
                "Tried ZIP (PBIT/PBIX), JSON (BIM), and TMDL formats.",
                file=sys.stderr,
            )
            sys.exit(1)

        output_path = args.output or "pbi_model.json"
        with open(output_path, "w") as f:
            json.dump(model, f, indent=2)

        _print_model_summary(model)
        print(f"-> {output_path}")


if __name__ == "__main__":
    main()
