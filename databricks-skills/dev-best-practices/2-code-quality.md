# Part II: Code Quality Standards

Code quality isn't about perfection — it's about writing code that's easy to understand, maintain, and hand off. Customers inherit our code — every shortcut becomes their technical debt.

If a customer has existing style guides, adopt theirs. Consistency with their codebase matters more than our preferences.

## 4.1 Python Standards

### PEP 8 Compliance (enforced via Ruff)

- Maximum line length: 88 characters (Ruff default)
- 4 spaces for indentation (no tabs)
- Two blank lines between top-level definitions

**`pyproject.toml` Ruff config:**

```toml
[tool.ruff]
line-length = 88
indent-width = 4

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "UP",  # pyupgrade
]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### Import Organization

```python
# 1. Standard library
import json
from pathlib import Path

# 2. Third-party packages
import mlflow
from pydantic import BaseModel

# 3. Local modules
from project.config import settings
from project.utils import helpers
```

Ruff handles this automatically with `ruff check --fix`.

### Type Hints

Use type hints for function signatures — they serve as documentation and catch bugs early.

```python
# Good
def process_customer(
    customer_id: str,
    options: dict[str, Any] | None = None
) -> CustomerResult:
    ...

def get_customers(ids: list[str]) -> dict[str, Customer]:
    ...
```

**When to use:**
- Always: function parameters and return types
- Usually: class attributes
- Optional: local variables (only if it aids clarity)

Don't over-annotate obvious code.

## 4.2 Documentation

### Docstrings

Use [Google-style docstrings](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html) for public functions and classes.

```python
def search_documents(query: str, limit: int = 10) -> list[Document]:
    """Search documents matching the query.

    Args:
        query: Natural language search query
        limit: Maximum results to return

    Returns:
        List of matching documents ordered by relevance

    Raises:
        ValueError: If query is empty
        SearchError: If search backend unavailable
    """
```

**When to write docstrings:**
- Public functions and classes: always
- Private helpers (`_function`): only if complex
- Obvious one-liners: skip it

### Inline Comments

Comments should explain *why*, not *what*. The code shows what's happening.

```python
# Bad - describes what the code does (obvious)
# Loop through customers and check status
for customer in customers:
    if customer.status == "active":
        ...

# Good - explains why
# Filter to active customers only — churned customers
# have incomplete data that breaks downstream processing
for customer in customers:
    if customer.status == "active":
        ...
```

> **NOTE:** AI-generated code tends to be overly liberal with inline comments — avoid this.

## 4.3 Naming Conventions

| Resource | Convention | Example |
|----------|-----------|---------|
| Functions | snake_case | `get_customer_data` |
| Classes | PascalCase | `CustomerAgent` |
| Constants | UPPER_SNAKE | `MAX_RETRIES` |
| Private | leading underscore | `_internal_helper` |
| UC resources | snake_case | `dev_sales.customers` |
| Model endpoints | kebab-case | `customer-support-agent` |
| DAB jobs | snake_case | `deploy_agent_model` |
| Git branches | username/description | `niall/add-billing-tool` |

**Tips:**
- Functions: use verbs (`get_`, `process_`, `validate_`)
- Booleans: use `is_`, `has_`, `can_` prefixes
- Collections: use plurals (`customers`, `order_items`)
- Avoid abbreviations unless universally understood (`id`, `url` are fine; `cust`, `proc` are not)

## 4.4 Error Handling

### Be Explicit — catch specific exceptions

```python
# BAD - catches everything, hides bugs
try:
    result = process_data(data)
except:
    return None

# GOOD - specific exceptions
try:
    result = process_data(data)
except ValidationError as e:
    logger.warning(f"Invalid data: {e}")
    return None
except ConnectionError:
    raise  # Let infrastructure errors bubble up
```

### Custom Exceptions for domain-specific errors

```python
class DataPipelineError(Exception):
    """Base for pipeline errors."""

class ValidationError(DataPipelineError):
    """Data validation failed."""

class TransformationError(DataPipelineError):
    """Data transformation failed."""
```

### Helpful Error Messages — include context

```python
# BAD
raise ValueError("Invalid input")

# GOOD
raise ValueError(
    f"Customer ID '{customer_id}' not found in database. "
    f"Verify the ID exists in the customers table."
)
```

**Rule:** Catch expected failures you can handle (validation, network timeouts). Let unexpected errors bubble up.

## 4.5 Code Simplicity

**Avoid over-engineering.** Write the simplest code that solves the problem.

```python
# Over-engineered
class CustomerProcessorFactory:
    def create_processor(self, type: str) -> BaseProcessor: ...

# Simple
def process_customer(customer: Customer) -> Result: ...
```

**Signs you're over-engineering:**
- Building "frameworks" instead of solving the problem
- Adding configuration for things that won't change
- Creating abstractions with only one implementation
- Premature optimization

> **Watch out for AI-generated code!** LLMs often over-engineer — excessive try/except, unnecessary fallbacks, verbose abstractions. They may also use outdated Databricks patterns. Always review and simplify.

**Refactor when:** you're touching the code anyway and it's hard to understand, the same bug keeps appearing, you need to add a feature and the current structure makes it hard.

**Don't refactor:** code you're not actively working on, just because you'd write it differently, without tests to verify behavior is preserved.

## 4.6 Logging

### Use structured logging

```python
import logging

logger = logging.getLogger(__name__)

# Good - structured, searchable
logger.info(
    "Processing customer batch",
    extra={"batch_size": len(customers), "customer_ids": customer_ids[:5]}
)

# Bad - unstructured, hard to parse
logger.info(f"Processing {len(customers)} customers: {customer_ids}")
```

### Log levels

| Level | Use When |
|-------|---------|
| `DEBUG` | Detailed diagnostic info (disabled in prod) |
| `INFO` | Normal operations worth recording |
| `WARNING` | Something unexpected but handled |
| `ERROR` | Something failed, needs attention |

**What to log:** Request/response boundaries, decisions made, external calls, errors with context.

**What NOT to log:** Sensitive data (PII, credentials), high-frequency loops, redundant info already in stack traces.

### Databricks logging setup

```python
import logging

def setup_logging():
    """Set up logging and suppress noisy py4j messages."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logging.getLogger("py4j").setLevel(logging.CRITICAL)

def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name (typically __name__)."""
    return logging.getLogger(name)
```

## 4.7 Testing

### 4.7.1 Testing Philosophy

#### Core Principles

**1. Shift Left (Fast Feedback Loops)**

- **Unit Tests:** Catch logic errors quickly in a lightweight environment (laptop, GitHub Actions)
- **Integration Tests:** Catch configuration, scale, and environment errors before production

**2. How to test code, data, and models**

- **Code:** Unit and integration tests that simulate production conditions
- **Data:** Monitoring/validation at runtime; test transformation logic and guard against invalid values
- **Models:** Focus on inference behavior — output structure, value constraints, accuracy metrics against static datasets
- **Agents:** Hybrid approach — deterministic plumbing (unit testable) + stochastic LLM behavior (eval only)

**3. Tests as Living Documentation**

Update tests *in the same commit* as code changes. A PR is incomplete if it changes logic without updating the corresponding test.

**4. Confidence over Coverage**

Don't chase 100% coverage. Focus on complexity and risk.
- **Test:** Complex business rules, regex parsing, mathematical calculations
- **Skip:** Trivial getters/setters, standard Spark API calls, boilerplate

#### "Do I Have Enough Tests?" Heuristics

**The "Friday Deploy" Test**
*If you had to deploy at 4:00 PM on a Friday and leave for the weekend, would you trust your test suite?* If "No, I'd need to manually check X" — you're missing a test for X.

**The "New Hire" Test**
*If a new team member accidentally deletes a critical line of business logic, will a test fail immediately?* If "Maybe not" — your tests are too shallow.

**The Critical Path Coverage Rule**
*Have I tested: Happy Path + 1 Edge Case + 1 Error State?*
- Happy Path: Logic works with perfect data
- Edge Case: Empty lists, null values, zero divisors
- Error State: Correct error message on invalid input

### 4.7.2 Unit Testing

**What to test:**
- Business transformation logic (expected, edge, error states)
- Model wrapper logic (pre/post-processing) — mock the ML framework
- API contracts and interfaces

**What NOT to test:**
- Production data distribution (that's data quality, not unit tests)
- Trivial Spark operations vendor-verified to work
- Loading heavy model artifacts

**Best practices:**
- Write tests against pure Python functions — avoid `SparkSession` dependency
- Use `unittest.mock` to simulate APIs and ML frameworks
- Use fixtures to share in-memory objects across tests

**Testing AI Agents — distinguish deterministic plumbing from probabilistic brain:**

| Component | Test Type | Strategy |
|-----------|-----------|---------|
| **Tools** (Functions) | Unit Test | Test as standard Python functions |
| **Orchestration** (Logic) | Unit Test | Mock the LLM; verify agent executes correct tool |
| **Prompt Engineering** | Unit Test | Test string formatting and template injection |
| **LLM Response** | Eval (Not Test) | Model quality — use LLM eval tools, not pytest |

```python
import pytest
from project.transformations import calculate_customer_score

def test_returns_score_for_valid_customer():
    customer = {"id": "123", "purchase_count": 10, "tenure_months": 24}
    score = calculate_customer_score(customer)
    assert 0 <= score <= 100

def test_raises_for_missing_required_fields():
    customer = {"id": "123"}  # missing fields
    with pytest.raises(ValueError, match="Missing required field"):
        calculate_customer_score(customer)

def test_handles_zero_purchases():
    customer = {"id": "123", "purchase_count": 0, "tenure_months": 12}
    assert calculate_customer_score(customer) == 0
```

```python
# Mocking external dependencies
from unittest.mock import Mock, patch

def test_api_call_retries_on_failure():
    mock_response = Mock()
    mock_response.json.return_value = {"status": "success"}

    with patch("project.api.requests.post", return_value=mock_response) as mock_post:
        result = call_external_api("https://api.example.com", {"data": "test"})

    assert result["status"] == "success"
    mock_post.assert_called_once()

# Agent orchestration test — mock the LLM, test the wiring
def test_agent_executes_refund_tool_when_instructed():
    mock_llm_response = Mock()
    mock_llm_response.tool_calls = [{"name": "refund_tool", "args": {"id": "123"}}]

    with patch("project.agent.llm_client.chat", return_value=mock_llm_response):
        agent = Agent()
        result = agent.run("I want a refund")

    assert result["status"] == "refund_processed"
```

### 4.7.3 Integration Testing

**What to test:**
- Pipeline execution end-to-end (exit code 0)
- Component handoffs: data written by Step A is correctly readable by Step B
- Environment interaction: access to Catalogs, Schemas, Secrets, Volumes
- Side effects: tables created/updated, files written to expected locations

**What NOT to test:**
- Exhaustive logic permutations (belongs in unit tests)
- Full data volume — use small representative samples
- Spark engine correctness

**Best practices:**
- **Isolation:** Use `integration_tests` catalog/schema — never write to production during tests
- **Idempotency:** Tests must be re-runnable with setup and teardown
- **Synthetic data:** Create small, static DataFrames — don't read from "live" tables
- **Service Principals:** Never run automated integration tests as a user

**File structure:**

```
notebooks/
└── integration_tests/
    ├── test_customer_pipeline.py
    └── test_agent_responses.py
```

**Example integration test notebook:**

```python
# Databricks notebook source
# COMMAND ----------
# Setup
test_catalog = "dev_catalog"
test_schema = "integration_tests"

test_data = spark.createDataFrame([
    {"customer_id": "1", "name": "Alice", "status": "active"},
    {"customer_id": "2", "name": "Bob", "status": "inactive"},
])
test_data.write.mode("overwrite").saveAsTable(f"{test_catalog}.{test_schema}.test_customers")

# COMMAND ----------
from project.pipelines import customer_pipeline
customer_pipeline.run(spark, test_catalog, test_schema)

# COMMAND ----------
# Verify outputs
result = spark.table(f"{test_catalog}.{test_schema}.customer_summary")
assert result.count() == 2, f"Expected 2 rows, got {result.count()}"
assert result.filter("status = 'active'").count() == 1

# COMMAND ----------
# Teardown
spark.sql(f"DROP TABLE IF EXISTS {test_catalog}.{test_schema}.test_customers")
spark.sql(f"DROP TABLE IF EXISTS {test_catalog}.{test_schema}.customer_summary")
print("All integration tests passed")
```

**Running tests:**

```bash
# unit tests (local, fast)
uv run pytest tests/unit/ -v

# integration tests (via DAB in staging)
databricks bundle deploy -t staging
databricks bundle run integration_tests -t staging
databricks bundle destroy  # clean up test resources
```

**Define integration test job in DAB:**

```yaml
# resources/tests/integration_tests.yml
resources:
  jobs:
    integration_tests:
      name: "Integration Tests"
      tasks:
        - task_key: test_customer_pipeline
          notebook_task:
            notebook_path: ./notebooks/integration-tests/test_customer_pipeline.py
```
