# patterns-uc-registration

Register a logged model to Unity Catalog, set aliases, verify, and handle promotion / rollback.

---

## Pattern 1: Explicit register from a specific run

Cleanest workflow. Train (separate step) → pick best run → register.

```python
import mlflow
from mlflow import MlflowClient

mlflow.set_registry_uri("databricks-uc")

MODEL_NAME = "my_catalog.my_schema.grocery_forecaster"

# run_id from a specific training run (see patterns-training.md Pattern 6)
run_id = "abc123def456"

result = mlflow.register_model(
    model_uri=f"runs:/{run_id}/model",
    name=MODEL_NAME,
    tags={
        "trained_by": "forecasting_team",
        "dataset_version": "2024-Q4",
    },
)
print(f"Registered {MODEL_NAME} version {result.version}")
```

`result` is a `ModelVersion` object:
- `result.name` — fully qualified three-level name
- `result.version` — the new version (string, e.g., `"3"`)
- `result.status` — should be `"READY"` by the time this returns

---

## Pattern 2: Log-and-register in one call

Shorter but couples logging and registration. Use when you *know* the current run is the one worth registering.

```python
with mlflow.start_run():
    model.fit(X_train, y_train)
    mlflow.sklearn.log_model(
        sk_model=model,
        artifact_path="model",
        signature=infer_signature(X_train, model.predict(X_train[:5])),
        input_example=X_train.iloc[:5],
        registered_model_name="my_catalog.my_schema.grocery_forecaster",
    )
    # Model is registered as a new version; you still need to set alias separately.
```

**Still need a separate alias call** — `log_model` doesn't set aliases.

---

## Pattern 3: Set aliases (`@champion`, `@challenger`)

Aliases decouple the loader from the version. Moving `@champion` to a new version silently updates every `models:/...@champion` loader.

```python
from mlflow import MlflowClient
client = MlflowClient()

# Set or move an alias
client.set_registered_model_alias(
    name="my_catalog.my_schema.grocery_forecaster",
    alias="champion",
    version=result.version,
)
```

**Conventions:**
- `@champion` — the current production winner. Exactly one version at a time.
- `@challenger` — a candidate under evaluation. Exactly one at a time.
- Custom aliases — free-form, e.g., `@pair_team_07`, `@nightly`, `@reviewed`.

**Read existing aliases:**
```python
model = client.get_registered_model("my_catalog.my_schema.grocery_forecaster")
print(model.aliases)   # e.g., {"champion": "3", "challenger": "4"}
```

**Delete an alias:**
```python
client.delete_registered_model_alias(
    name="my_catalog.my_schema.grocery_forecaster",
    alias="challenger",
)
```

---

## Pattern 4: Verify registration (Navigator's V-step)

Don't trust `register_model`'s success message alone. See `GOTCHAS.md` #5.

### Via SQL

```sql
DESCRIBE MODEL my_catalog.my_schema.grocery_forecaster;
```

Expected output includes the model metadata and (if set) aliases. If the result is "table or view not found," the model didn't register to UC — check `set_registry_uri` (GOTCHAS #1).

### Via Catalog Explorer UI

1. Open Catalog Explorer
2. Navigate to `my_catalog` → `my_schema` → **Models** tab
3. Confirm `grocery_forecaster` appears with an `@champion` badge

If the model appears under the workspace MLflow icon instead (left sidebar, under MLflow), you registered to the workspace registry. See GOTCHAS #1.

### Via Python assertion (scriptable)

```python
from mlflow import MlflowClient
client = MlflowClient()

model = client.get_registered_model("my_catalog.my_schema.grocery_forecaster")

# Three assertions that should always hold post-registration
assert model is not None, "Model not registered to UC"
assert len(model.latest_versions) > 0, "No versions exist"
assert "champion" in model.aliases, "@champion alias not set"
print(f"✓ {model.name} v{model.aliases['champion']} is @champion")
```

---

## Pattern 5: A/B promotion — swap `@challenger` to `@champion`

You've trained a new version, registered it, and validated its predictions against the current champion. Now promote:

```python
client = MlflowClient()
MODEL_NAME = "my_catalog.my_schema.grocery_forecaster"

# Get current state
model = client.get_registered_model(MODEL_NAME)
old_champion = model.aliases.get("champion")
new_champion = model.aliases.get("challenger")

if new_champion is None:
    raise RuntimeError("No @challenger set — nothing to promote")

# Move the alias (atomic — downstream loaders see the switch on next load)
client.set_registered_model_alias(MODEL_NAME, "champion", new_champion)

# Optional: archive the old champion version with a custom alias
if old_champion:
    client.set_registered_model_alias(MODEL_NAME, f"archived_{old_champion}", old_champion)

# Remove the @challenger alias
client.delete_registered_model_alias(MODEL_NAME, "challenger")

print(f"Promoted v{new_champion} from @challenger to @champion (was v{old_champion})")
```

**Rollback** is the inverse — move `@champion` back to the previous version.

---

## Pattern 6: List all model versions

Useful for lineage inspection or cleanup.

```sql
SHOW MODEL VERSIONS ON MODEL my_catalog.my_schema.grocery_forecaster;
```

Or via Python:
```python
from mlflow import MlflowClient
client = MlflowClient()

versions = client.search_model_versions(
    filter_string=f"name='my_catalog.my_schema.grocery_forecaster'",
    order_by=["version_number DESC"],
)
for v in versions:
    print(f"v{v.version}: run_id={v.run_id}, status={v.status}, aliases={v.aliases}")
```

---

## Pattern 7: Tags — richer metadata without new versions

Tags are key-value metadata on the registered model (or a specific version). Useful for:
- Team ownership: `set_model_version_tag(name, "1", "team", "forecasting")`
- Dataset provenance: `set_model_version_tag(name, "1", "dataset_version", "2024-Q4")`
- Review status: `set_model_version_tag(name, "1", "reviewed", "true")`

```python
from mlflow import MlflowClient
client = MlflowClient()

# Tag on the registered model (applies to all versions)
client.set_registered_model_tag(
    name="my_catalog.my_schema.grocery_forecaster",
    key="domain",
    value="retail",
)

# Tag on a specific version
client.set_model_version_tag(
    name="my_catalog.my_schema.grocery_forecaster",
    version="3",
    key="reviewed_by",
    value="jane@company.com",
)
```

Tags are queryable via `search_model_versions(filter_string="tags.reviewed = 'true'")`.

---

## Permission requirements

| Operation | Permission needed | Granted via |
|-----------|-------------------|-------------|
| `register_model` (first version of a model) | `CREATE MODEL ON SCHEMA <schema>` | `GRANT CREATE MODEL ON SCHEMA ... TO ...` |
| `register_model` (new version of existing) | `EDIT ON MODEL <model>` | Automatic for model owner; otherwise grant |
| `set_registered_model_alias` | `EDIT ON MODEL <model>` | Same as above |
| `get_registered_model` / `DESCRIBE MODEL` | `USE CATALOG` + `USE SCHEMA` + `EXECUTE ON MODEL` | Standard read grants |
| `load_model` | `EXECUTE ON MODEL <model>` | `GRANT EXECUTE ON MODEL ... TO ...` |

If any of these fail, request the specific grant from the schema owner. See `GOTCHAS.md` #7.
