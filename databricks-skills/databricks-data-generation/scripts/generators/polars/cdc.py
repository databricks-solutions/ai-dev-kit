"""Cross-industry CDC helpers for Polars-based synthetic data generation.

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user scripts. Uses pure Polars
for Tier 1 local CDC generation (zero JVM overhead).
"""

import random
from datetime import datetime

import polars as pl


def add_cdc_operations(df: pl.DataFrame, weights: dict[str, int] | None = None,
                       seed: int = 42) -> pl.DataFrame:
    """Add CDC operation and operation_date columns to a Polars DataFrame.

    Args:
        df: Source DataFrame
        weights: Dict of operation weights, e.g. {"APPEND": 50, "UPDATE": 30, "DELETE": 10}
        seed: Random seed for reproducibility
    """
    if weights is None:
        weights = {"APPEND": 50, "UPDATE": 30, "DELETE": 10}

    random.seed(seed)
    ops = list(weights.keys())
    wts = list(weights.values())
    operations = random.choices(ops, weights=wts, k=len(df))

    return df.with_columns(
        pl.Series("operation", operations),
        pl.lit(datetime.now()).alias("operation_date"),
    )
