# Fraud Triage Agent Demo

## Overview

A full-stack, Lakehouse-native fraud detection and analyst triage system built entirely on Databricks. Demonstrates how modern AI can address industrialized fraud attacks (GenAI-powered phishing, account takeover, synthetic identity fraud) in real-time.

## Business Problem

Banks face three critical fraud challenges:
1. **False Positive Overload** — Legacy systems flag up to 90% legitimate transactions
2. **Latency Gap** — Batch detection means funds have already left accounts
3. **Analyst Bottleneck** — Manual investigation with no AI-assisted reasoning

## Architecture

```
Raw Data (Volumes)
    │
    ▼
[Synthetic Data Generation]
    │  (dbldatagen → Parquet/Delta in UC Volumes)
    │
    ▼
[Bronze Layer] → raw_transactions, raw_login_events (Delta Tables)
    │
    ▼
[Silver Layer] → enriched_transactions, enriched_login_events (joined, cleaned)
    │
    ▼
[Gold Layer] → fraud_alert_candidates (high-risk patterns identified)
    │                │
    │                ▼
    │     [Genie Space] ← Natural language analyst investigation
    │
    ▼
[Streaming Pipeline]
    │  (Structured Streaming: ingest → feature join → AI scoring → upsert)
    │
    ▼
[Lakebase: fraud_risk_state] ← Low-latency state store
    │
    ▼
[AI Reasoning Agent]
    │  (Claude on Databricks → risk_score, risk_category, plain-english explanation)
    │
    ▼
[Live Fraud Queue — Databricks App]
    ├── Real-time alert dashboard
    ├── Risk score filtering
    ├── AI explanation review
    └── Approve / Block actions
```

## Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Synthetic Data | dbldatagen + PySpark | Realistic fraud telemetry at scale |
| Data Pipeline | Spark Declarative Pipeline | Bronze → Silver → Gold transformations |
| Genie Space | Databricks Genie | Natural language fraud investigation |
| AI Reasoning | Claude (databricks-claude-sonnet-4-5) | Explainable fraud scoring |
| Streaming | Structured Streaming + Lakebase | Sub-second risk state updates |
| Analyst UI | Databricks Apps (FastAPI + React-like) | Live fraud queue triage |

## Workspace

- **Workspace**: https://fevm-sv-ai-builder-workspace.cloud.databricks.com
- **Catalog**: sv_ai_builder_workspace_catalog
- **Schema**: fraud_demo
- **Profile**: DEFAULT

## Scale Target

- 50M transactions/day
- 10M login events/day
- Sub-second fraud state updates via Lakebase
