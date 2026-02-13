"""Local file output utilities for Tier 1 and Tier 2 data generation.

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user scripts.
"""

import os

import polars as pl


def ensure_output_dir(path: str = "output") -> str:
    """Create output directory if it doesn't exist. Returns the path."""
    os.makedirs(path, exist_ok=True)
    return path


def write_local_parquet(df: pl.DataFrame, table_name: str,
                        base_dir: str = "output",
                        industry: str = "") -> str:
    """Write a Polars DataFrame to local parquet.

    Returns the full file path written.
    Convention: output/{industry}/{table_name}.parquet
    """
    subdir = os.path.join(base_dir, industry) if industry else base_dir
    ensure_output_dir(subdir)
    path = os.path.join(subdir, f"{table_name}.parquet")
    df.write_parquet(path)
    return path


def write_local_csv(df: pl.DataFrame, table_name: str,
                    base_dir: str = "output",
                    industry: str = "") -> str:
    """Write a Polars DataFrame to local CSV.

    Returns the full file path written.
    Convention: output/{industry}/{table_name}.csv
    """
    subdir = os.path.join(base_dir, industry) if industry else base_dir
    ensure_output_dir(subdir)
    path = os.path.join(subdir, f"{table_name}.csv")
    df.write_csv(path)
    return path
