# Domain-Specific Guidance

Realistic patterns for common data domains. All examples use Spark + Faker + Pandas UDFs.

---

## Retail/E-commerce

### Tables
```
customers → orders → order_items → products
```

### Key Patterns

| Pattern | Implementation |
|---------|----------------|
| Seasonal spikes | Q4 holiday shopping (1.5-2x volume in Nov-Dec) |
| Cart abandonment | ~70% of carts never complete |
| Loyalty tier progression | Free → Pro → Enterprise over time |
| Regional pricing | 5-15% price variation by region |

### Realistic Distributions

```python
@F.pandas_udf(DoubleType())
def generate_order_amount(tiers: pd.Series) -> pd.Series:
    """E-commerce order amounts by tier."""
    amounts = []
    for tier in tiers:
        if tier == "Premium":
            amounts.append(float(np.random.lognormal(mean=5.5, sigma=0.9)))  # ~$245 avg
        elif tier == "Standard":
            amounts.append(float(np.random.lognormal(mean=4.2, sigma=0.7)))  # ~$67 avg
        else:  # Basic
            amounts.append(float(np.random.lognormal(mean=3.5, sigma=0.6)))  # ~$33 avg
    return pd.Series(amounts)

# Order status with cart abandonment
status_weights = [0.70, 0.08, 0.07, 0.10, 0.05]  # abandoned, pending, processing, shipped, delivered
```

### Schema Example

```python
# Products
products_df = spark.range(0, N_PRODUCTS).select(
    F.concat(F.lit("PROD-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("product_id"),
    fake_product_name(F.col("id")).alias("name"),
    F.array(F.lit("Electronics"), F.lit("Clothing"), F.lit("Home"), F.lit("Sports"))[
        (F.rand() * 4).cast("int")
    ].alias("category"),
    generate_price(F.col("id")).alias("base_price"),
)
```

---

## Support/CRM

### Tables
```
accounts → contacts → tickets → interactions
```

### Key Patterns

| Pattern | Implementation |
|---------|----------------|
| Incident spikes | 3-5x volume during outages |
| Resolution by priority | Critical: 4h avg, Low: 72h avg |
| Enterprise contacts | 5-10 contacts per account vs 1-2 for SMB |
| CSAT correlation | Faster resolution = higher satisfaction |

### Realistic Distributions

```python
@F.pandas_udf("struct<priority:string,resolution_hours:double,csat:int>")
def generate_ticket_metrics(tiers: pd.Series) -> pd.DataFrame:
    """Support ticket metrics with correlated attributes."""
    results = []
    for tier in tiers:
        # Priority correlates with tier
        if tier == 'Enterprise':
            priority = np.random.choice(['Critical', 'High', 'Medium'], p=[0.3, 0.5, 0.2])
        else:
            priority = np.random.choice(['Critical', 'High', 'Medium', 'Low'], p=[0.05, 0.2, 0.45, 0.3])

        # Resolution time by priority (exponential distribution)
        resolution_scale = {'Critical': 4, 'High': 12, 'Medium': 36, 'Low': 72}
        resolution_hours = np.random.exponential(scale=resolution_scale[priority])

        # CSAT correlates with resolution time
        if resolution_hours < 4:
            csat = np.random.choice([4, 5], p=[0.3, 0.7])
        elif resolution_hours < 24:
            csat = np.random.choice([3, 4, 5], p=[0.2, 0.5, 0.3])
        else:
            csat = np.random.choice([1, 2, 3, 4], p=[0.1, 0.3, 0.4, 0.2])

        results.append({"priority": priority, "resolution_hours": round(resolution_hours, 1), "csat": int(csat)})
    return pd.DataFrame(results)
```

### Schema Example

```python
# Tickets with coherent attributes
tickets_df = (
    spark.range(0, N_TICKETS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("TKT-"), F.lpad(F.col("id").cast("string"), 6, "0")).alias("ticket_id"),
        # FK to customer (weighted by tier)
        ...
    )
    .withColumn("metrics", generate_ticket_metrics(F.col("tier")))
    .select("*", "metrics.*")
    .drop("metrics")
)
```

---

## Manufacturing/IoT

### Tables
```
equipment → sensors → readings → maintenance_orders
```

### Key Patterns

| Pattern | Implementation |
|---------|----------------|
| Sensor lifecycle | Normal → degraded → failure progression |
| Anomaly precursors | Anomalies precede maintenance by 2-7 days |
| Seasonal production | Summer/winter production variations |
| Equipment age | Failure rate increases with age |

### Realistic Distributions

```python
@F.pandas_udf(DoubleType())
def generate_sensor_reading(equipment_ages: pd.Series) -> pd.Series:
    """Sensor readings with age-based degradation."""
    readings = []
    for age_days in equipment_ages:
        # Base reading with age-based drift
        base = 100.0
        drift = (age_days / 365) * 5  # 5 units drift per year
        noise = np.random.normal(0, 2)

        # Occasional anomalies (more likely with age)
        anomaly_prob = min(0.01 + (age_days / 365) * 0.02, 0.1)
        if np.random.random() < anomaly_prob:
            noise += np.random.choice([-1, 1]) * np.random.exponential(10)

        readings.append(base + drift + noise)
    return pd.Series(readings)
```

### Schema Example

```python
# Sensor readings time series
readings_df = (
    spark.range(0, N_READINGS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("READ-"), F.col("id").cast("string")).alias("reading_id"),
        # FK to sensor
        ((F.col("id") % N_SENSORS) + 1).alias("sensor_id"),
        F.date_add(F.lit(START_DATE.date()), (F.col("id") / READINGS_PER_DAY).cast("int")).alias("timestamp"),
        generate_sensor_reading(F.col("equipment_age")).alias("value"),
    )
)
```

---

## Financial Services

### Tables
```
accounts → transactions → payments → fraud_flags
```

### Key Patterns

| Pattern | Implementation |
|---------|----------------|
| Transaction power law | 80% of volume from 20% of accounts |
| Fraud patterns | Unusual times, amounts, locations |
| Balance consistency | Transactions maintain positive balance |
| Regulatory compliance | No negative balances, valid amounts |

### Realistic Distributions

```python
@F.pandas_udf(DoubleType())
def generate_transaction_amount(account_types: pd.Series) -> pd.Series:
    """Transaction amounts following power law by account type."""
    amounts = []
    for acct_type in account_types:
        if acct_type == "Corporate":
            # Power law for corporate (few large transactions)
            amount = (np.random.pareto(a=1.5) + 1) * 1000
        elif acct_type == "Premium":
            amount = np.random.lognormal(mean=6, sigma=1.2)
        else:  # Standard
            amount = np.random.lognormal(mean=4, sigma=0.8)
        amounts.append(min(amount, 1_000_000))  # Cap at $1M
    return pd.Series(amounts)

@F.pandas_udf(BooleanType())
def generate_fraud_flag(amounts: pd.Series, hours: pd.Series) -> pd.Series:
    """Flag suspicious transactions based on amount and time."""
    flags = []
    for amount, hour in zip(amounts, hours):
        # Higher fraud probability for: large amounts + unusual hours
        base_prob = 0.001
        if amount > 5000:
            base_prob *= 3
        if hour < 6 or hour > 22:
            base_prob *= 2
        flags.append(np.random.random() < base_prob)
    return pd.Series(flags)
```

### Schema Example

```python
# Transactions with fraud indicators
transactions_df = (
    spark.range(0, N_TRANSACTIONS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("TXN-"), F.lpad(F.col("id").cast("string"), 10, "0")).alias("transaction_id"),
        # FK to account
        ...
        generate_transaction_amount(F.col("account_type")).alias("amount"),
        F.hour(F.col("timestamp")).alias("hour"),
    )
    .withColumn("is_suspicious", generate_fraud_flag(F.col("amount"), F.col("hour")))
)
```

---

## General Best Practices

1. **Start with domain tables**: Define the core entities and relationships first
2. **Add domain-specific distributions**: Use realistic statistical patterns for your domain
3. **Include edge cases**: Every domain has edge cases (returns, cancellations, failures)
4. **Time-based patterns matter**: Most domains have daily/weekly/seasonal patterns
5. **Correlate attributes**: Attributes within a row should make business sense together

**Note:** These are guidance patterns, not rigid schemas. Adapt to user's specific requirements.
