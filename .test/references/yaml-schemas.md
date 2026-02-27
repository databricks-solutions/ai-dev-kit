# YAML Schemas Reference

## Skill Manifest (`skills/{skill}/manifest.yaml`)

Defines skill metadata, evaluation datasets, scorers by tier, and quality gates.

```yaml
skill:
  name: "databricks-spark-declarative-pipelines"
  source_path: "databricks-skills/databricks-spark-declarative-pipelines"
  description: "Streaming tables, CDC, medallion architecture"

evaluation:
  datasets:
    - path: ground_truth.yaml
      type: yaml

  scorers:
    tier1:  # Deterministic (fast)
      - python_syntax
      - sql_syntax
      - pattern_adherence
      - no_hallucinated_apis
    tier2:  # Execution-based
      - code_executes
    tier3:  # LLM Judge
      - Guidelines

  quality_gates:
    tier1_pass_rate: 1.0
    tier2_pass_rate: 0.8
    tier3_pass_rate: 0.85
```

## Ground Truth (`skills/{skill}/ground_truth.yaml`)

Test cases with inputs, expected outputs, expectations, and metadata.

```yaml
test_cases:
  - id: "sdp_bronze_ingestion_001"

    inputs:
      prompt: "Create a bronze ingestion pipeline for JSON files in /Volumes/raw/orders"

    outputs:
      response: |
        Here's a bronze ingestion pipeline using Spark Declarative Pipelines...

        ```sql
        CREATE OR REFRESH STREAMING TABLE bronze_orders
        CLUSTER BY (order_date)
        AS SELECT *, current_timestamp() AS _ingested_at
        FROM read_files('/Volumes/raw/orders', format => 'json');
        ```
      execution_success: true

    expectations:
      expected_facts:
        - "Uses STREAMING TABLE for incremental ingestion"
        - "Uses CLUSTER BY instead of PARTITION BY"
        - "Includes _ingested_at timestamp"

      expected_patterns:
        - pattern: "CREATE OR REFRESH STREAMING TABLE"
          min_count: 1
        - pattern: "CLUSTER BY"
          min_count: 1
        - pattern: "read_files\\s*\\("
          min_count: 1

      guidelines:
        - "Must use modern SDP syntax, not legacy DLT"
        - "Should include metadata columns for lineage"

    metadata:
      category: "happy_path"
      difficulty: "easy"
      source: "manual"
      tags: ["bronze", "ingestion", "autoloader"]
```

## Routing Tests (`skills/_routing/ground_truth.yaml`)

Tests for skill trigger detection with single-skill, multi-skill, and no-match scenarios.

```yaml
test_cases:
  # Single-skill routing
  - id: "routing_sdp_001"
    inputs:
      prompt: "Create a streaming table for ingesting JSON events"
    expectations:
      expected_skills: ["databricks-spark-declarative-pipelines"]
      is_multi_skill: false
    metadata:
      category: "single_skill"
      difficulty: "easy"
      reasoning: "Mentions 'streaming table' - clear SDP trigger"

  - id: "routing_sdk_001"
    inputs:
      prompt: "How do I list clusters using the Python SDK?"
    expectations:
      expected_skills: ["databricks-python-sdk"]
      is_multi_skill: false
    metadata:
      category: "single_skill"
      difficulty: "easy"

  # Multi-skill routing
  - id: "routing_multi_001"
    inputs:
      prompt: "Create a data pipeline with streaming tables and deploy it using DABs"
    expectations:
      expected_skills:
        - "databricks-spark-declarative-pipelines"
        - "databricks-asset-bundles"
      is_multi_skill: true
    metadata:
      category: "multi_skill"
      difficulty: "medium"

  # No skill match
  - id: "routing_no_match_001"
    inputs:
      prompt: "What is the weather like today?"
    expectations:
      expected_skills: []
      is_multi_skill: false
    metadata:
      category: "no_match"
      difficulty: "easy"
```
