# Memory Schema Reference

Complete DDL for memory tables in Unity Catalog.

## Core Tables

### decisions

Explicit choices made during development or operation.

```sql
CREATE TABLE IF NOT EXISTS my_catalog.memory.decisions (
    id STRING DEFAULT uuid() NOT NULL,
    decision TEXT NOT NULL COMMENT 'The decision that was made',
    context TEXT COMMENT 'What situation led to this decision',
    rationale TEXT COMMENT 'Why this decision was made',
    alternatives TEXT COMMENT 'Other options considered',
    created_at TIMESTAMP DEFAULT current_timestamp(),
    created_by STRING DEFAULT current_user(),
    confidence DOUBLE DEFAULT 1.0 COMMENT '0.0-1.0 confidence score',
    tags ARRAY<STRING> COMMENT 'Categorization tags',
    task_scope STRING COMMENT 'Which task/domain this applies to',
    expires_at TIMESTAMP COMMENT 'Optional expiration for time-bound decisions',
    CONSTRAINT decisions_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Explicit decisions that inform prompt construction'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);

-- Index for task-scoped queries
CREATE INDEX IF NOT EXISTS idx_decisions_task 
ON my_catalog.memory.decisions (task_scope, created_at DESC);
```

### patterns

Learned behaviors extracted from production data or feedback.

```sql
CREATE TABLE IF NOT EXISTS my_catalog.memory.patterns (
    id STRING DEFAULT uuid() NOT NULL,
    pattern TEXT NOT NULL COMMENT 'The learned pattern',
    evidence TEXT COMMENT 'Examples or proof of this pattern',
    source STRING COMMENT 'Where this pattern was learned from',
    frequency INT DEFAULT 1 COMMENT 'How often this pattern has been observed',
    first_seen TIMESTAMP DEFAULT current_timestamp(),
    last_seen TIMESTAMP DEFAULT current_timestamp(),
    confidence DOUBLE COMMENT 'Confidence score, often based on frequency',
    tags ARRAY<STRING>,
    task_scope STRING,
    superseded_by STRING COMMENT 'ID of pattern that replaces this one',
    CONSTRAINT patterns_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Patterns learned from production data and feedback'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);

-- Index for high-frequency patterns
CREATE INDEX IF NOT EXISTS idx_patterns_freq 
ON my_catalog.memory.patterns (task_scope, frequency DESC);
```

### feedback

User corrections, preferences, and complaints.

```sql
CREATE TABLE IF NOT EXISTS my_catalog.memory.feedback (
    id STRING DEFAULT uuid() NOT NULL,
    run_id STRING COMMENT 'MLflow run ID if available',
    trace_id STRING COMMENT 'MLflow trace ID if available',
    input_text TEXT COMMENT 'The input that produced the output',
    input_hash STRING COMMENT 'Hash of input for deduplication',
    output_text TEXT COMMENT 'What the model produced',
    correction TEXT COMMENT 'What the user said it should be',
    feedback_type STRING NOT NULL COMMENT 'correction, preference, complaint, praise',
    severity STRING DEFAULT 'medium' COMMENT 'low, medium, high, critical',
    created_at TIMESTAMP DEFAULT current_timestamp(),
    created_by STRING,
    resolved BOOLEAN DEFAULT false,
    resolved_by_pattern_id STRING COMMENT 'Pattern created to address this',
    tags ARRAY<STRING>,
    task_scope STRING,
    CONSTRAINT feedback_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'User feedback on model outputs'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);

-- Index for unresolved feedback
CREATE INDEX IF NOT EXISTS idx_feedback_unresolved 
ON my_catalog.memory.feedback (resolved, task_scope, created_at DESC);
```

## Supporting Tables

### memory_embeddings

Unified embedding table for Vector Search.

```sql
CREATE TABLE IF NOT EXISTS my_catalog.memory.memory_embeddings (
    id STRING NOT NULL,
    memory_type STRING NOT NULL COMMENT 'decision, pattern, or feedback',
    source_id STRING NOT NULL COMMENT 'ID in source table',
    content TEXT NOT NULL COMMENT 'Text to embed',
    embedding ARRAY<FLOAT> COMMENT 'Vector embedding',
    task_scope STRING,
    confidence DOUBLE,
    created_at TIMESTAMP DEFAULT current_timestamp(),
    CONSTRAINT embeddings_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Unified embeddings for semantic memory search';

-- Create Vector Search index
-- Note: Run this separately after table creation
/*
CREATE VECTOR SEARCH INDEX memory_index
ON my_catalog.memory.memory_embeddings (embedding)
USING 'databricks-gte-large-en'
OPTIONS (
    metric_type = 'cosine',
    num_dimensions = 1024
);
*/
```

### prompt_memory_links

Track which memories influenced which prompt versions.

```sql
CREATE TABLE IF NOT EXISTS my_catalog.memory.prompt_memory_links (
    id STRING DEFAULT uuid() NOT NULL,
    prompt_name STRING NOT NULL COMMENT 'MLflow prompt registry name',
    prompt_version INT NOT NULL,
    memory_type STRING NOT NULL,
    memory_id STRING NOT NULL,
    influence_score DOUBLE COMMENT 'How much this memory influenced the prompt',
    created_at TIMESTAMP DEFAULT current_timestamp(),
    CONSTRAINT links_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Links between prompts and the memories that shaped them';
```

## Retention Policies

```sql
-- Clean up old, low-confidence patterns (run weekly)
DELETE FROM my_catalog.memory.patterns
WHERE confidence < 0.3 
  AND last_seen < current_timestamp() - INTERVAL 90 DAYS
  AND superseded_by IS NOT NULL;

-- Archive resolved feedback older than 1 year
-- (Move to archive table, not shown here)

-- Decay confidence for stale patterns
UPDATE my_catalog.memory.patterns
SET confidence = confidence * 0.95
WHERE last_seen < current_timestamp() - INTERVAL 30 DAYS
  AND confidence > 0.1;
```

## Migration Script

```python
def create_memory_schema(catalog: str, schema: str):
    """Create all memory tables in the specified location."""
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.getOrCreate()
    
    # Create schema if not exists
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
    
    # Read and execute DDL
    ddl_statements = [
        # decisions table
        f"""CREATE TABLE IF NOT EXISTS {catalog}.{schema}.decisions ...""",
        # patterns table  
        f"""CREATE TABLE IF NOT EXISTS {catalog}.{schema}.patterns ...""",
        # feedback table
        f"""CREATE TABLE IF NOT EXISTS {catalog}.{schema}.feedback ...""",
        # embeddings table
        f"""CREATE TABLE IF NOT EXISTS {catalog}.{schema}.memory_embeddings ...""",
        # links table
        f"""CREATE TABLE IF NOT EXISTS {catalog}.{schema}.prompt_memory_links ...""",
    ]
    
    for ddl in ddl_statements:
        spark.sql(ddl)
    
    print(f"Memory schema created at {catalog}.{schema}")
```
