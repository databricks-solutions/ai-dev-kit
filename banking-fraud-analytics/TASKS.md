# Fraud Triage Agent — Task Tracker

## Status Legend
- [x] Completed
- [ ] Pending
- [~] In Progress

## Tasks

### Phase 1: Project Setup
- [x] Create DEMO.md architecture document
- [x] Create TASKS.md tracker
- [ ] Initialize uv project with pyproject.toml
- [ ] Create databricks.yml bundle config
- [ ] Verify Unity Catalog schema + volumes exist

### Phase 2: Synthetic Data Generation
- [ ] Write generate_fraud_data.py (transactions + login events)
- [ ] Test data generation locally with Databricks Connect
- [ ] Deploy data generation job via bundle
- [ ] Run and verify data in UC tables

### Phase 3: AI Reasoning Agent
- [ ] Write fraud_scoring_agent.py using Claude on Databricks
- [ ] Design prompt template for fraud explanation
- [ ] Test locally with sample transactions

### Phase 4: Streaming Pipeline
- [ ] Write streaming_pipeline.py (Structured Streaming)
- [ ] Implement feature join (transaction + login events)
- [ ] Implement Lakebase upsert for fraud_risk_state
- [ ] Deploy and run streaming job

### Phase 5: Databricks App (Live Fraud Queue)
- [ ] Write FastAPI backend (app.py)
- [ ] Build analyst dashboard UI
- [ ] Add approve/block transaction actions
- [ ] Test locally
- [ ] Deploy to Databricks Apps

### Phase 6: Genie Space
- [ ] Create Genie Space with fraud tables
- [ ] Add example queries
- [ ] Verify natural language queries work

### Phase 7: Validation
- [ ] End-to-end test: data → scoring → app
- [ ] Verify all components deployed and running
