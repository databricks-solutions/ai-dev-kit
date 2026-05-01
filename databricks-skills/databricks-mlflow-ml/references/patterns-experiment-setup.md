# patterns-experiment-setup

Experiments in UC-enforced workspaces need more setup than older MLflow guides show. The critical change: you must pin the experiment's `artifact_location` to a Unity Catalog volume, or `log_model` will fail with storage errors.

---

## Pattern 1: Create experiment with UC volume artifact_location

```python
import mlflow

mlflow.set_registry_uri("databricks-uc")   # always first

# Prerequisite: the UC volume must exist
# CREATE VOLUME IF NOT EXISTS my_catalog.my_schema.mlflow_artifacts;

mlflow.set_experiment(
    experiment_name="/Users/me@company.com/forecasting",
    artifact_location="dbfs:/Volumes/my_catalog/my_schema/mlflow_artifacts/forecasting",
)
```

**Why both are required:**
- `experiment_name` — the workspace-visible path (browsable from the Experiments UI)
- `artifact_location` — where logged artifacts (model binaries, plots, datasets) physically live

In older workspaces, `artifact_location` defaulted to DBFS root. UC-enforced workspaces reject DBFS root writes, so `log_model` fails with opaque errors like:

```
MlflowException: API request to endpoint /api/2.0/mlflow/runs/log-artifact failed
with error code 403 != 200. Response body: PERMISSION_DENIED ...
```

Pointing at a UC volume resolves this AND makes artifacts first-class-governed under UC lineage.

---

## Pattern 2: Create the volume if it doesn't exist (idempotent)

Run once per schema, before any experiment creation:

```python
spark.sql(f"""
    CREATE VOLUME IF NOT EXISTS my_catalog.my_schema.mlflow_artifacts
    COMMENT 'MLflow experiment artifacts for forecasting models'
""")
```

Or via SQL editor:

```sql
CREATE VOLUME IF NOT EXISTS my_catalog.my_schema.mlflow_artifacts;
```

**Permissions needed:** `USE SCHEMA` + `CREATE VOLUME`. If missing, request `CREATE VOLUME ON SCHEMA my_catalog.my_schema` from the schema owner.

---

## Pattern 3: Experiment already exists, wrong `artifact_location`

You can't retroactively change `artifact_location`. Three options, in order of preference:

**Option A — New experiment** (cleanest, keeps old runs intact):
```python
mlflow.set_experiment(
    experiment_name="/Users/me@company.com/forecasting_v2",   # v2 suffix
    artifact_location="dbfs:/Volumes/my_catalog/my_schema/mlflow_artifacts/forecasting_v2",
)
# New runs land in v2. Old runs stay in v1 (archive them if you like).
```

**Option B — Delete + recreate** (loses history; use only if no good runs exist):
```python
from mlflow import MlflowClient
client = MlflowClient()

exp = client.get_experiment_by_name("/Users/me@company.com/forecasting")
client.delete_experiment(exp.experiment_id)

mlflow.set_experiment(
    experiment_name="/Users/me@company.com/forecasting",
    artifact_location="dbfs:/Volumes/my_catalog/my_schema/mlflow_artifacts/forecasting",
)
```

**Option C — Manual relocation of DBFS artifacts to UC volume**: do not do this. Storage paths are resolved at log time and encoded in the run's metadata; moving files doesn't update the pointers.

---

## Pattern 4: Verify experiment is correctly configured

After setup, before training:

```python
exp = mlflow.get_experiment_by_name("/Users/me@company.com/forecasting")
assert exp is not None, "Experiment not created"
assert exp.artifact_location.startswith("dbfs:/Volumes/"), (
    f"artifact_location is not a UC volume: {exp.artifact_location}"
)
print(f"Experiment ID: {exp.experiment_id}")
print(f"Artifact location: {exp.artifact_location}")
```

If the assert fails, you have an old experiment pointing at DBFS root. Apply Pattern 3.

---

## Pattern 5: Workspace-path vs Repo-path experiments

MLflow accepts two conventions for `experiment_name`:

```python
# Workspace-path convention (recommended for collaborative experiments)
mlflow.set_experiment(experiment_name="/Users/me@company.com/forecasting")

# Repo-path convention (only if you're running from a Git folder)
mlflow.set_experiment(experiment_name="/Repos/me@company.com/my-repo/forecasting")
```

**Prefer workspace path** for experiments shared across pairs/teams. Repo-path experiments become orphans when the repo is deleted.

**Both need `artifact_location` pointing at a UC volume.** The path convention only affects where the experiment metadata is browsable, not where artifacts live.

---

## Pattern 6: Running from a notebook cell with autoselected experiment

Databricks notebooks auto-associate runs with an experiment matching the notebook's workspace path:

```python
# In a notebook at /Users/me@company.com/Notebooks/train.py
# Databricks will auto-set experiment_name to the notebook path
# BUT the default artifact_location is still DBFS root — you still need to override:

mlflow.set_experiment(
    experiment_name="/Users/me@company.com/Notebooks/train",
    artifact_location="dbfs:/Volumes/my_catalog/my_schema/mlflow_artifacts/train",
)
```

Or call `set_experiment` explicitly before the first `start_run` — the artifact_location fix must be applied regardless of notebook auto-association.
