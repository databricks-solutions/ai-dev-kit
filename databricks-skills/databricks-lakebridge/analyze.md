# Analyze

The Analyze capability assesses source code complexity and generates a migration inventory. It produces a complexity score for each job/file, which feeds into the Conversion Calculator for migration planning.

Documentation: https://databrickslabs.github.io/lakebridge/assessment

## What It Does

- **Job complexity assessment**: Scores each source file/job by complexity (Simple, Medium, Complex, Very Complex)
- **Comprehensive inventory**: Maps programs, transformations, functions, variables, and dependencies
- **Cross-system interdependency mapping**: Identifies relationships between jobs and systems

## Supported Source Technologies

Source technologies are frequently updated. Always check the official documentation for the latest list:
https://databrickslabs.github.io/lakebridge/assessment/analyzer

## CLI Commands

### analyze

Analyze source code and generate a complexity report:

```bash
databricks labs lakebridge analyze \
  --source-directory /path/to/source/code \
  --report-file /path/to/report.json \
  --source-tech <source_technology>
```

| Option | Description |
|--------|-------------|
| `--source-directory` | Path to directory containing source code |
| `--report-file` | Output path for the analysis report (JSON) |
| `--source-tech` | Source technology identifier (see docs for valid values) |

## Complexity Scoring

The analyzer assigns complexity scores based on source-technology-specific rules. Scoring criteria vary by platform (SQL, DataStage, Talend, SSIS, Alteryx, BODS, SAS, Pentaho, etc.).

Scores feed into the Conversion Calculator to estimate migration effort and prioritize workloads.

For detailed scoring rules per technology, see:
https://databrickslabs.github.io/lakebridge/assessment/analyzer/complexity_scoring

## Metadata Export

Some source technologies require metadata extraction before analysis. The export process varies by platform:

- SQL-based systems: Extract DDL and stored procedures
- ETL tools: Export job definitions and metadata files

For platform-specific export instructions, see:
https://databrickslabs.github.io/lakebridge/assessment/analyzer/export_metadata
