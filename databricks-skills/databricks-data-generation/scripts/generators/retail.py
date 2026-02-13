"""Retail industry synthetic data generators.

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user notebooks and scripts.
"""

# CONNECT COMPATIBILITY NOTES:
#   Catalyst-safe (works over Connect):
#     - values=/weights=, minValue/maxValue, begin/end dates, expr=, percentNulls=, omit=
#   UDF-dependent (notebook only — apply workarounds for Connect):
#     - text=mimesisText() → values=["James","Mary",...], random=True
#     - template=r"ddddd" → expr="lpad(cast(floor(rand()*100000) as string), 5, '0')"
#     - distribution=Gamma/Beta → random=True or expr= math
#     - .withConstraint() → .build().filter("condition")

import dbldatagen as dg
from dbldatagen.constraints import PositiveValues, SqlExpr
from pyspark.sql import DataFrame
from utils.mimesis_text import mimesisText


def generate_customers(spark, rows=100_000, seed=42) -> DataFrame:
    """Generate retail customer master data with demographics and loyalty tiers."""
    partitions = max(4, rows // 100_000)
    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=rows)
        .withColumn("first_name", "string", text=mimesisText("person.first_name"))
        .withColumn("last_name", "string", text=mimesisText("person.last_name"))
        .withColumn("email", "string", text=mimesisText("person.email"), percentNulls=0.02)
        .withColumn("phone", "string", text=mimesisText("person.telephone"), percentNulls=0.01)
        .withColumn("city", "string", text=mimesisText("address.city"))
        .withColumn("state", "string", values=["NY", "CA", "IL", "TX", "AZ", "PA", "FL", "OH", "NC", "GA"])
        .withColumn("zip_code", "string", template=r"ddddd")
        .withColumn("signup_date", "date", begin="2020-01-01", end="2024-12-31", random=True)
        .withColumn("tenure_months", "integer",
                    expr="months_between(current_date(), signup_date)", omit=True)
        .withColumn("loyalty_tier", "string",
                    expr="""CASE
                        WHEN tenure_months > 48 THEN 'Platinum'
                        WHEN tenure_months > 24 THEN 'Gold'
                        WHEN tenure_months > 12 THEN 'Silver'
                        ELSE 'Bronze'
                    END""")
        .withColumn("lifetime_value", "decimal(12,2)", minValue=0, maxValue=50000,
                    distribution=dg.distributions.Gamma(shape=2.0, scale=2.0))
        .withColumn("is_active", "boolean", expr="rand() < 0.85")
        .build()
    )


def generate_products(spark, rows=10_000, seed=42) -> DataFrame:
    """Generate product catalog with categories, pricing, and cost data."""
    partitions = max(4, rows // 50_000)
    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("product_id", "long", minValue=10_000, uniqueValues=rows)
        .withColumn("sku", "string", template=r"SKU-dddddddd")
        .withColumn("product_name", "string", prefix="Product-", baseColumn="product_id")
        .withColumn("category", "string",
                    values=["Electronics", "Clothing", "Home & Garden", "Sports",
                            "Beauty", "Food & Grocery", "Toys", "Automotive"])
        .withColumn("brand", "string",
                    values=["BrandA", "BrandB", "BrandC", "BrandD", "BrandE", "Generic"])
        .withColumn("unit_price", "decimal(10,2)", minValue=5, maxValue=500, random=True)
        .withColumn("cost", "decimal(10,2)", expr="unit_price * (0.4 + rand() * 0.3)")
        .withColumn("weight_kg", "decimal(6,2)", minValue=0.1, maxValue=50, random=True)
        .withColumn("is_active", "boolean", expr="rand() < 0.95")
        .withColumn("created_date", "date", begin="2018-01-01", end="2024-12-31", random=True)
        .build()
    )


def generate_transactions(spark, rows=1_000_000, n_customers=100_000, seed=42) -> DataFrame:
    """Generate retail transactions with payment methods and computed totals."""
    partitions = max(10, rows // 100_000)
    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("txn_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("customer_id", "long",
                    minValue=1_000_000, maxValue=1_000_000 + n_customers - 1)
        .withColumn("store_id", "long", minValue=100, maxValue=150)
        .withColumn("txn_timestamp", "timestamp",
                    begin="2024-01-01 00:00:00", end="2024-12-31 23:59:59", random=True)
        .withColumn("payment_method", "string",
                    values=["Credit Card", "Debit Card", "Cash", "Digital Wallet", "Gift Card"],
                    weights=[40, 25, 15, 15, 5])
        .withColumn("subtotal", "decimal(12,2)", minValue=10, maxValue=500,
                    distribution=dg.distributions.Gamma(shape=2.0, scale=2.0), omit=True)
        .withColumn("discount_pct", "float", minValue=0.0, maxValue=0.3,
                    distribution=dg.distributions.Beta(alpha=2, beta=5), omit=True)
        .withColumn("discount_amount", "decimal(10,2)", expr="subtotal * discount_pct",
                    percentNulls=0.02)
        .withColumn("tax_amount", "decimal(10,2)",
                    expr="(subtotal - coalesce(discount_amount, 0)) * 0.08")
        .withColumn("total_amount", "decimal(12,2)",
                    expr="subtotal - coalesce(discount_amount, 0) + tax_amount")
        .withColumn("items_count", "integer", minValue=1, maxValue=20, distribution=dg.distributions.Exponential())
        .withConstraint(PositiveValues(columns="total_amount", strict=True))
        .withConstraint(SqlExpr("coalesce(discount_amount, 0) <= subtotal"))
        .build()
    )


def generate_line_items(spark, rows=3_000_000, n_transactions=1_000_000,
                        n_products=10_000, seed=42) -> DataFrame:
    """Generate transaction line items linking transactions to products."""
    partitions = max(20, rows // 100_000)
    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("line_item_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("txn_id", "long", minValue=1, maxValue=n_transactions)
        .withColumn("product_id", "long", minValue=10_000, maxValue=10_000 + n_products - 1)
        .withColumn("quantity", "integer", minValue=1, maxValue=10, distribution=dg.distributions.Exponential())
        .withColumn("unit_price", "decimal(10,2)", minValue=5, maxValue=500, random=True)
        .withColumn("line_total", "decimal(12,2)", expr="quantity * unit_price")
        .build()
    )


def generate_inventory(spark, rows=500_000, n_products=10_000, seed=42) -> DataFrame:
    """Generate inventory levels by product and store location."""
    partitions = max(4, rows // 50_000)
    return (
        dg.DataGenerator(spark, rows=rows, partitions=partitions, randomSeed=seed)
        .withColumn("inventory_id", "long", minValue=1, uniqueValues=rows)
        .withColumn("product_id", "long", minValue=10_000, maxValue=10_000 + n_products - 1)
        .withColumn("store_id", "long", minValue=100, maxValue=150)
        .withColumn("quantity_on_hand", "integer", minValue=0, maxValue=500,
                    distribution=dg.distributions.Exponential())
        .withColumn("reorder_point", "integer", minValue=10, maxValue=50, random=True)
        .withColumn("last_updated", "timestamp",
                    begin="2024-01-01 00:00:00", end="2024-12-31 23:59:59", random=True)
        .build()
    )


def generate_retail_cdc(spark, volume_path, n_customers=100_000, n_batches=5, seed=42):
    """Generate retail CDC data and write to UC Volume.

    Creates an initial full load of customers followed by incremental CDC batches
    with APPEND/UPDATE/DELETE operations.
    """
    from .cdc import add_cdc_operations, write_cdc_to_volume

    for i in range(n_batches):
        rows = n_customers if i == 0 else n_customers // 10
        base_df = generate_customers(spark, rows=rows, seed=seed + i)
        weights = {"APPEND": 100} if i == 0 else {"APPEND": 50, "UPDATE": 30, "DELETE": 10}
        cdc_df = add_cdc_operations(base_df, weights=weights)
        write_cdc_to_volume(cdc_df, volume_path, batch_id=i)


def generate_retail_demo(spark, catalog, schema="retail", volume="raw_data",
                         n_customers=100_000, seed=42):
    """Generate complete retail demo dataset with all tables.

    Writes raw JSON to UC Volume and clean Delta tables to the catalog.
    """
    from ..utils.output import write_medallion

    n_products = 10_000
    n_transactions = n_customers * 10
    n_line_items = n_transactions * 3

    customers = generate_customers(spark, rows=n_customers, seed=seed)
    products = generate_products(spark, rows=n_products, seed=seed)
    transactions = generate_transactions(spark, rows=n_transactions,
                                         n_customers=n_customers, seed=seed)
    line_items = generate_line_items(spark, rows=n_line_items,
                                     n_transactions=n_transactions,
                                     n_products=n_products, seed=seed)
    inventory = generate_inventory(spark, rows=n_products * 50,
                                   n_products=n_products, seed=seed)

    write_medallion(
        tables={
            "customers": customers,
            "products": products,
            "transactions": transactions,
            "line_items": line_items,
            "inventory": inventory,
        },
        catalog=catalog,
        schema=schema,
        volume=volume,
    )
