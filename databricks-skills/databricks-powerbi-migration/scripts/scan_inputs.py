#!/usr/bin/env python3
"""
Scan the input/ folder and classify every file by content.

Classifications:
  pbi_model         ZIP with DataModelSchema, BIM JSON, or TMDL
  mapping_json      JSON with a "mappings" array
  dbx_schema        JSON with catalog/schema/tables keys (extract_dbx_schema.py output)
  sql_ddl           Text containing CREATE TABLE / CREATE VIEW statements
  sql_query_output  Text resembling DESCRIBE TABLE or INFORMATION_SCHEMA output
  csv_schema_dump   CSV with schema-shaped headers (table_name, column_name, data_type)
  csv_data          CSV file (headers can inform schema)
  sample_report     Document/image that may contain report layout (.docx, .pdf, .png, .jpg, .xlsx, .pptx)
  databricks_config YAML with host/token keys
  unknown           Anything else

Usage:
    python scan_inputs.py <input_dir> [-o manifest.json]

No external dependencies required (stdlib only).
"""

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Classifiers -- each returns (type, format_or_none, details) or None
# ---------------------------------------------------------------------------

def _try_pbi_model(path: Path) -> tuple[str, str, str] | None:
    """Detect Power BI model files (ZIP/JSON/TMDL)."""
    if path.is_dir():
        if (path / "tables").is_dir() or (path / "definition" / "tables").is_dir():
            tmdl_count = sum(
                1 for _ in (path / "tables").glob("*.tmdl")
            ) if (path / "tables").is_dir() else sum(
                1 for _ in (path / "definition" / "tables").glob("*.tmdl")
            )
            return ("pbi_model", "tmdl", f"TMDL directory with {tmdl_count} table files")
        return None

    if zipfile.is_zipfile(str(path)):
        try:
            with zipfile.ZipFile(str(path), "r") as zf:
                names = zf.namelist()
                has_schema = any("datamodelschema" in n.lower() for n in names)
                if has_schema:
                    ext = path.suffix.lstrip(".").lower()
                    fmt = ext if ext in ("pbit", "pbix") else "pbit"
                    raw = None
                    for candidate in ("DataModelSchema", "DataModelSchema.json"):
                        if candidate in names:
                            raw = zf.read(candidate)
                            break
                    if raw is None:
                        for n in names:
                            if "datamodelschema" in n.lower():
                                raw = zf.read(n)
                                break
                    details = f"ZIP archive ({fmt})"
                    if raw:
                        try:
                            for enc in ("utf-16-le", "utf-8-sig", "utf-8"):
                                try:
                                    text = raw.decode(enc).lstrip("\ufeff")
                                    break
                                except (UnicodeDecodeError, ValueError):
                                    continue
                            else:
                                text = raw.decode("utf-8", errors="replace")
                            mj = json.loads(text)
                            model = mj.get("model", mj)
                            tc = len(model.get("tables", []))
                            mc = sum(len(t.get("measures", [])) for t in model.get("tables", []))
                            details = f"{tc} tables, {mc} measures"
                        except Exception:
                            pass
                    return ("pbi_model", fmt, details)
        except (zipfile.BadZipFile, Exception):
            pass

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(data, dict):
            model = data.get("model", data)
            if isinstance(model, dict) and "tables" in model:
                tc = len(model.get("tables", []))
                mc = sum(len(t.get("measures", [])) for t in model.get("tables", []))
                return ("pbi_model", "bim", f"{tc} tables, {mc} measures")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        pass

    try:
        text = path.read_text(encoding="utf-8-sig")
        first_line = text.lstrip().split("\n", 1)[0].strip()
        if re.match(r"^(table|relationship)\s+", first_line):
            return ("pbi_model", "tmdl", "TMDL text file")
    except (UnicodeDecodeError, OSError):
        pass

    return None


def _try_mapping_json(path: Path) -> tuple[str, str | None, str] | None:
    if path.is_dir():
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(data, dict) and "mappings" in data and isinstance(data["mappings"], list):
            count = len(data["mappings"])
            return ("mapping_json", None, f"{count} table mapping(s)")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        pass
    return None


def _try_dbx_schema(path: Path) -> tuple[str, str | None, str] | None:
    if path.is_dir():
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(data, dict) and all(k in data for k in ("catalog", "schema", "tables")):
            tc = len(data.get("tables", []))
            return ("dbx_schema", None, f"{data['catalog']}.{data['schema']} -- {tc} tables")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        pass
    return None


def _try_sql_ddl(path: Path) -> tuple[str, str | None, str] | None:
    if path.is_dir():
        return None
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return None
    upper = text.upper()
    create_count = len(re.findall(r"\bCREATE\s+(OR\s+REPLACE\s+)?(TABLE|VIEW|MATERIALIZED\s+VIEW)\b", upper))
    if create_count > 0:
        return ("sql_ddl", None, f"{create_count} CREATE TABLE/VIEW statement(s)")
    return None


def _try_sql_query_output(path: Path) -> tuple[str, str | None, str] | None:
    """Detect pasted DESCRIBE TABLE or INFORMATION_SCHEMA output."""
    if path.is_dir():
        return None
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return None
    upper = text.upper()
    describe_markers = [
        r"\bDESCRIBE\s+(TABLE\s+)?EXTENDED\b",
        r"\bSHOW\s+TABLES\b",
        r"\bINFORMATION_SCHEMA\b",
        r"\btable_name\b.*\bcolumn_name\b.*\bdata_type\b",
    ]
    for marker in describe_markers:
        if re.search(marker, upper if marker.startswith(r"\b") else text, re.IGNORECASE):
            lines = [l for l in text.strip().splitlines() if l.strip()]
            return ("sql_query_output", None, f"Schema query output, {len(lines)} lines")

    # Heuristic: tab/pipe-separated rows that look like col_name | type patterns
    pipe_rows = re.findall(r"^\s*\w+\s*\|\s*\w+", text, re.MULTILINE)
    if len(pipe_rows) >= 3:
        return ("sql_query_output", None, f"Tabular schema output, {len(pipe_rows)} rows")

    return None


def _try_csv_schema_dump(path: Path) -> tuple[str, str | None, str] | None:
    """Detect CSV files containing schema metadata (INFORMATION_SCHEMA-style exports)."""
    if path.is_dir():
        return None
    if path.suffix.lower() not in (".csv", ".tsv"):
        return None
    try:
        text = path.read_text(encoding="utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        headers = next(reader, None)
        if not headers:
            return None
        normalized = [h.strip().lower().replace(" ", "_") for h in headers]
        has_table = any(h in ("table_name", "tablename", "table") for h in normalized)
        has_column = any(h in ("column_name", "columnname", "column") for h in normalized)
        if not (has_table and has_column):
            return None
        rows = list(reader)
        table_names = set()
        table_col_idx = next(
            (i for i, h in enumerate(normalized) if h in ("table_name", "tablename", "table")),
            0,
        )
        for row in rows:
            if len(row) > table_col_idx and row[table_col_idx].strip():
                table_names.add(row[table_col_idx].strip())
        return (
            "csv_schema_dump",
            None,
            f"Schema dump: {len(table_names)} tables, {len(rows)} columns",
        )
    except Exception:
        return None


def _try_csv(path: Path) -> tuple[str, str | None, str] | None:
    if path.is_dir():
        return None
    if path.suffix.lower() in (".csv", ".tsv"):
        try:
            text = path.read_text(encoding="utf-8-sig")
            reader = csv.reader(io.StringIO(text))
            headers = next(reader, None)
            row_count = sum(1 for _ in reader)
            if headers:
                cols = ", ".join(headers[:5])
                extra = f" + {len(headers) - 5} more" if len(headers) > 5 else ""
                return ("csv_data", None, f"{row_count} rows, columns: {cols}{extra}")
        except Exception:
            pass
    return None


def _try_databricks_config(path: Path) -> tuple[str, str | None, str] | None:
    if path.is_dir():
        return None
    if path.suffix.lower() not in (".yml", ".yaml"):
        return None
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return None
    has_host = bool(re.search(r"^host\s*:", text, re.MULTILINE))
    has_token = bool(re.search(r"^token\s*:", text, re.MULTILINE))
    has_profile = bool(re.search(r"^profile\s*:", text, re.MULTILINE))
    if has_host or has_token or has_profile:
        cat_match = re.search(r"^catalog\s*:\s*[\"']?(\S+)", text, re.MULTILINE)
        sch_match = re.search(r"^schema\s*:\s*[\"']?(\S+)", text, re.MULTILINE)
        parts = []
        if cat_match:
            cat_val = cat_match.group(1).strip("\"'")
            parts.append(f"catalog={cat_val}")
        if sch_match:
            sch_val = sch_match.group(1).strip("\"'")
            parts.append(f"schema={sch_val}")
        details = ", ".join(["Databricks config"] + parts) if parts else "Databricks config (host/token)"
        return ("databricks_config", None, details)
    return None


_SAMPLE_REPORT_EXTENSIONS = {
    ".docx", ".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".pptx", ".gif", ".bmp", ".tiff",
}


def _try_sample_report(path: Path) -> tuple[str, str | None, str] | None:
    """Detect document/image files that may contain sample report layouts."""
    if path.is_dir():
        return None
    if path.suffix.lower() in _SAMPLE_REPORT_EXTENSIONS:
        try:
            size = path.stat().st_size
            size_label = (
                f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"
            )
            ext = path.suffix.lstrip(".").upper()
            return ("sample_report", ext.lower(), f"{ext} file, {size_label}")
        except OSError:
            return None
    return None


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------

CLASSIFIERS = [
    _try_pbi_model,
    _try_mapping_json,
    _try_dbx_schema,
    _try_sql_ddl,
    _try_sql_query_output,
    _try_csv_schema_dump,
    _try_csv,
    _try_sample_report,
    _try_databricks_config,
]


def scan_directory(input_dir: Path) -> list[dict]:
    """Scan all files in input_dir and classify each one."""
    results = []

    entries = sorted(input_dir.iterdir(), key=lambda p: (p.is_dir(), p.name))
    for entry in entries:
        if entry.name.startswith("."):
            continue

        classified = False
        for classifier in CLASSIFIERS:
            hit = classifier(entry)
            if hit:
                file_type, fmt, details = hit
                record = {
                    "path": str(entry),
                    "name": entry.name,
                    "type": file_type,
                    "details": details,
                }
                if fmt:
                    record["format"] = fmt
                results.append(record)
                classified = True
                break

        if not classified:
            try:
                if entry.is_file():
                    size = entry.stat().st_size
                    line_count = len(entry.read_text(errors="replace").splitlines())
                    details = f"{line_count} lines, {size} bytes"
                else:
                    details = "Directory"
            except OSError:
                details = "Unreadable"
            results.append({
                "path": str(entry),
                "name": entry.name,
                "type": "unknown",
                "details": details,
            })

    return results


def render_summary(files: list[dict]) -> str:
    """Return a human-readable summary of classified files."""
    lines = [f"Found {len(files)} file(s) in input folder:\n"]
    type_icons = {
        "pbi_model": "[PBI MODEL]",
        "mapping_json": "[MAPPING]",
        "dbx_schema": "[DBX SCHEMA]",
        "sql_ddl": "[SQL DDL]",
        "sql_query_output": "[QUERY OUTPUT]",
        "csv_schema_dump": "[CSV SCHEMA]",
        "csv_data": "[CSV]",
        "sample_report": "[REPORT]",
        "databricks_config": "[CONFIG]",
        "unknown": "[UNKNOWN]",
    }
    for f in files:
        icon = type_icons.get(f["type"], "[?]")
        fmt = f" ({f['format']})" if "format" in f else ""
        lines.append(f"  {icon} {f['name']}{fmt} -- {f['details']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Scan and classify all files in the input directory"
    )
    parser.add_argument("input_dir", help="Path to the input directory")
    parser.add_argument("-o", "--output", default=None, help="Output manifest JSON path")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"Error: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    files = scan_directory(input_dir)
    manifest = {"input_dir": str(input_dir), "files": files}

    print(render_summary(files))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"\nManifest written to {out_path}")
    else:
        print(f"\nJSON manifest (use -o to save):")
        print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
