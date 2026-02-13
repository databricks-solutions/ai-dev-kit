"""Schema introspection utilities wrapping dbldatagen's DataAnalyzer.

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user notebooks and scripts.
"""

from pyspark.sql import DataFrame, SparkSession


def summarize_table(spark: SparkSession, table_name: str) -> DataFrame:
    """Summarize an existing Unity Catalog table's schema and data characteristics.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified UC table name (catalog.schema.table).

    Returns:
        Summary DataFrame with column-level statistics.
    """
    from dbldatagen import DataAnalyzer

    df = spark.table(table_name)
    analyzer = DataAnalyzer(df=df, sparkSession=spark)
    return analyzer.summarizeToDF()


def generate_from_table(spark: SparkSession, table_name: str,
                        rows: int = None, name: str = None) -> str:
    """Generate dbldatagen code matching an existing UC table's schema and distributions.

    Analyzes the table's data to produce a DataGenerator script with appropriate
    min/max values, null probabilities, and type mappings.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified UC table name (catalog.schema.table).
        rows: Override row count in generated code (uses source count if None).
        name: Name for the generated DataGenerator (defaults to table name).

    Returns:
        Python code string for a DataGenerator spec.
    """
    from dbldatagen import DataAnalyzer

    df = spark.table(table_name)
    gen_name = name or table_name.split(".")[-1] + "_synth"
    analyzer = DataAnalyzer(df=df, sparkSession=spark)
    return analyzer.scriptDataGeneratorFromData(suppressOutput=True, name=gen_name)


def generate_from_schema(spark: SparkSession, table_name: str,
                         name: str = None) -> str:
    """Generate dbldatagen code from a UC table's schema only (no data analysis).

    Faster than generate_from_table but uses default value ranges instead of
    actual data statistics.

    Args:
        spark: Active SparkSession.
        table_name: Fully qualified UC table name (catalog.schema.table).
        name: Name for the generated DataGenerator (defaults to table name).

    Returns:
        Python code string for a DataGenerator spec.
    """
    from dbldatagen import DataAnalyzer

    schema = spark.table(table_name).schema
    gen_name = name or table_name.split(".")[-1] + "_synth"
    return DataAnalyzer.scriptDataGeneratorFromSchema(
        schema, suppressOutput=True, name=gen_name
    )
