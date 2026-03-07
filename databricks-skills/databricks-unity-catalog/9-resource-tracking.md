# Resource Tracking

Reference for the MCP resource tracking system: listing, auditing, and cleaning up Databricks resources created during sessions.

## Overview

The MCP server maintains a **project manifest** that automatically records every resource it creates — dashboards, jobs, pipelines, Genie spaces, Knowledge Assistants, Multi-Agent Supervisors, catalogs, schemas, volumes, apps, Lakebase instances, Vector Search endpoints/indexes, and metric views. This manifest persists across sessions, giving you a single inventory of everything the MCP server has provisioned.

**Why it matters:**
- **Demo/POC cleanup** — After building a customer demo, list everything that was created and tear it down in one pass
- **Cost control** — Forgotten jobs and pipelines keep running; the manifest surfaces them
- **Workspace hygiene** — Prevents orphaned resources from accumulating across sessions
- **Audit trail** — Timestamps show when each resource was created and last updated

---

## Tracked Resource Types

| Type | `type` filter value | Example ID format |
|------|---------------------|-------------------|
| Dashboard | `dashboard` | `01f116b258841849b6be19b153889f5d` |
| Job | `job` | Numeric job ID |
| Pipeline | `pipeline` | Pipeline ID |
| Genie Space | `genie_space` | `01f116b25cb61b919a9efa192d5a96e4` |
| Knowledge Assistant | `knowledge_assistant` | KA ID |
| Multi-Agent Supervisor | `multi_agent_supervisor` | MAS ID |
| Catalog | `catalog` | Catalog name (e.g. `lakemeter_catalog`) |
| Schema | `schema` | Two-level name (e.g. `catalog.schema`) |
| Volume | `volume` | Three-level name (e.g. `catalog.schema.volume`) |
| App | `app` | App name string |
| Lakebase Instance | `lakebase_instance` | Instance name |
| Lakebase Project | `lakebase_project` | Project name |
| VS Endpoint | `vs_endpoint` | Endpoint name |
| VS Index | `vs_index` | Index name |
| Metric View | `metric_view` | Three-level name (e.g. `catalog.schema.view`) |

> **Note:** The `list_tracked_resources` tool's `type` filter officially documents 9 types (dashboard through volume above). The additional types (app, lakebase_instance, lakebase_project, vs_endpoint, vs_index, metric_view) are tracked in the manifest and can be filtered, but are not listed in the tool's schema description.

---

## MCP Tools

### list_tracked_resources

List all resources in the project manifest, optionally filtered by type.

```python
# List everything
list_tracked_resources()

# Filter by type
list_tracked_resources(type="dashboard")
list_tracked_resources(type="volume")
list_tracked_resources(type="genie_space")
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `type` | string \| null | No | `null` | Filter by resource type. One of: `dashboard`, `job`, `pipeline`, `genie_space`, `knowledge_assistant`, `multi_agent_supervisor`, `catalog`, `schema`, `volume`. Omit to return all. |

**Response format:**

```json
{
  "resources": [
    {
      "type": "dashboard",
      "name": "Maya Bank - Executive Dashboard",
      "id": "01f116b258841849b6be19b153889f5d",
      "created_at": "2026-03-03T01:53:28.806733+00:00",
      "updated_at": "2026-03-03T03:37:47.790086+00:00",
      "url": "https://workspace.cloud.databricks.com/sql/dashboardsv3/01f116b258841849b6be19b153889f5d"
    }
  ],
  "count": 1
}
```

**Resource fields:**

| Field | Always present | Description |
|-------|---------------|-------------|
| `type` | Yes | Resource type string |
| `name` | Yes | Human-readable name |
| `id` | Yes | Resource identifier (format varies by type) |
| `created_at` | Yes | ISO 8601 timestamp of creation |
| `updated_at` | Yes | ISO 8601 timestamp of last update |
| `url` | No | Direct link to the resource (dashboards only) |

When the filter matches nothing, returns `{"resources": [], "count": 0}`.

---

### delete_tracked_resource

Remove a resource from the manifest, and optionally delete it from Databricks.

```python
# Remove from manifest only (safe — resource still exists in Databricks)
delete_tracked_resource(
    type="dashboard",
    resource_id="01f116b258841849b6be19b153889f5d"
)

# Remove from manifest AND delete from Databricks
delete_tracked_resource(
    type="dashboard",
    resource_id="01f116b258841849b6be19b153889f5d",
    delete_from_databricks=True
)
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `type` | string | Yes | — | Resource type (e.g. `dashboard`, `job`, `volume`) |
| `resource_id` | string | Yes | — | The resource ID as shown in `list_tracked_resources` |
| `delete_from_databricks` | boolean | No | `false` | If `true`, deletes the actual resource from Databricks before removing the manifest entry |

**Response format (success):**

```json
{
  "success": true,
  "removed_from_manifest": true,
  "deleted_from_databricks": false,
  "error": null
}
```

**Response format (not found in manifest, default `delete_from_databricks=false`):**

```json
{
  "success": false,
  "removed_from_manifest": false,
  "deleted_from_databricks": false,
  "error": "Resource job/nonexistent-12345 not found in manifest"
}
```

**Response fields:**

| Field | Description |
|-------|-------------|
| `success` | `true` if the operation completed without error |
| `removed_from_manifest` | `true` if the entry was found and removed from the manifest |
| `deleted_from_databricks` | `true` if the resource was also deleted from the workspace |
| `error` | Error message string, or `null` on success |

---

## Workflows

### Post-Demo Cleanup

After a customer demo, clean up all resources that were created:

```
1. list_tracked_resources()                          # See everything
2. Review the list — decide what to keep vs. remove
3. delete_tracked_resource(                           # Delete each unwanted resource
       type="dashboard",
       resource_id="...",
       delete_from_databricks=True
   )
4. list_tracked_resources()                          # Confirm cleanup is complete
```

### Targeted Cleanup by Type

Clean up only a specific resource category:

```
1. list_tracked_resources(type="genie_space")        # Find all Genie spaces
2. delete_tracked_resource(                           # Remove each one
       type="genie_space",
       resource_id="...",
       delete_from_databricks=True
   )
```

### Manifest-Only Removal

If a resource was already deleted manually (e.g. via the Databricks UI), remove the stale manifest entry without attempting a Databricks deletion:

```
delete_tracked_resource(
    type="volume",
    resource_id="catalog.schema.volume",
    delete_from_databricks=False                     # Default — manifest only
)
```

### Audit Before Workspace Handoff

Before handing a workspace to a customer or colleague, review what you've created:

```
1. list_tracked_resources()                          # Full inventory
2. Note resources with old created_at timestamps     # Identify stale items
3. Clean up or document as needed
```

---

## Behavior Notes

- **Automatic tracking** — Resources are added to the manifest when created through MCP tools. No manual registration is needed.
- **Persistence** — The manifest is stored in `.databricks-resources.json` in the project root (CWD where the MCP server was launched). It survives across sessions — resources created last week still appear.
- **Safe defaults** — `delete_from_databricks` defaults to `false`, so a delete call only touches the manifest unless you explicitly opt in.
- **No type validation on delete** — Passing an unrecognized type to `delete_tracked_resource` returns a "not found" error rather than a type validation error.
- **Manifest removal on Databricks failure** — When `delete_from_databricks=True` is set but the Databricks API call fails, the manifest entry is still removed. The response will show `success=false` with an error message, but `removed_from_manifest=true`.
- **Databricks deletion support** — `delete_from_databricks=True` is supported for: dashboard, job, pipeline, genie_space, knowledge_assistant, multi_agent_supervisor, catalog, schema, volume, app. It is **not** supported for: lakebase_instance, lakebase_project, vs_endpoint, vs_index, metric_view — these return "Unsupported resource type for deletion".
- **Upsert on create** — If you recreate a resource with the same name, the manifest updates the existing entry's ID rather than creating a duplicate. Matching is by type+id first, then type+name.
- **Idempotent list** — Calling `list_tracked_resources` multiple times returns the same results; it has no side effects.
- **URL field** — Only dashboards include a `url` field in the manifest. All other resource types omit it.
- **ID format varies** — Dashboards and Genie spaces use hex IDs; catalogs use their name; schemas use dot-separated two-level names (`catalog.schema`); volumes use three-level names (`catalog.schema.volume`).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Resource exists in Databricks but not in manifest | Created outside MCP (UI, CLI, SDK) | Not tracked — manage manually |
| Manifest entry exists but resource is gone | Deleted via UI/CLI without updating manifest | `delete_tracked_resource(..., delete_from_databricks=False)` to clean up the stale entry |
| `delete_from_databricks=True` fails | Permissions, resource already deleted, or API error | Check the `error` field; fall back to manifest-only removal |
| `delete_from_databricks=True` returns "Unsupported resource type" | Resource type has no registered deleter (e.g. vs_endpoint, lakebase_instance) | Use `delete_from_databricks=False` for manifest-only removal; delete the resource manually |
| Empty list after creating resources | Resources created in a different project/workspace context | Verify you're connected to the correct workspace |

---

## Verified Against Live Workspace

| Tool | Input | Result | Status |
|------|-------|--------|--------|
| `list_tracked_resources` | _(none)_ | Returned 5 resources (catalog, volumes, dashboard, genie_space) | Tested |
| `list_tracked_resources` | `type="dashboard"` | Filtered correctly to dashboard resources only | Tested |
| `list_tracked_resources` | `type="volume"` | Filtered correctly to volume resources only | Tested |
| `delete_tracked_resource` | `type="job"`, `resource_id="nonexistent-12345"` | Graceful error: "not found in manifest"; no corruption | Tested |

### Verified Against Source Code

| Claim | Source file | Verdict |
|-------|------------|---------|
| Response fields: type, name, id, created_at, updated_at, url | `manifest.py` lines 137-145 | Confirmed — `url` only set when caller provides it |
| Only dashboards include `url` | All `track_resource()` call sites | Confirmed — only `aibi_dashboards.py` passes `url=` |
| `delete_from_databricks` defaults to `false` | `manifest.py` tool definition, line 62 | Confirmed |
| Manifest entry removed even when Databricks deletion fails | `manifest.py` lines 90-101 | Confirmed — comment on line 96 |
| Invalid type filter returns empty list, not error | `manifest.py` `list_resources()` lines 174-180 | Confirmed — simple filter, no validation |
| 15 resource types tracked (9 documented + 6 additional) | All `track_resource()` call sites | Confirmed |
| 10 types support `delete_from_databricks=True` | All `register_deleter()` call sites | Confirmed |
| Manifest stored in `.databricks-resources.json` | `manifest.py` line 40 | Confirmed |
