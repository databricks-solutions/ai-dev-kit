"""Output utilities for writing synthetic data.

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user notebooks and scripts.
"""

from pyspark.sql import DataFrame


def write_delta(
    df: DataFrame,
    catalog: str,
    schema: str,
    table: str,
    mode: str = "overwrite",
    ensure_exists: bool = False,
) -> None:
    """Write DataFrame to Delta Lake table.

    Args:
        df: Spark DataFrame to write
        catalog: Unity Catalog name
        schema: Schema/database name
        table: Table name
        mode: Write mode (overwrite, append)
        ensure_exists: If True, create catalog and schema via Databricks SDK before writing
    """
    if ensure_exists:
        from .uc_setup import ensure_uc_path
        ensure_uc_path(catalog, schema)
    full_name = f"{catalog}.{schema}.{table}"
    df.write.format("delta").mode(mode).saveAsTable(full_name)


def write_parquet(df: DataFrame, path: str, mode: str = "overwrite") -> None:
    """Write DataFrame to Parquet files."""
    df.write.mode(mode).parquet(path)


def write_csv(df: DataFrame, path: str, mode: str = "overwrite") -> None:
    """Write DataFrame to CSV files."""
    df.write.mode(mode).option("header", True).csv(path)


def write_to_volume(
    df: DataFrame,
    volume_path: str,
    format: str = "json",
    mode: str = "overwrite",
    ensure_exists: bool = False,
    catalog: str | None = None,
    schema: str | None = None,
    volume: str | None = None,
):
    """Write DataFrame to UC Volume.

    Args:
        df: Spark DataFrame to write
        volume_path: Full volume path (e.g. /Volumes/catalog/schema/volume/subdir)
        format: Output format (json, csv, parquet)
        mode: Write mode (overwrite, append)
        ensure_exists: If True, create catalog, schema, and volume via Databricks SDK
        catalog: Required when ensure_exists=True
        schema: Required when ensure_exists=True
        volume: Required when ensure_exists=True
    """
    if ensure_exists:
        if not all([catalog, schema, volume]):
            raise ValueError(
                "catalog, schema, and volume are required when ensure_exists=True"
            )
        from .uc_setup import ensure_uc_path
        ensure_uc_path(catalog, schema, volume)
    df.write.format(format).mode(mode).save(volume_path)


def write_medallion(
    tables: dict,
    catalog: str,
    schema: str,
    volume: str = "raw_data",
    ensure_exists: bool = False,
):
    """Write raw data to Volume and cleaned data to Delta tables.

    Args:
        tables: Dict of {"table_name": (raw_df, clean_df)} or {"table_name": df}
            When a tuple is provided, raw_df goes to Volume as JSON and clean_df
            goes to Delta. When a single df is provided, it writes directly to Delta.
        catalog: Unity Catalog name
        schema: Schema name
        volume: Volume name for raw data
        ensure_exists: If True, create catalog, schema, and volume via Databricks SDK
    """
    if ensure_exists:
        from .uc_setup import ensure_uc_path
        ensure_uc_path(catalog, schema, volume)
    for name, data in tables.items():
        if isinstance(data, tuple):
            raw_df, clean_df = data
            raw_df.write.format("json").mode("overwrite").save(
                f"/Volumes/{catalog}/{schema}/{volume}/{name}")
            clean_df.write.format("delta").mode("overwrite").saveAsTable(
                f"{catalog}.{schema}.{name}")
        else:
            data.write.format("delta").mode("overwrite").saveAsTable(
                f"{catalog}.{schema}.{name}")
