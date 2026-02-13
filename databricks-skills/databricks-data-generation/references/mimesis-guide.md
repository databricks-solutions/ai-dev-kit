# Mimesis Guide

Mimesis integration for generating realistic PII in dbldatagen via `mimesisText()`.

> **Connect compatibility:** `mimesisText()` uses `PyfuncTextFactory` which creates pandas UDFs internally. This does **NOT** work over Databricks Connect + serverless — the remote workers don't have mimesis installed. For PII columns via Connect, use `values=["James","Mary",...], random=True` instead. The full mimesisText() API below works in **Databricks notebooks** where mimesis is installed on the cluster.

## Why Mimesis over Faker

| Dimension | Faker | Mimesis |
|-----------|-------|---------|
| **Speed** | Baseline | ~4x faster (benchmarked) |
| **Typing** | Untyped / dynamic | Fully type-annotated |
| **API surface** | Flat namespace, hundreds of top-level methods | `Generic` class unifies all providers under clear sub-objects |
| **Method resolution** | Dynamic monkey-patching, fragile introspection | Static attributes, no monkey-patching or dynamic method resolution |

## Installation

```bash
uv pip install dbldatagen mimesis
```

## Basic Usage with dbldatagen

`mimesisText()` is the primary convenience function for using Mimesis with dbldatagen.
It accepts a dot-delimited provider path (e.g. `"person.first_name"`) and resolves it
against a `mimesis.Generic` instance distributed across Spark workers with no UDFs needed.

```python
import dbldatagen as dg
from utils.mimesis_text import mimesisText

spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=100_000)
    .withColumn("first_name", "string", text=mimesisText("person.first_name"))
    .withColumn("last_name", "string", text=mimesisText("person.last_name"))
    .withColumn("email", "string", text=mimesisText("person.email"))
    .withColumn("phone", "string", text=mimesisText("person.telephone"))
    .withColumn("address", "string", text=mimesisText("address.address"))
    .withColumn("city", "string", text=mimesisText("address.city"))
    .build()
)
```

The string passed to `mimesisText()` follows the pattern `"<provider>.<method>"`, where
the provider name maps to an attribute on `mimesis.Generic` and the method is called with
no arguments.

## Provider Mapping

### Person

| mimesisText call | Example output |
|-----------------|----------------|
| `mimesisText("person.first_name")` | Jennifer |
| `mimesisText("person.last_name")` | Williams |
| `mimesisText("person.full_name")` | Dr. Michael Johnson |
| `mimesisText("person.email")` | user@example.com |
| `mimesisText("person.telephone")` | +1-555-123-4567 |
| `mimesisText("person.username")` | john_smith42 |

### Address

| mimesisText call | Example output |
|-----------------|----------------|
| `mimesisText("address.address")` | 123 Main Street |
| `mimesisText("address.city")` | Los Angeles |
| `mimesisText("address.state")` | California |
| `mimesisText("address.zip_code")` | 90210 |
| `mimesisText("address.country")` | United States |

### Finance

| mimesisText call | Example output |
|-----------------|----------------|
| `mimesisText("finance.company")` | Acme Corp |
| `mimesisText("finance.currency_iso_code")` | USD |

### Datetime

| mimesisText call | Example output |
|-----------------|----------------|
| `mimesisText("datetime.date")` | 2024-03-14 |
| `mimesisText("datetime.time")` | 14:30:00 |

### Text

| mimesisText call | Example output |
|-----------------|----------------|
| `mimesisText("text.sentence")` | A single sentence |
| `mimesisText("text.text")` | A paragraph of text |
| `mimesisText("text.word")` | A single word |

### Internet

| mimesisText call | Example output |
|-----------------|----------------|
| `mimesisText("internet.url")` | https://example.com |
| `mimesisText("internet.ip_v4")` | 192.168.1.1 |
| `mimesisText("internet.mac_address")` | 00:1A:2B:3C:4D:5E |

## Locale Support

Use `PyfuncTextFactory` to create a locale-specific Mimesis factory. The init function
runs once per Spark worker and attaches a `Generic` instance configured with the desired locale.

```python
from dbldatagen import PyfuncTextFactory
import dbldatagen as dg

def init_french(ctx):
    from mimesis import Generic
    from mimesis.locales import Locale
    ctx.mimesis = Generic(locale=Locale.FR)

FrenchText = (
    PyfuncTextFactory(name="FrenchText")
    .withInit(init_french)
    .withRootProperty("mimesis")
)

spec = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("name", "string", text=FrenchText(lambda g: g.person.full_name()))
    .withColumn("city", "string", text=FrenchText(lambda g: g.address.city()))
    .build()
)
```

## Advanced Patterns - Lambda Escape Hatch

For complex generation logic that goes beyond a single provider method, pass a lambda
directly to `MimesisText`. The lambda receives the `Generic` instance and can combine
multiple providers, apply formatting, or add conditional logic.

```python
from utils.mimesis_text import MimesisText
import dbldatagen as dg

# Direct lambda for complex logic
spec = (
    dg.DataGenerator(spark, rows=50_000, partitions=8)
    .withColumn("display_name", "string",
                text=MimesisText(lambda g: f"{g.person.first_name()} {g.person.last_name()[0]}."))
    .build()
)
```

## PyfuncTextFactory Deep-Dive

`PyfuncTextFactory` is the underlying dbldatagen mechanism that powers both `mimesisText()`
and custom text factories. It follows an init / rootProperty / call pattern:

1. **`withInit(fn)`** - Registers an initialization function that runs once per Spark
   worker partition. The function receives a context object and should attach any
   expensive-to-create resources (e.g. a `Generic` instance) as attributes on that context.

2. **`withRootProperty(name)`** - Tells the factory which attribute on the context object
   to pass into the generation callable. This becomes the first argument to every lambda
   or provider-path call.

3. **Calling the factory** - When invoked with a lambda or string, the factory returns a
   text specification that dbldatagen uses in `withColumn(..., text=...)`. At generation
   time, each row calls the lambda with the root property object.

```python
from dbldatagen import PyfuncTextFactory

def init_mimesis(ctx):
    from mimesis import Generic
    from mimesis.locales import Locale
    ctx.gen = Generic(locale=Locale.EN)

MyFactory = (
    PyfuncTextFactory(name="MyFactory")
    .withInit(init_mimesis)
    .withRootProperty("gen")
)

# Use with a lambda
spec.withColumn("email", "string", text=MyFactory(lambda g: g.person.email()))
```

## When to Use Standalone Mimesis

Use standalone Mimesis (without dbldatagen or Spark) for **Tier 1 local generation** — datasets under ~100K rows built with Polars + Mimesis. For Spark-based generation (Tier 2/3), use `mimesisText()` in notebooks or `values=` lists via Connect.

### Seeded Generic Instance Pattern

Always create a seeded `Generic` instance for reproducible output. Set both `random.seed()` (for Python stdlib) and `Generic(seed=)` (for Mimesis) at the top of each function:

```python
import random
from mimesis import Generic
from mimesis.locales import Locale

random.seed(42)
g = Generic(locale=Locale.EN, seed=42)

# Generate PII columns via list comprehensions
first_names = [g.person.first_name() for _ in range(10_000)]
emails = [g.person.email() for _ in range(10_000)]
cities = [g.address.city() for _ in range(10_000)]
```

### Performance Notes

- `Generic` instantiation is fast (~1ms)
- Each provider call (e.g., `g.person.email()`) takes ~10us
- For 10K rows: ~100ms for PII columns; for 100K rows: ~1-3 seconds
- Beyond ~100K rows, switch to Tier 2 (Spark + dbldatagen via Connect)

### Cross-Reference

For complete Tier 1 patterns including distributions, nulls, FKs, and Polars expressions, see [polars-generation-guide.md](polars-generation-guide.md). For the full mapping of `mimesisText()` calls to standalone Mimesis calls, see the "Mimesis Provider Quick Reference" table in that guide.

## Resources

- [Mimesis Documentation](https://mimesis.name/)
- [Mimesis GitHub](https://github.com/lk-geimfari/mimesis)
- [dbldatagen PyfuncTextFactory](https://databrickslabs.github.io/dbldatagen/public_docs/text_data_generation.html)
