---
name: skill-test
description: Testing framework for evaluating Databricks skills. Use when building test cases for skills, running skill evaluations, comparing skill versions, or creating ground truth datasets with the Generate-Review-Promote (GRP) pipeline. Triggers include "test skill", "evaluate skill", "skill regression", "ground truth", "GRP pipeline", "skill quality", and "skill metrics".
---

# Databricks Skills Testing Framework

Offline YAML-first evaluation with human-in-the-loop review and interactive skill improvement.

## Quick Start

```python
# Evaluate a skill
from src.runners import evaluate_skill
results = evaluate_skill("spark-declarative-pipelines")

# Evaluate routing
from src.runners import evaluate_routing
results = evaluate_routing()

# Generate test case candidate
from src.grp import generate_candidate, save_candidates
candidate = generate_candidate("spark-declarative-pipelines", prompt, response)
save_candidates([candidate], Path("skills/spark-declarative-pipelines/candidates.yaml"))
```

## Workflows

### Skill Evaluation

```python
from src.runners import evaluate_skill
results = evaluate_skill("spark-declarative-pipelines")
# Loads skills/{skill}/ground_truth.yaml, runs scorers, reports to MLflow
```

### Routing Evaluation

```python
from src.runners import evaluate_routing
results = evaluate_routing()
# Tests skill trigger detection from skills/_routing/ground_truth.yaml
```

### Generate-Review-Promote Pipeline

```python
from src.grp import generate_candidate, save_candidates, promote_approved
from src.grp.reviewer import review_candidates_file
from pathlib import Path

# 1. Generate candidate from skill output
candidate = generate_candidate("spark-declarative-pipelines", prompt, response)

# 2. Save for review
save_candidates([candidate], Path("skills/spark-declarative-pipelines/candidates.yaml"))

# 3. Interactive review
review_candidates_file(Path("skills/spark-declarative-pipelines/candidates.yaml"))

# 4. Promote approved to ground truth
promote_approved(
    Path("skills/spark-declarative-pipelines/candidates.yaml"),
    Path("skills/spark-declarative-pipelines/ground_truth.yaml")
)
```

### Version Comparison

```python
from src.runners import evaluate_skill
from src.runners.compare import compare_baselines, save_baseline

results = evaluate_skill("spark-declarative-pipelines")
comparison = compare_baselines("spark-declarative-pipelines", results["metrics"])

if comparison.passed_gates:
    save_baseline("spark-declarative-pipelines", results["run_id"],
                  results["metrics"], results["test_count"])
```

## Quality Gates

| Metric | Threshold |
|--------|-----------|
| syntax_valid/mean | 100% |
| pattern_adherence/mean | 90% |
| no_hallucinated_apis/mean | 100% |
| execution_success/mean | 80% |
| routing_accuracy/mean | 90% |

## Test Case Format

```yaml
test_cases:
  - id: "sdp_bronze_001"
    inputs:
      prompt: "Create a bronze ingestion pipeline"
    outputs:
      response: |
        ```sql
        CREATE OR REFRESH STREAMING TABLE...
        ```
      execution_success: true
    expectations:
      expected_facts:
        - "STREAMING TABLE"
      expected_patterns:
        - pattern: "CREATE OR REFRESH"
          min_count: 1
      guidelines:
        - "Must use modern SDP syntax"
    metadata:
      category: "happy_path"
```

## Directory Structure

```
skill-test/
├── src/
│   ├── config.py          # Configuration
│   ├── dataset.py         # YAML/UC data loading
│   ├── scorers/           # Evaluation scorers
│   ├── grp/               # Generate-Review-Promote pipeline
│   └── runners/           # Evaluation runners
├── skills/                # Per-skill test definitions
│   ├── _routing/          # Routing test cases
│   └── {skill-name}/      # Skill-specific tests
└── baselines/             # Regression baselines
```

## References

- [YAML Schemas](references/yaml-schemas.md) - Manifest and ground truth formats
- [Scorers](references/scorers.md) - Available evaluation scorers
