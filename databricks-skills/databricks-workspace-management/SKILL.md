---
name: databricks-workspace-management
description: "Manage Databricks workspace resources: users, groups, service principals, permissions, clusters, and warehouses. Use when administering workspace access, setting up RBAC, managing compute resources, or troubleshooting permission issues."
---

# Databricks Workspace Management

Administer workspace-level resources — users, groups, service principals, permissions, and compute — using the Databricks SDK and REST API.

## When to Use

- Adding or managing users and groups
- Creating and configuring service principals
- Setting up role-based access control (RBAC)
- Managing permissions on clusters, warehouses, jobs, and other resources
- Listing and monitoring compute resources
- Troubleshooting access and permission issues

## Quick Start

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Who am I?
me = w.current_user.me()
print(f"User: {me.user_name}, ID: {me.id}")

# List SQL warehouses
for wh in w.warehouses.list():
    print(f"  {wh.name}: {wh.state}")
```

## Common Patterns

### Pattern 1: User Management

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Get current user
me = w.current_user.me()

# Get a specific user by ID
user = w.users.get(id=me.id)
print(f"User: {user.user_name}, active: {user.active}")

# Create a new user
new_user = w.users.create(
    user_name="new.user@company.com",
    display_name="New User",
    active=True
)
```

**Note:** On large workspaces, `list(w.users.list())` paginates through all users and can be very slow. Use the REST API with `count` and `startIndex` for paginated listing:

```python
response = w.api_client.do(
    "GET", "/api/2.0/preview/scim/v2/Users",
    query={"count": 10, "startIndex": 1}
)
total = response.get("totalResults")
users = response.get("Resources", [])
```

### Pattern 2: Group Management

```python
# List groups (paginated for large workspaces)
response = w.api_client.do(
    "GET", "/api/2.0/preview/scim/v2/Groups",
    query={"count": 10, "startIndex": 1}
)
print(f"Total groups: {response.get('totalResults')}")
for g in response.get("Resources", []):
    print(f"  {g.get('displayName')}")

# Create a group
group = w.groups.create(display_name="data-engineers")

# Add user to group
w.groups.patch(
    id=group.id,
    operations=[{
        "op": "add",
        "path": "members",
        "value": [{"value": user.id}]
    }]
)
```

### Pattern 3: Service Principal Management

```python
# List service principals (paginated)
response = w.api_client.do(
    "GET", "/api/2.0/preview/scim/v2/ServicePrincipals",
    query={"count": 10, "startIndex": 1}
)
print(f"Total SPs: {response.get('totalResults')}")

# Create a service principal
sp = w.service_principals.create(
    display_name="my-etl-pipeline",
    active=True
)
print(f"SP ID: {sp.id}, Application ID: {sp.application_id}")
```

### Pattern 4: Permission Management

Permissions use a consistent API across resource types:

```python
# Get permissions on a SQL warehouse
perms = w.permissions.get(
    request_object_type="sql/warehouses",
    request_object_id="<warehouse-id>"
)
for acl in perms.access_control_list:
    name = acl.user_name or acl.group_name or acl.service_principal_name
    levels = [p.permission_level.value for p in acl.all_permissions]
    print(f"  {name}: {levels}")

# Set permissions
w.permissions.set(
    request_object_type="sql/warehouses",
    request_object_id="<warehouse-id>",
    access_control_list=[{
        "group_name": "data-engineers",
        "permission_level": "CAN_USE"
    }]
)
```

**Resource types for permissions:**

| Resource | `request_object_type` |
|----------|----------------------|
| Cluster | `clusters` |
| SQL Warehouse | `sql/warehouses` |
| Job | `jobs` |
| Notebook | `notebooks` |
| Directory | `directories` |
| MLflow Experiment | `experiments` |
| MLflow Model | `registered-models` |
| Serving Endpoint | `serving-endpoints` |
| Dashboard | `sql/dashboards` |
| Alert | `sql/alerts` |

**Permission levels:**

| Level | Description |
|-------|-------------|
| `CAN_VIEW` | Read-only access |
| `CAN_USE` | Can use the resource (warehouses) |
| `CAN_MANAGE` | Full control |
| `CAN_RUN` | Can run (jobs, notebooks) |
| `CAN_EDIT` | Can modify |
| `IS_OWNER` | Owner (full control + transfer) |

### Pattern 5: Compute Resource Listing

```python
# List clusters
clusters = list(w.clusters.list())
running = [c for c in clusters if str(c.state) == "State.RUNNING"]
print(f"Total: {len(clusters)}, Running: {len(running)}")

# List SQL warehouses
for wh in w.warehouses.list():
    print(f"  {wh.name}: {wh.state} (size={wh.cluster_size})")
```

## CLI Reference

```bash
# Users
databricks users list
databricks users get <user-id>
databricks users create --json '{"user_name": "user@company.com"}'

# Groups
databricks groups list
databricks groups create --json '{"displayName": "my-group"}'

# Service Principals
databricks service-principals list
databricks service-principals create --json '{"display_name": "my-sp"}'

# Permissions
databricks permissions get sql/warehouses <warehouse-id>
databricks permissions set sql/warehouses <warehouse-id> --json '...'

# Clusters
databricks clusters list
databricks clusters get <cluster-id>

# Warehouses
databricks warehouses list
databricks warehouses get <warehouse-id>
```

## Common Issues

| Issue | Solution |
|-------|----------|
| **`list(w.users.list())` hangs** | Use REST API with `count` param for pagination on large workspaces |
| **`PERMISSION_DENIED`** | Check if user has workspace admin or appropriate object-level permissions |
| **Can't find service principal** | SPs have both `id` (SCIM ID) and `application_id` (client ID) — use the right one |
| **Permission not taking effect** | Permissions are eventually consistent — wait a few seconds and retry |
| **Can't set `IS_OWNER`** | Owner is set at creation time or transferred, not granted via permissions API |
| **Group membership not visible** | Use SCIM API directly: `GET /api/2.0/preview/scim/v2/Groups/<id>` |
