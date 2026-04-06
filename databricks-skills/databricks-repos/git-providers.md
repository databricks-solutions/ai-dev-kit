# Git Providers Reference

## Supported Providers

Databricks Repos supports these Git providers. Use the exact `provider` string when calling `create_or_update_repo`.

| Provider | `provider` Value | URL Format |
|----------|-----------------|------------|
| GitHub | `gitHub` | `https://github.com/{org}/{repo}` |
| GitHub Enterprise | `gitHubEnterprise` | `https://{host}/{org}/{repo}` |
| GitLab | `gitLab` | `https://gitlab.com/{group}/{repo}` |
| GitLab Enterprise | `gitLabEnterpriseEdition` | `https://{host}/{group}/{repo}` |
| Azure DevOps | `azureDevOpsServices` | `https://dev.azure.com/{org}/{project}/_git/{repo}` |
| Bitbucket Cloud | `bitbucketCloud` | `https://bitbucket.org/{workspace}/{repo}` |
| Bitbucket Server | `bitbucketServer` | `https://{host}/scm/{project}/{repo}.git` |
| AWS CodeCommit | `awsCodeCommit` | `https://git-codecommit.{region}.amazonaws.com/v1/repos/{repo}` |

## Credential Setup

Git credentials are configured per user in **User Settings → Git Integration** (or via the Git Credentials API).

### Personal Access Tokens

Most providers use personal access tokens (PATs):

| Provider | Token Scope Required |
|----------|---------------------|
| GitHub | `repo` (full control of private repos) |
| GitLab | `read_repository`, `write_repository` |
| Azure DevOps | `Code (Read & Write)` |
| Bitbucket Cloud | `Repositories (Read/Write)` |

### Token Configuration

Tokens are configured once per workspace user, either through:

1. **UI**: User Settings → Git Integration → Add credential
2. **API**: Git Credentials REST API

Once configured, all `create_or_update_repo` and `update_repo` calls use the stored credential automatically.

## URL Formats

### HTTPS vs SSH

Databricks Repos supports **HTTPS URLs only**. SSH URLs (`git@github.com:...`) are not supported.

```
# Correct
https://github.com/my-org/my-repo

# Incorrect (SSH not supported)
git@github.com:my-org/my-repo.git
```

### URL Normalization

- Trailing `.git` is optional: `https://github.com/org/repo` and `https://github.com/org/repo.git` both work
- URLs are case-sensitive for the path portion
- Do not include authentication tokens in the URL

## Default Workspace Path

When `path` is omitted from `create_or_update_repo`, the repo is cloned to:

```
/Repos/{current_user}/{repo_name}
```

Where `{repo_name}` is extracted from the URL (last path segment, without `.git`).

## Branch and Tag Behavior

- **Default branch**: When cloning, the repo checks out the default branch (usually `main` or `master`)
- **Switching branches**: `update_repo(repo_id, branch="...")` pulls latest and checks out the branch
- **Tags**: `update_repo(repo_id, tag="v1.0")` checks out the tag (detached HEAD — `branch` returns `null`)
- **One ref at a time**: Provide either `branch` or `tag` to `update_repo`, not both

## Limitations

| Limitation | Details |
|------------|---------|
| Max repo size | 10 GB |
| Max file size | 500 MB |
| Submodules | Not supported |
| LFS | Supported (files up to 500 MB) |
| Sparse checkout | Not supported |
| Commit/push from workspace | Not supported via Repos API (use Git directly) |
