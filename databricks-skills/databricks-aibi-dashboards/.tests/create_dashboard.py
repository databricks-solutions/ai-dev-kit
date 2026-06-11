"""
Create the example dashboard in the workspace from the saved JSON.

Pairs with `generate_test_data.py` (which seeds the support_cases table).
Run that first, then this script:

    pip install "databricks-sdk>=0.30"
    python create_dashboard.py

Env vars (all optional, same defaults as generate_test_data.py):
    TEST_CATALOG   default: main
    TEST_SCHEMA    default: dashboard_skill_test
    DASHBOARD_NAME default: "Dashboard skill — example (Support Operations)"
    DASHBOARD_PARENT_PATH  default: /Users/<your_email>   (workspace home)

Behavior: if a dashboard with the same name already exists in the parent
folder, it is updated in place (same dashboard_id). Otherwise a new one is
created. Either way the URL is printed at the end.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import Dashboard

CATALOG = os.environ.get("TEST_CATALOG", "main")
SCHEMA = os.environ.get("TEST_SCHEMA", "dashboard_skill_test")
DASHBOARD_NAME = os.environ.get(
    "DASHBOARD_NAME", "Dashboard skill — example (Support Operations)"
)

JSON_PATH = Path(__file__).parent / "dashboard.lvdash.json"


def main() -> None:
    if not JSON_PATH.exists():
        sys.exit(f"Missing dashboard JSON: {JSON_PATH}")

    with JSON_PATH.open() as f:
        spec = json.load(f)

    # Datasets in the saved JSON use bare `FROM support_cases`. Prefix with the
    # catalog/schema the data-gen script writes to, so the dashboard binds to
    # the real test table.
    bare = "FROM support_cases"
    qualified = f"FROM {CATALOG}.{SCHEMA}.support_cases"
    n_replacements = 0
    for ds in spec.get("datasets", []):
        for i, line in enumerate(ds.get("queryLines", [])):
            if bare in line:
                ds["queryLines"][i] = line.replace(bare, qualified)
                n_replacements += 1
    print(f"Prefixed {n_replacements} `FROM support_cases` references → {qualified}")

    serialized = json.dumps(spec)

    w = WorkspaceClient()
    me = w.current_user.me().user_name
    parent_path = os.environ.get("DASHBOARD_PARENT_PATH", f"/Users/{me}")

    # Look for a previous run by reading a sidecar id file (avoids `lakeview.list()`,
    # which paginates over every dashboard the user can see and is painfully slow on
    # large workspaces like field-eng).
    id_file = Path(__file__).parent / ".dashboard_id"
    existing_id: str | None = None
    if id_file.exists():
        candidate = id_file.read_text().strip()
        try:
            w.lakeview.get(candidate)  # verify it still exists
            existing_id = candidate
        except Exception:
            existing_id = None  # stale id, fall through to create

    if existing_id:
        print(f"Updating existing dashboard {existing_id}...")
        updated = w.lakeview.update(
            dashboard_id=existing_id,
            dashboard=Dashboard(
                display_name=DASHBOARD_NAME,
                serialized_dashboard=serialized,
            ),
        )
        dashboard_id = updated.dashboard_id
    else:
        print(f"Creating new dashboard in {parent_path}...")
        created = w.lakeview.create(
            dashboard=Dashboard(
                display_name=DASHBOARD_NAME,
                parent_path=parent_path,
                serialized_dashboard=serialized,
            )
        )
        dashboard_id = created.dashboard_id

    # Publish so it's openable via the v3 dashboard URL.
    try:
        w.lakeview.publish(dashboard_id=dashboard_id)
    except Exception as e:
        # Publishing is best-effort — if the workspace is configured to require
        # manual publish, just report it instead of failing the whole run.
        print(f"  (publish skipped: {e})")

    id_file.write_text(dashboard_id)
    host = w.config.host.rstrip("/")
    print()
    print("Done.")
    print(f"  Dashboard ID: {dashboard_id}")
    print(f"  URL:          {host}/dashboardsv3/{dashboard_id}")


if __name__ == "__main__":
    main()
