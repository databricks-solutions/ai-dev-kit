# Part III: Software Architecture

Good architecture makes code easier to understand, test, and hand off. In FDE engagements, customers inherit everything we build — our architectural choices become their long-term maintenance burden.

## 6.1 Design Principles

### Prefer Simple Over Clever

```python
# Clever - hard to understand at a glance
result = {k: v for d in [a, b, c] for k, v in d.items() if v and k not in exclude}

# Simple - obviously correct
result = {}
for d in [a, b, c]:
    for k, v in d.items():
        if v and k not in exclude:
            result[k] = v
```

Write the boring version first. Optimize later if needed.

### Composition Over Inheritance

```python
# Inheritance - rigid
class BaseProcessor:
    def process(self): ...
class CustomerProcessor(BaseProcessor): ...
class PremiumCustomerProcessor(CustomerProcessor): ...  # Getting deep...

# Composition - flexible
def process_customer(customer, validators, transformers):
    for validator in validators:
        validator(customer)
    for transformer in transformers:
        customer = transformer(customer)
    return customer
```

### Fail Fast, Fail Loud

```python
# BAD - silent failure
def get_config(path):
    try:
        return load_yaml(path)
    except FileNotFoundError:
        return {}  # will cause confusing errors later

# GOOD
def get_config(path):
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    return load_yaml(path)
```

### Design for Change

Group things that change together by *domain*, not *technical layer*:

```
# BAD - customer logic scattered by layer
project/
├── validators/customer_validator.py
├── loaders/customer_loader.py
└── transformers/customer_transformer.py

# GOOD - related logic grouped by domain
project/
└── customers/
    └── processor.py  # validate, load, transform together
```

Isolate external dependencies behind interfaces; use configuration for values that might change.

### Single Source of Truth

Every piece of configuration should have one authoritative location. Duplication leads to inconsistency.

**Where configuration lives:**

| Value Type | Where to Define | Example |
|------------|----------------|---------|
| Environment-specific (catalog, schema) | DAB variables in `databricks.yml` | `catalog: ${var.catalog_name}` |
| Secrets (API keys, tokens) | Databricks Secrets | `dbutils.secrets.get("scope", "key")` |
| Application constants | Python module (`constants.py`) | `MAX_RETRIES = 3` |
| Complex/structured config | YAML files loaded via Pydantic | `configs/prod.yaml` |
| Runtime overrides | Notebook widgets with defaults from above | `dbutils.widgets.text(...)` |

**Recommended pattern:** DAB variables → injected as job parameters → widgets provide defaults for interactive use.

```yaml
# databricks.yml - source of truth
variables:
  catalog_name:
    default: dev_catalog
targets:
  prod:
    variables:
      catalog_name: prod_catalog
```

```python
# In notebook - widget with fallback
dbutils.widgets.text("catalog", "dev_catalog")
catalog = dbutils.widgets.get("catalog")  # job param overrides when run as job
```

**What NOT to do:** Hardcode environment-specific values, duplicate the same value in DAB variables AND config files, put secrets in config files, define defaults in multiple places.

### Build for Handoff

Prefer explicit over implicit. Code should be obvious to someone reading it for the first time.

```python
# IMPLICIT
def process(df):
    df = _clean(df)       # what does _clean do?
    df = _transform(df)   # transforms how?
    return df

# EXPLICIT
def process_customer_orders(df: DataFrame) -> DataFrame:
    df = remove_duplicate_orders(df)
    df = convert_timestamps_to_utc(df)
    return df
```

## 6.2 Project Structure

See also the [example repository](https://github.com/databricks-field-eng/reusable-ip-ai/tree/main/reusable_ip/projects/dabs/repo_template).

```
project-root/
│
├── pyproject.toml               # Project metadata & dependencies
├── uv.lock                      # Locked dependencies
├── requirements.txt             # For Databricks notebook imports
├── Makefile                     # Task runner (install, test, lint, etc.)
├── .pre-commit-config.yaml      # Pre-commit hooks
├── .gitignore
├── README.md
│
├── {project_name}/              # Python package (core logic)
│   ├── __init__.py
│   ├── config/
│   ├── pipelines/
│   ├── models/                  # ML models (if applicable)
│   ├── agents/                  # Agents (if applicable)
│   ├── tools/                   # Agent tools (if applicable)
│   └── utils/
│
├── tests/                       # Tests mirror source structure
│   ├── conftest.py
│   ├── unit/
│   └── integration/
│
├── configs/                     # Environment config files
│   ├── dev.yaml
│   ├── staging.yaml
│   └── prod.yaml
│
├── scripts/                     # Utility scripts
│   └── generate_requirements.py
│
├── notebooks/                   # Databricks notebooks (entrypoints only)
│   ├── 00_setup/
│   ├── 01_data/
│   ├── 02_development/
│   └── 03_deployment/
│
├── databricks.yml               # DAB configuration
├── resources/                   # DAB resource definitions
│   ├── jobs/
│   ├── pipelines/
│   └── apps/
│
└── .github/workflows/           # CI/CD pipelines
```

### Key Principle: Notebooks Are Entrypoints, Not Implementation

```python
# GOOD - notebook imports and calls
from project.pipelines import customer_pipeline
result = customer_pipeline.run(spark, config)

# BAD - notebook contains the implementation
def complex_transformation(df):  # 200 lines of logic in a notebook cell
    ...
```

| Concern | Notebooks | Python Modules |
|---------|-----------|---------------|
| **Testing** | Hard to unit test | Easy with pytest |
| **Code review** | Noisy diffs (cell metadata) | Clean, readable diffs |
| **Reuse** | Copy-paste | Import from anywhere |
| **IDE support** | Limited | Full support |

### Committing Notebooks to Git

Commit notebooks as Python source files (`.py`) rather than `.ipynb`. Databricks supports `.py` notebooks natively with `# COMMAND ----------` cell separators.

```
# GOOD - clean diffs
notebooks/run_pipeline.py

# AVOID - outputs bloat repo
notebooks/run_pipeline.ipynb
```

If you must use `.ipynb`, clear outputs before committing.

## 6.3 Code Organization

### Separation of Concerns

Organize by domain/feature for larger projects; by technical concern for smaller ones:

```python
# Larger projects - by domain
project/
├── customers/          # loader.py, transformer.py, validator.py
├── billing/            # api.py, calculator.py
├── agents/             # support_agent.py, tools/
└── common/             # config.py, logging.py

# Smaller projects - by technical concern
project/
├── data/           # Data access and transformation
├── models/         # ML model logic
├── api/            # External API integrations
└── utils/          # Shared utilities
```

### Functions vs Classes

Use **functions** for stateless transformations (data in → data out).
Use **classes** when you need state, shared context, or dependency injection for testing.

```python
# Good function - stateless
def clean_customer_data(df: DataFrame) -> DataFrame:
    return df.dropDuplicates(["customer_id"]).filter(col("status") == "active")

# Good class - stateful, injectable
class CustomerDataLoader:
    def __init__(self, spark: SparkSession, catalog: str):
        self.spark = spark
        self.catalog = catalog

    def load_customers(self, date: str) -> DataFrame:
        return self.spark.table(f"{self.catalog}.customers").filter(col("date") == date)
```

### Constants

```python
# constants.py
MAX_RETRIES = 3
BATCH_SIZE = 1000
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
VALID_STATUSES = {STATUS_ACTIVE, STATUS_INACTIVE}
```

Use for: magic numbers, repeated string literals, values that might change but shouldn't be scattered.
Don't use for: environment-specific values (use config), values used exactly once.

### Dependency Injection

Pass dependencies in rather than creating them internally — makes code testable and flexible.

```python
# GOOD - dependencies injected
def process_batch(spark: SparkSession, config: Config, logger: Logger):
    data = spark.table(config.source_table)
    ...

# BAD - hidden dependencies
def process_batch():
    spark = SparkSession.builder.getOrCreate()  # Hidden, hard to test
    config = load_config()                       # Where does this come from?
```

### Rule of Three

Don't abstract too early. Wait until you have three similar implementations before creating a shared abstraction.

## 6.4 Config Management

Externalize configuration to make code environment-agnostic. Never hardcode catalog names, endpoints, or environment-specific values.

**Loading configuration with Pydantic:**

```python
from pydantic_settings import BaseSettings
from pydantic import Field

class AppConfig(BaseSettings):
    catalog: str
    schema_name: str = Field(alias="schema")
    batch_size: int = 1000
    endpoint: str

    class Config:
        env_prefix = "APP_"  # Reads APP_CATALOG, APP_SCHEMA, etc.

config = AppConfig()
# Or load from file
config = AppConfig(_env_file="configs/dev.yaml")
```

**Key principles:**
- Never hardcode environment-specific values
- Use Databricks Secrets for credentials (not config files)
- Validate configuration at startup — fail fast if something's wrong
- Make the default environment safe (dev, not prod)

## 6.5 Resilience & Idempotency

### Retry with Exponential Backoff

```python
import backoff

@backoff.on_exception(
    backoff.expo,
    (RequestException, TimeoutError),
    max_tries=3,
    max_time=60
)
def call_external_api(endpoint: str, data: dict) -> dict:
    response = requests.post(endpoint, json=data, timeout=10)
    response.raise_for_status()
    return response.json()
```

| Retry | Don't Retry |
|-------|------------|
| Network timeouts | Invalid input (400) |
| Rate limits (429) | Auth failures (401, 403) |
| Server errors (5xx) | Not found (404) |

### Idempotency

Data pipelines should produce the same result when run multiple times.

```python
# BAD - append creates duplicates on re-run
df.write.mode("append").saveAsTable("catalog.schema.customers")

# GOOD - merge ensures idempotency
from delta.tables import DeltaTable
target = DeltaTable.forName(spark, "catalog.schema.customers")
target.alias("t").merge(
    source_df.alias("s"),
    "t.customer_id = s.customer_id"
).whenMatchedUpdateAll() \
 .whenNotMatchedInsertAll() \
 .execute()
```

### Error Boundaries

Catch errors at system boundaries — not deep inside business logic.

```python
# GOOD - let errors propagate, catch at the entry boundary
def handle_discount_request(customer_id):
    try:
        customer = get_customer(customer_id)
        loyalty_score = get_loyalty_score(customer)
        return calculate_discount(customer, loyalty_score)
    except LoyaltyServiceError:
        logger.warning(f"Loyalty service unavailable for {customer_id}")
        return calculate_discount(customer, loyalty_score=1.0)
```

## 6.6 API & Interface Design

```python
# Self-documenting interface
def search_documents(
    query: str,
    filters: dict[str, Any] | None = None,
    limit: int = 10,
    include_metadata: bool = False
) -> list[Document]:
    """Search documents matching the query.

    Args:
        query: Natural language search query
        filters: Optional field filters (e.g., {"category": "billing"})
        limit: Maximum results to return (default 10, max 100)

    Returns:
        List of matching documents, ordered by relevance

    Raises:
        ValueError: If query is empty or limit > 100
    """
```

**Principles:** Required params first, sensible defaults, consistent return types, fail explicitly (raise ValueError, not return None).

### Data Classes for Complex Returns

```python
from dataclasses import dataclass

# BAD - what does result[0] mean?
def process_batch(df) -> tuple[DataFrame, int, list[str]]: ...

# GOOD
@dataclass
class BatchResult:
    processed_df: DataFrame
    error_count: int
    error_ids: list[str]

def process_batch(df) -> BatchResult: ...
result = process_batch(df)
print(f"Errors: {result.error_count}")
```

## 6.7 Data Contracts & Schemas

### Pydantic for Validation

```python
from pydantic import BaseModel, Field, field_validator

class CustomerRecord(BaseModel):
    customer_id: str
    email: str
    status: str = Field(pattern="^(active|inactive|churned)$")
    balance: float = Field(ge=0)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email format")
        return v.lower()
```

### Delta Table Schemas

```python
from pyspark.sql.types import StructType, StructField, StringType, DoubleType

CUSTOMER_SCHEMA = StructType([
    StructField("customer_id", StringType(), nullable=False),
    StructField("email", StringType(), nullable=False),
    StructField("status", StringType(), nullable=False),
    StructField("balance", DoubleType(), nullable=False),
])

df = spark.read.schema(CUSTOMER_SCHEMA).json(source_path)
df.write.option("mergeSchema", "false").saveAsTable("catalog.schema.customers")
```

## 6.8 Versioning & Rollback

Use semantic versioning (MAJOR.MINOR.PATCH):

```bash
git tag -a v1.2.0 -m "v1.2.0: Add billing features"
git push origin v1.2.0
```

### Rolling Back Code and Infrastructure

```bash
# 1. Check out previous release tag
git checkout v1.1.0

# 2. Redeploy to prod
databricks bundle deploy -t prod
```

**Recommended approach:** Configure CI/CD to deploy to prod on release tag. To roll back, create a new release tag pointing to the previous known-good commit.

### Rolling Back Models and Data

| Asset | How to Rollback |
|-------|----------------|
| **Registered models** | `client.set_registered_model_alias(name, "production", previous_version)` |
| **Delta tables** | `spark.read.option("versionAsOf", 5).table(...)` or `RESTORE TABLE t TO VERSION AS OF 5` |

## 6.9 Documenting Architecture Decisions

Document significant decisions so future maintainers understand why things are the way they are.

**When to document:** Choosing between valid approaches, non-obvious trade-offs, decisions that would be expensive to reverse.

| Scope | Template | When to Use |
|-------|----------|------------|
| Overall system | Design Doc | New systems, major features, significant architecture changes |
| Focused decision | Decision Doc | Choosing between options for a specific component |

Keep all documentation in the project's Google Drive folder (owned by the TPM). Link from the Reference Doc.

## 6.10 System Design

### When to Design Upfront

| Task Type | Design Approach |
|-----------|----------------|
| Bug fix, small feature | Jump in, no formal design |
| New component or service | Sketch on LucidChart, then build |
| New system, major feature | Write a Design Doc, get sign-off before building |
| Cross-team or customer-facing | Design Doc required |

### Start with Requirements

- **Functional:** What should the system do?
- **Non-functional:** What qualities must it have? (latency, uptime, concurrency)
- **Constraints:** What are you working within? (timeline, existing infrastructure)

Distinguish **MUST** (blocking), **SHOULD** (expected), **COULD** (stretch).

### Consider Failure Modes

| Component | Failure Mode | Mitigation |
|-----------|-------------|-----------|
| External API | Timeout, rate limit | Retry with backoff, circuit breaker |
| Vector search | Index unavailable | Graceful degradation, cached results |
| LLM endpoint | High latency, errors | Timeout, fallback model |
| Data pipeline | Bad input data | Validation, quarantine bad records, alerts |

Design for predicted failures. Prioritize operational simplicity — complex failover mechanisms are hard to hand off.

### Make Trade-offs Explicit

| Trade-off | We Chose | Because | Implication |
|-----------|---------|---------|------------|
| Latency vs Cost | Higher latency | Serverless reduces ops burden | P95 ~800ms, not ~200ms |
| Flexibility vs Simplicity | Simpler design | 8-week timeline, handoff to customer | Adding new data sources requires significant refactor |
