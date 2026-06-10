# Dashboard skill — manual verification harness

This folder hosts a Databricks-Connect script that seeds the test data the
worked example in `../4-examples.md` queries from. The point is to be able
to actually render the example dashboard end-to-end and visually confirm
the skill produces a state-of-the-art result.

## Quick start

```bash
pip install "databricks-connect>=15.0"

# uses your default Databricks auth (env vars or ~/.databrickscfg)
python generate_test_data.py
```

Defaults: writes `main.dashboard_skill_test.support_cases` with 5000 rows.
Override via `TEST_CATALOG`, `TEST_SCHEMA`, `TEST_TABLE`, `NUM_CASES`.

The script prints the next-step commands to create the dashboard against
the generated table.

## Why this isn't a pytest

This is intentionally a one-shot script, not an automated test:

- The point is **human visual verification** of the rendered dashboard
  (theme coherence, layout, color semantics) — those judgments don't
  belong in CI.
- The dataset takes ~10s to write and is meant to be inspected once per
  meaningful change to `4-examples.md`.
