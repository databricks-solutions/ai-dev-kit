"""Retail industry synthetic data generators (Polars + Mimesis).

REFERENCE IMPLEMENTATION — This file is not an importable module. Claude reads it
for patterns and adapts the code inline for user scripts. Uses pure Polars + Mimesis
for Tier 1 local generation (<100K rows, zero JVM overhead).
"""

import random
from datetime import date, datetime, timedelta

import polars as pl
from mimesis import Generic
from mimesis.locales import Locale

STATES = ["NY", "CA", "IL", "TX", "AZ", "PA", "FL", "OH", "NC", "GA"]
CATEGORIES = ["Electronics", "Clothing", "Home & Garden", "Sports",
              "Beauty", "Food & Grocery", "Toys", "Automotive"]
BRANDS = ["BrandA", "BrandB", "BrandC", "BrandD", "BrandE", "Generic"]
PAYMENT_METHODS = ["Credit Card", "Debit Card", "Cash", "Digital Wallet", "Gift Card"]
PAYMENT_WEIGHTS = [40, 25, 15, 15, 5]


def generate_customers(rows: int = 10_000, seed: int = 42) -> pl.DataFrame:
    """Generate retail customer master data with demographics and loyalty tiers."""
    random.seed(seed)
    g = Generic(locale=Locale.EN, seed=seed)

    signup_start = date(2020, 1, 1)
    signup_range = (date(2024, 12, 31) - signup_start).days
    today = date.today()

    customer_ids = list(range(1_000_000, 1_000_000 + rows))
    first_names = [g.person.first_name() for _ in range(rows)]
    last_names = [g.person.last_name() for _ in range(rows)]
    emails = [
        None if random.random() < 0.02
        else f"{fn.lower()}.{ln.lower()}{i % 1000}@example.com"
        for i, (fn, ln) in enumerate(zip(first_names, last_names))
    ]
    phones = [
        None if random.random() < 0.01 else g.person.telephone()
        for _ in range(rows)
    ]
    cities = [g.address.city() for _ in range(rows)]
    states = random.choices(STATES, k=rows)
    zip_codes = [f"{random.randint(10000, 99999)}" for _ in range(rows)]
    signup_dates = [signup_start + timedelta(days=random.randint(0, signup_range))
                    for _ in range(rows)]
    lifetime_values = [round(random.gammavariate(2.0, 2.0) * 2500, 2) for _ in range(rows)]
    is_active = [random.random() < 0.85 for _ in range(rows)]

    df = pl.DataFrame({
        "customer_id": customer_ids,
        "first_name": first_names,
        "last_name": last_names,
        "email": emails,
        "phone": phones,
        "city": cities,
        "state": states,
        "zip_code": zip_codes,
        "signup_date": signup_dates,
        "lifetime_value": lifetime_values,
        "is_active": is_active,
    })

    # Derived: loyalty_tier based on tenure
    return df.with_columns(
        pl.when((pl.col("signup_date").cast(pl.Date) < today) &
                ((today - pl.col("signup_date")).dt.total_days() > 48 * 30))
        .then(pl.lit("Platinum"))
        .when((today - pl.col("signup_date")).dt.total_days() > 24 * 30)
        .then(pl.lit("Gold"))
        .when((today - pl.col("signup_date")).dt.total_days() > 12 * 30)
        .then(pl.lit("Silver"))
        .otherwise(pl.lit("Bronze"))
        .alias("loyalty_tier")
    )


def generate_products(rows: int = 5_000, seed: int = 42) -> pl.DataFrame:
    """Generate product catalog with categories, pricing, and cost data."""
    random.seed(seed)

    product_ids = list(range(10_000, 10_000 + rows))
    skus = [f"SKU-{random.randint(10000000, 99999999)}" for _ in range(rows)]
    product_names = [f"Product-{pid}" for pid in product_ids]
    categories = random.choices(CATEGORIES, k=rows)
    brands = random.choices(BRANDS, k=rows)
    unit_prices = [round(random.uniform(5, 500), 2) for _ in range(rows)]
    costs = [round(p * (0.4 + random.random() * 0.3), 2) for p in unit_prices]
    weights_kg = [round(random.uniform(0.1, 50), 2) for _ in range(rows)]
    is_active = [random.random() < 0.95 for _ in range(rows)]
    created_start = date(2018, 1, 1)
    created_range = (date(2024, 12, 31) - created_start).days
    created_dates = [created_start + timedelta(days=random.randint(0, created_range))
                     for _ in range(rows)]

    return pl.DataFrame({
        "product_id": product_ids,
        "sku": skus,
        "product_name": product_names,
        "category": categories,
        "brand": brands,
        "unit_price": unit_prices,
        "cost": costs,
        "weight_kg": weights_kg,
        "is_active": is_active,
        "created_date": created_dates,
    })


def generate_transactions(rows: int = 50_000, n_customers: int = 10_000,
                          seed: int = 42) -> pl.DataFrame:
    """Generate retail transactions with payment methods and computed totals."""
    random.seed(seed)

    txn_ids = list(range(1, rows + 1))
    customer_ids = [random.randint(1_000_000, 1_000_000 + n_customers - 1)
                    for _ in range(rows)]
    store_ids = [random.randint(100, 150) for _ in range(rows)]
    ts_start = datetime(2024, 1, 1)
    ts_range = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())
    txn_timestamps = [ts_start + timedelta(seconds=random.randint(0, ts_range))
                      for _ in range(rows)]
    payment_methods = random.choices(PAYMENT_METHODS, weights=PAYMENT_WEIGHTS, k=rows)
    subtotals = [round(random.gammavariate(2.0, 2.0) * 50, 2) for _ in range(rows)]
    discount_pcts = [random.betavariate(2, 5) * 0.3 for _ in range(rows)]

    discount_amounts = []
    tax_amounts = []
    total_amounts = []
    items_counts = []
    for sub, disc_pct in zip(subtotals, discount_pcts):
        disc = round(sub * disc_pct, 2)
        disc = None if random.random() < 0.02 else disc
        disc_val = disc if disc is not None else 0
        tax = round((sub - disc_val) * 0.08, 2)
        total = round(sub - disc_val + tax, 2)
        discount_amounts.append(disc)
        tax_amounts.append(tax)
        total_amounts.append(total)
        items_counts.append(max(1, int(random.expovariate(0.2))))

    # subtotal is omitted (matches Spark generator's omit=True) — used only to derive other columns
    return pl.DataFrame({
        "txn_id": txn_ids,
        "customer_id": customer_ids,
        "store_id": store_ids,
        "txn_timestamp": txn_timestamps,
        "payment_method": payment_methods,
        "discount_amount": discount_amounts,
        "tax_amount": tax_amounts,
        "total_amount": total_amounts,
        "items_count": [min(c, 20) for c in items_counts],
    })


def generate_line_items(rows: int = 150_000, n_transactions: int = 50_000,
                        n_products: int = 5_000, seed: int = 42) -> pl.DataFrame:
    """Generate transaction line items linking transactions to products."""
    random.seed(seed)

    line_item_ids = list(range(1, rows + 1))
    txn_ids = [random.randint(1, n_transactions) for _ in range(rows)]
    product_ids = [random.randint(10_000, 10_000 + n_products - 1)
                   for _ in range(rows)]
    quantities = [max(1, min(10, int(random.expovariate(0.3)))) for _ in range(rows)]
    unit_prices = [round(random.uniform(5, 500), 2) for _ in range(rows)]

    df = pl.DataFrame({
        "line_item_id": line_item_ids,
        "txn_id": txn_ids,
        "product_id": product_ids,
        "quantity": quantities,
        "unit_price": unit_prices,
    })

    return df.with_columns(
        (pl.col("quantity") * pl.col("unit_price")).round(2).alias("line_total")
    )


def generate_inventory(rows: int = 50_000, n_products: int = 5_000,
                       seed: int = 42) -> pl.DataFrame:
    """Generate inventory levels by product and store location."""
    random.seed(seed)

    ts_start = datetime(2024, 1, 1)
    ts_range = int((datetime(2024, 12, 31, 23, 59, 59) - ts_start).total_seconds())

    inventory_ids = list(range(1, rows + 1))
    product_ids = [random.randint(10_000, 10_000 + n_products - 1)
                   for _ in range(rows)]
    store_ids = [random.randint(100, 150) for _ in range(rows)]
    qty_on_hand = [max(0, int(random.expovariate(0.01)))
                   for _ in range(rows)]
    reorder_points = [random.randint(10, 50) for _ in range(rows)]
    last_updated = [ts_start + timedelta(seconds=random.randint(0, ts_range))
                    for _ in range(rows)]

    return pl.DataFrame({
        "inventory_id": inventory_ids,
        "product_id": product_ids,
        "store_id": store_ids,
        "quantity_on_hand": [min(q, 500) for q in qty_on_hand],
        "reorder_point": reorder_points,
        "last_updated": last_updated,
    })
