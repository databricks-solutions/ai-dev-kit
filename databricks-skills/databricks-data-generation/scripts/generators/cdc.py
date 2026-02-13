"""Cross-industry CDC helpers for synthetic data generation.

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user notebooks and scripts.
"""

from pyspark.sql import DataFrame, functions as F


def add_cdc_operations(df: DataFrame, weights=None) -> DataFrame:
    """Add CDC operation and operation_date columns to a DataFrame.

    Args:
        df: Source DataFrame
        weights: Dict of operation weights, e.g. {"APPEND": 50, "UPDATE": 30, "DELETE": 10}
    """
    if weights is None:
        weights = {"APPEND": 50, "UPDATE": 30, "DELETE": 10}

    ops = list(weights.keys())
    wts = list(weights.values())
    total = sum(wts)

    # Build cumulative probability expression
    conditions = []
    cumulative = 0
    for op, wt in zip(ops, wts):
        cumulative += wt / total
        conditions.append(f"WHEN rand_val < {cumulative} THEN '{op}'")

    case_expr = f"CASE {' '.join(conditions)} END"

    return (df
        .withColumn("rand_val", F.rand())
        .withColumn("operation", F.expr(case_expr))
        .withColumn("operation_date", F.current_timestamp())
        .drop("rand_val"))


def generate_cdc_batches(spark, spec_fn, n_batches=5, rows_per_batch=10_000, seed=42):
    """Generate multiple CDC batches from a spec-building function.

    Args:
        spark: SparkSession
        spec_fn: Function(spark, rows, seed) -> DataFrame that generates base data
        n_batches: Number of incremental batches
        rows_per_batch: Rows per incremental batch
        seed: Random seed

    Returns:
        List of DataFrames, one per batch
    """
    batches = []
    for i in range(n_batches):
        batch_weights = (
            {"APPEND": 100} if i == 0
            else {"APPEND": 50, "UPDATE": 30, "DELETE": 10}
        )
        base_df = spec_fn(spark, rows_per_batch, seed + i)
        cdc_df = add_cdc_operations(base_df, weights=batch_weights)
        batches.append(cdc_df)
    return batches


def write_cdc_to_volume(df: DataFrame, volume_path: str, batch_id: int = 0,
                        format="json"):
    """Write CDC DataFrame to UC Volume landing zone."""
    df.write.format(format).mode("overwrite").save(
        f"{volume_path}/batch_{batch_id}")
