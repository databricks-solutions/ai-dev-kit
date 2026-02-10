# Synthetic Data Generation

Generate realistic synthetic data using Faker and Spark, with non-linear distributions, integrity constraints, and save to Databricks.

## Overview

This skill guides the generation of realistic, story-driven synthetic data for Databricks using Python with Faker, NumPy, and Spark. It activates when users need test data, demo datasets, or synthetic tables with believable distributions and referential integrity. The generated data is saved as raw Parquet files to Unity Catalog Volumes, ready for downstream processing through Spark Declarative Pipelines (bronze/silver/gold layers).

## What's Included

```
synthetic-data-generation/
└── SKILL.md
```

## Key Topics

- Workflow: write Python scripts locally, execute on Databricks via MCP tools, iterate on failures
- Context reuse pattern for faster execution (`cluster_id` and `context_id` persistence)
- Storage destination: Unity Catalog Volumes with `ai_dev_kit` catalog default
- Raw transactional data only (no pre-aggregated fields) to feed downstream SDP pipelines
- Referential integrity: generate master tables first, then child tables with valid foreign keys
- Non-linear distributions: log-normal for prices, exponential for durations, weighted categoricals
- Time-based patterns: weekday/weekend effects, holiday calendars, seasonality, event spikes
- Row coherence: correlated attributes (tier affects priority, priority affects resolution time, resolution affects CSAT)
- Data volume guidelines: 10K-50K minimum rows so patterns survive GROUP BY aggregation
- Dynamic date ranges: last 6 months from current date
- Script structure with configuration variables at top and validation at bottom
- Pandas for generation, Spark for saving to Volumes

## When to Use

- Creating test or demo datasets for Databricks
- Generating synthetic data with realistic distributions
- Building data that preserves referential integrity across multiple tables
- Preparing raw data for a medallion architecture pipeline
- Needing reproducible datasets with configurable seeds and volumes
- Prototyping dashboards or analytics with believable data

## Related Skills

- [Spark Declarative Pipelines](../spark-declarative-pipelines/) -- for building bronze/silver/gold pipelines on top of generated data
- [AI/BI Dashboards](../aibi-dashboards/) -- for visualizing the generated data in dashboards
- [Databricks Unity Catalog](../databricks-unity-catalog/) -- for managing catalogs, schemas, and volumes where data is stored

## Resources

- [Unity Catalog Volumes](https://docs.databricks.com/en/connect/unity-catalog/volumes.html)
- [Faker Library Documentation](https://faker.readthedocs.io/)
- [Databricks Execution Context API](https://docs.databricks.com/api/workspace/commandexecution)
