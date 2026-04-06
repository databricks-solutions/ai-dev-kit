---
name: databricks-repos
description: "Manage Databricks Git repositories. Use when cloning repos into the workspace, switching branches, syncing with remote, listing repos, or deleting repo checkouts."
---

# Databricks Repos

Manage Git repositories cloned into the Databricks workspace.

## Overview

Databricks Repos lets you clone Git repositories into the workspace, switch branches or tags, and keep code in sync with the remote. Repos appear under `/Repos/{user}/{repo-name}` and can contain notebooks, Python modules, and other files that are version-controlled externally.

## When to Use This Skill

Use this skill when:
- Cloning a Git repository into the workspace
- Switching branches or tags on an existing repo
- Listing repos to find what's already cloned
- Cleaning up old repo checkouts
- Setting up a development workflow with Git-backed notebooks

## MCP Tools

| Tool | Actions | Purpose |
|------|---------|---------|
| `manage_repos` | list, get, create, update, sync, delete | Full lifecycle management of Git repos in the workspace |

### Actions

| Action | Required Params | Optional Params | Description |
|--------|----------------|-----------------|-------------|
| `list` | — | `path_prefix` | List all cloned repos, optionally filtered by path prefix |
| `get` | `repo_id` | — | Get repo details (path, URL, branch, commit) |
| `create` | `url`, `provider` | `path` | Idempotent clone (returns existing if same URL already cloned) |
| `update` | `repo_id` | `branch`, `tag` | Switch to a different branch or tag |
| `sync` | `repo_id` | `branch`, `tag` | Alias for update — pull latest and checkout ref |
| `delete` | `repo_id` | — | Remove a repo from the workspace |

## Quick Start

### 1. Clone a Repository

```python
manage_repos(
    action="create",
    url="https://github.com/databricks/databricks-sdk-py",
    provider="gitHub"
)
# {"id": 123, "path": "/Repos/user/databricks-sdk-py", "branch": "main", "created": true}
```

### 2. List Your Repos

```python
manage_repos(action="list", path_prefix="/Repos/user@example.com")
# {"repos": [{"id": 123, "path": "...", "branch": "main", ...}], "count": 3}
```

### 3. Switch Branch

```python
manage_repos(action="update", repo_id=123, branch="develop")
# {"id": 123, "branch": "develop", "head_commit_id": "abc123..."}
```

### 4. Sync to Latest

```python
manage_repos(action="sync", repo_id=123, branch="main")
# {"id": 123, "branch": "main", "head_commit_id": "latest..."}
```

### 5. Delete a Repo

```python
manage_repos(action="delete", repo_id=123)
# {"repo_id": 123, "status": "deleted"}
```

## Common Patterns

### Clone and Switch to a Feature Branch

```python
# Clone the repo (idempotent — safe to call if already cloned)
result = manage_repos(
    action="create",
    url="https://github.com/my-org/ml-pipeline",
    provider="gitHub"
)

# Switch to the feature branch
manage_repos(action="update", repo_id=result["id"], branch="feature/new-model")
```

### Check Out a Specific Tag

```python
manage_repos(action="update", repo_id=123, tag="v2.1.0")
# {"id": 123, "branch": null, "head_commit_id": "..."}
```

### Find a Repo by Path

```python
# List all repos for a user
repos = manage_repos(action="list", path_prefix="/Repos/user@example.com")

# Filter results to find a specific repo
# Each repo has: id, path, url, provider, branch, head_commit_id
```

### Custom Workspace Path

```python
manage_repos(
    action="create",
    url="https://github.com/my-org/shared-utils",
    provider="gitHub",
    path="/Repos/user@example.com/custom-name"
)
```

### Cleanup Old Repos

```python
# List repos to review
repos = manage_repos(action="list", path_prefix="/Repos/user@example.com")

# Delete repos no longer needed
manage_repos(action="delete", repo_id=456)
```

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Git Providers | [git-providers.md](git-providers.md) | Supported Git providers, credential setup, and URL formats |

## Common Issues

| Issue | Solution |
|-------|----------|
| **Clone fails with auth error** | Git credentials must be configured in User Settings -> Git Integration |
| **Repo already exists** | `create` action is idempotent — returns the existing repo with `created: false` |
| **Branch not found** | Verify the branch exists on the remote. Use the exact branch name (case-sensitive) |
| **Cannot delete repo** | You need MANAGE permission on the repo. Check workspace ACLs |
| **Repo not syncing** | Use `sync` action with the branch name to pull latest from remote |

## Related Skills

- **[databricks-workspace](../databricks-workspace/SKILL.md)** - Browse workspace objects including repo contents
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - Run notebooks from repos as job tasks
- **[databricks-bundles](../databricks-bundles/SKILL.md)** - Deploy code via Asset Bundles (alternative to Repos for CI/CD)
