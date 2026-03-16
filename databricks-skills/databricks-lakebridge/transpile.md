# Transpile

The Transpile capability converts SQL and ETL code from various source systems to Databricks-compatible formats. Lakebridge provides three transpiler engines with different strengths.

Documentation: https://databrickslabs.github.io/lakebridge/transpile

## Transpiler Comparison

| Transpiler | Approach | Strengths | Best For |
|------------|----------|-----------|----------|
| **BladeBridge** | Pattern-based (Perl + Python LSP) | Configurable rules, real-time LSP, handles ETL | DataStage, Informatica, large-scale SQL |
| **Morpheus** | Grammar-based (ANTLR + Scala) | Deterministic, strong equivalence | Snowflake, T-SQL to Databricks SQL |
| **Switch** | LLM-powered | Handles ambiguity, non-SQL formats, extensible | Complex SQL, Airflow, Python/Scala, custom sources |

## Supported Source Dialects

Source dialects and transpiler coverage are frequently updated. Always check the official documentation:
https://databrickslabs.github.io/lakebridge/transpile

## CLI Commands

### install-transpile

Install transpiler components to the Databricks workspace:

```bash
# Install core transpilers
databricks labs lakebridge install-transpile --profile <profile-name>

# Include LLM-powered Switch transpiler
databricks labs lakebridge install-transpile --include-llm-transpiler true --profile <profile-name>
```

### describe-transpile

Show installed transpiler configuration:

```bash
databricks labs lakebridge describe-transpile --profile <profile-name>
```

### transpile (BladeBridge / Morpheus)

Run pattern-based or grammar-based transpilation:

```bash
databricks labs lakebridge transpile \
  --transpiler-config-path /path/to/config.json \
  --input-source /path/to/input \
  --source-dialect <dialect> \
  --output-folder /path/to/output \
  --profile <profile-name>
```

| Option | Description |
|--------|-------------|
| `--transpiler-config-path` | Path to transpiler configuration JSON |
| `--input-source` | Path to source SQL/ETL files |
| `--source-dialect` | Source dialect (e.g., snowflake, tsql, oracle) |
| `--output-folder` | Local output directory |
| `--catalog-name` | Unity Catalog name (optional) |
| `--schema-name` | Schema name (optional) |
| `--skip-validation` | Skip output validation (optional) |

### llm-transpile (Switch)

Run LLM-powered transpilation:

```bash
databricks labs lakebridge llm-transpile \
  --input-source /path/to/input \
  --output-ws-folder /Workspace/Users/<user>/output \
  --source-dialect <dialect> \
  --accept-terms true \
  --profile <profile-name>
```

| Option | Description |
|--------|-------------|
| `--input-source` | Path to source files |
| `--output-ws-folder` | Workspace output folder path |
| `--source-dialect` | Source dialect (e.g., mssql, snowflake, oracle, airflow) |
| `--accept-terms` | Accept terms of service (required) |
| `--foundation-model` | Foundation model to use (optional) |
| `--catalog-name` | Unity Catalog name (optional) |
| `--schema-name` | Schema name (optional) |

## Switch Customization

Switch supports custom YAML prompts for extending transpilation behavior or adding new source types. For details on creating custom prompts, see:
https://databrickslabs.github.io/lakebridge/transpile/pluggable_transpilers/switch/customizing_switch

## Transpiler Configuration

BladeBridge and Morpheus use JSON configuration files for custom rules, schema mapping, and dialect-specific overrides. For configuration reference, see:
https://databrickslabs.github.io/lakebridge/transpile/pluggable_transpilers/bladebridge/bladebridge_configuration
