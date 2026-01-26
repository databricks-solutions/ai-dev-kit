# Skill Testing Framework

Test Databricks skills with real execution on serverless compute.

## Prerequisites

```bash
pip install -e databricks-skills/skill-test
```

Requires a Databricks workspace with serverless SQL/compute enabled.

## Quick Start

### 1. Test an Existing Skill

```
/skill-test spark-declarative-pipelines
```

This runs all test cases in `skills/spark-declarative-pipelines/ground_truth.yaml` and reports pass/fail for each code block.

### 2. Add a New Test Case

```
/skill-test spark-declarative-pipelines add
```

Claude will:
1. Ask for your test prompt
2. Invoke the skill to generate a response
3. Execute code blocks on Databricks
4. Auto-save passing tests to `ground_truth.yaml`
5. Save failing tests to `candidates.yaml` for review

### 3. Create a Regression Baseline

```
/skill-test spark-declarative-pipelines baseline
```

Saves current metrics to `baselines/spark-declarative-pipelines/baseline.yaml`.

### 4. Check for Regressions

```
/skill-test spark-declarative-pipelines regression
```

Compares current pass rate against the saved baseline.

## Test a New Skill

```
/skill-test my-new-skill init
```

Creates scaffolding:
```
skills/my-new-skill/
├── ground_truth.yaml   # Verified test cases
├── candidates.yaml     # Pending review
└── manifest.yaml       # Skill metadata
```

## Test Case Format

```yaml
test_cases:
  - id: "sdp_bronze_001"
    inputs:
      prompt: "Create a bronze ingestion pipeline for JSON files"
    outputs:
      response: |
        ```sql
        CREATE OR REFRESH STREAMING TABLE bronze_events
        AS SELECT * FROM STREAM read_files('/data/events/*.json')
        ```
      execution_success: true
    expectations:
      expected_facts:
        - "STREAMING TABLE"
      guidelines:
        - "Must use modern SDP syntax"
```

## Directory Structure

```
skill-test/
├── skills/                    # Test definitions per skill
│   └── {skill-name}/
│       ├── ground_truth.yaml  # Verified tests
│       └── candidates.yaml    # Pending review
├── baselines/                 # Regression baselines
└── src/                       # Framework code
```

## Subcommands

| Command | Description |
|---------|-------------|
| `run` | Execute tests against ground truth (default) |
| `add` | Interactively add a new test case |
| `baseline` | Save current results as regression baseline |
| `regression` | Compare against baseline |
| `mlflow` | Run MLflow evaluation with LLM judges |
| `init` | Create scaffolding for a new skill |
