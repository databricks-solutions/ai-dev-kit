# Continuous Learning Pipeline

A Lakeflow Declarative Pipeline that extracts patterns from feedback and maintains memory health.

## Overview

This pipeline runs on a schedule (daily or weekly) to:
1. Extract patterns from accumulated feedback
2. Update confidence scores based on usage
3. Decay stale memories
4. Generate memory health reports

## Pipeline Definition

```yaml
# learning_pipeline.yml
name: memory_learning_pipeline
catalog: ${catalog}
schema: ${schema}

clusters:
  - label: default
    num_workers: 2
    spark_version: "15.4.x-scala2.12"

libraries:
  - notebook:
      path: /Workspace/memory/learning_pipeline

schedule:
  quartz_cron_expression: "0 0 2 * * ?"  # Daily at 2 AM
  timezone_id: "UTC"
```

## Pipeline Notebook

```python
# learning_pipeline notebook

import dlt
from pyspark.sql.functions import (
    col, expr, count, avg, max as max_, 
    current_timestamp, lit, when, concat_ws
)

# Configuration
PATTERN_MIN_FREQUENCY = 3  # Minimum occurrences to extract pattern
CONFIDENCE_DECAY_RATE = 0.95  # Weekly decay multiplier
STALE_THRESHOLD_DAYS = 30

@dlt.table(
    name="feedback_aggregates",
    comment="Aggregated feedback ready for pattern extraction"
)
def feedback_aggregates():
    """Group similar feedback for pattern extraction."""
    return (
        spark.table("my_catalog.memory.feedback")
        .filter(col("resolved") == False)
        .filter(col("created_at") > expr("current_timestamp() - INTERVAL 30 DAYS"))
        .groupBy("task_scope", "feedback_type")
        .agg(
            count("*").alias("frequency"),
            concat_ws(" || ", expr("collect_list(correction)")).alias("corrections"),
            concat_ws(" || ", expr("collect_list(output_text)")).alias("outputs"),
            max_("created_at").alias("latest")
        )
        .filter(col("frequency") >= PATTERN_MIN_FREQUENCY)
    )

@dlt.table(
    name="extracted_patterns",
    comment="Patterns extracted from feedback using LLM"
)
def extracted_patterns():
    """Use LLM to extract patterns from aggregated feedback."""
    return (
        dlt.read("feedback_aggregates")
        .withColumn("pattern", expr(f"""
            ai_query(
                'databricks-meta-llama-3-3-70b-instruct',
                concat(
                    'You are analyzing user feedback to extract a reusable pattern. ',
                    'Task scope: ', task_scope, '. ',
                    'Feedback type: ', feedback_type, '. ',
                    'Number of occurrences: ', frequency, '. ',
                    'Sample corrections: ', substr(corrections, 1, 500), '. ',
                    'Extract ONE concise pattern that would prevent this feedback. ',
                    'Format: A single sentence describing what to do or avoid. ',
                    'Do not include explanations or preamble.'
                )
            )
        """))
        .select(
            expr("uuid()").alias("id"),
            col("pattern"),
            col("corrections").alias("evidence"),
            lit("feedback_extraction").alias("source"),
            col("frequency"),
            col("task_scope"),
            expr("0.5 + (0.5 * least(frequency / 10.0, 1.0))").alias("confidence")
        )
    )

@dlt.table(
    name="pattern_updates",
    comment="Updates to apply to patterns table"
)
def pattern_updates():
    """
    Merge extracted patterns with existing ones.
    - New patterns: insert
    - Existing similar patterns: increment frequency
    """
    extracted = dlt.read("extracted_patterns")
    existing = spark.table("my_catalog.memory.patterns")
    
    # Find similar patterns using semantic similarity
    return (
        extracted.alias("new")
        .join(
            existing.alias("old"),
            expr("ai_similarity(new.pattern, old.pattern) > 0.85"),
            "left"
        )
        .select(
            when(col("old.id").isNotNull(), col("old.id"))
                .otherwise(col("new.id")).alias("id"),
            when(col("old.id").isNotNull(), col("old.pattern"))
                .otherwise(col("new.pattern")).alias("pattern"),
            col("new.evidence"),
            col("new.source"),
            when(col("old.id").isNotNull(), col("old.frequency") + col("new.frequency"))
                .otherwise(col("new.frequency")).alias("frequency"),
            when(col("old.id").isNotNull(), col("old.first_seen"))
                .otherwise(current_timestamp()).alias("first_seen"),
            current_timestamp().alias("last_seen"),
            when(col("old.id").isNotNull(), 
                 expr("greatest(old.confidence, new.confidence)"))
                .otherwise(col("new.confidence")).alias("confidence"),
            col("new.task_scope"),
            lit(None).alias("superseded_by"),
            col("old.id").isNotNull().alias("is_update")
        )
    )

@dlt.table(
    name="confidence_decay",
    comment="Patterns with decayed confidence"
)
def confidence_decay():
    """Apply confidence decay to stale patterns."""
    return (
        spark.table("my_catalog.memory.patterns")
        .filter(col("last_seen") < expr(f"current_timestamp() - INTERVAL {STALE_THRESHOLD_DAYS} DAYS"))
        .filter(col("confidence") > 0.1)
        .select(
            col("id"),
            (col("confidence") * CONFIDENCE_DECAY_RATE).alias("new_confidence")
        )
    )

@dlt.table(
    name="memory_health_report",
    comment="Daily memory health metrics"
)
def memory_health_report():
    """Generate health metrics for monitoring."""
    decisions = spark.table("my_catalog.memory.decisions")
    patterns = spark.table("my_catalog.memory.patterns")
    feedback = spark.table("my_catalog.memory.feedback")
    
    return spark.sql(f"""
        SELECT
            current_timestamp() AS report_time,
            
            -- Decisions metrics
            (SELECT COUNT(*) FROM my_catalog.memory.decisions) AS total_decisions,
            (SELECT COUNT(*) FROM my_catalog.memory.decisions 
             WHERE created_at > current_timestamp() - INTERVAL 7 DAYS) AS new_decisions_7d,
            (SELECT AVG(confidence) FROM my_catalog.memory.decisions) AS avg_decision_confidence,
            
            -- Patterns metrics
            (SELECT COUNT(*) FROM my_catalog.memory.patterns) AS total_patterns,
            (SELECT COUNT(*) FROM my_catalog.memory.patterns 
             WHERE last_seen > current_timestamp() - INTERVAL 7 DAYS) AS active_patterns_7d,
            (SELECT AVG(confidence) FROM my_catalog.memory.patterns) AS avg_pattern_confidence,
            (SELECT AVG(frequency) FROM my_catalog.memory.patterns) AS avg_pattern_frequency,
            
            -- Feedback metrics
            (SELECT COUNT(*) FROM my_catalog.memory.feedback) AS total_feedback,
            (SELECT COUNT(*) FROM my_catalog.memory.feedback WHERE resolved = false) AS unresolved_feedback,
            (SELECT COUNT(*) FROM my_catalog.memory.feedback 
             WHERE created_at > current_timestamp() - INTERVAL 7 DAYS) AS new_feedback_7d,
            
            -- Health indicators
            (SELECT COUNT(*) FROM my_catalog.memory.patterns 
             WHERE confidence < 0.3) AS low_confidence_patterns,
            (SELECT COUNT(*) FROM my_catalog.memory.patterns 
             WHERE last_seen < current_timestamp() - INTERVAL 90 DAYS) AS stale_patterns
    """)
```

## Apply Updates

After the pipeline runs, apply the changes:

```python
# Run as a separate job after pipeline completes

from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()

# Insert new patterns, update existing ones
spark.sql("""
    MERGE INTO my_catalog.memory.patterns AS target
    USING my_catalog.memory.pattern_updates AS source
    ON target.id = source.id
    WHEN MATCHED AND source.is_update = true THEN UPDATE SET
        frequency = source.frequency,
        last_seen = source.last_seen,
        confidence = source.confidence,
        evidence = concat(target.evidence, ' || ', source.evidence)
    WHEN NOT MATCHED THEN INSERT *
""")

# Apply confidence decay
spark.sql("""
    MERGE INTO my_catalog.memory.patterns AS target
    USING my_catalog.memory.confidence_decay AS source
    ON target.id = source.id
    WHEN MATCHED THEN UPDATE SET
        confidence = source.new_confidence
""")

# Mark feedback as resolved where patterns were created
spark.sql("""
    UPDATE my_catalog.memory.feedback
    SET resolved = true,
        resolved_by_pattern_id = (
            SELECT p.id FROM my_catalog.memory.patterns p
            WHERE ai_similarity(feedback.correction, p.pattern) > 0.8
            ORDER BY p.last_seen DESC
            LIMIT 1
        )
    WHERE resolved = false
    AND EXISTS (
        SELECT 1 FROM my_catalog.memory.patterns p
        WHERE ai_similarity(feedback.correction, p.pattern) > 0.8
    )
""")

print("Memory updates applied successfully")
```

## Monitoring

### Alerts

Set up alerts on the health report:

```python
# In a monitoring notebook
health = spark.table("my_catalog.memory.memory_health_report").orderBy(col("report_time").desc()).first()

alerts = []
if health.unresolved_feedback > 50:
    alerts.append(f"High unresolved feedback: {health.unresolved_feedback}")
if health.low_confidence_patterns > 20:
    alerts.append(f"Many low-confidence patterns: {health.low_confidence_patterns}")
if health.stale_patterns > 30:
    alerts.append(f"Many stale patterns: {health.stale_patterns}")

if alerts:
    # Send to Slack/email/etc
    notify(alerts)
```

### Dashboard

Create a SQL dashboard with:

```sql
-- Memory growth over time
SELECT DATE(report_time) AS date,
       total_decisions,
       total_patterns,
       total_feedback
FROM my_catalog.memory.memory_health_report
ORDER BY date;

-- Pattern confidence distribution
SELECT 
    CASE 
        WHEN confidence >= 0.8 THEN 'High (0.8+)'
        WHEN confidence >= 0.5 THEN 'Medium (0.5-0.8)'
        ELSE 'Low (<0.5)'
    END AS confidence_band,
    COUNT(*) AS pattern_count
FROM my_catalog.memory.patterns
GROUP BY 1;

-- Top patterns by usage
SELECT pattern, frequency, confidence, last_seen
FROM my_catalog.memory.patterns
ORDER BY frequency DESC
LIMIT 20;
```
