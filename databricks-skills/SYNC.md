# Sync from databricks-agent-skills

The [`databricks-skills/imported/`](./imported/) directory is kept in sync with
[`databricks/databricks-agent-skills`](https://github.com/databricks/databricks-agent-skills)
`experimental/` via `git subtree`.

## Mechanism

- **`databricks-agent-skills`** publishes a branch named `experimental-only`
  whose root tree is the contents of `experimental/`. The d-a-s repo runs
  `git subtree split --prefix=experimental --branch=experimental-only` after
  each push to `main` (workflow on that side).
- **This repo** runs
  [`.github/workflows/sync-skills-from-das.yml`](../.github/workflows/sync-skills-from-das.yml)
  weekly (and on manual dispatch). It calls `git subtree pull` from
  `experimental-only` into `databricks-skills/imported/` and opens a PR if
  there is drift.

## Do not edit `imported/` here

Files under `databricks-skills/imported/` are upstream-owned. Local edits will
be overwritten on the next sync. To change an imported skill, open a PR
against [`databricks/databricks-agent-skills`](https://github.com/databricks/databricks-agent-skills)
under `experimental/<skill>/`. The next sync will bring your change back here.

Skills under `databricks-skills/*` that are **not** in `imported/` (the legacy
top-level skills) remain a-d-k-owned and can be edited freely. Over time these
should also migrate upstream — see the PR introducing the sync mechanism.

## Manual sync (if you need it sooner than the cron)

```bash
git subtree pull \
  --prefix=databricks-skills/imported \
  https://github.com/databricks/databricks-agent-skills \
  experimental-only --squash
```

Then push the result via PR as usual.

## First-time setup (already done in PR introducing this file)

```bash
git subtree add \
  --prefix=databricks-skills/imported \
  https://github.com/databricks/databricks-agent-skills \
  experimental-only --squash
```

## Why `git subtree` over alternatives

- **vs `git submodule`** — subtree keeps files in the working tree, so
  `install_skills.sh` and end users see the skills directly without
  `git submodule update`. Submodules also can't reference a subdirectory of
  the target repo, so wouldn't work for this case anyway.
- **vs `rsync` / `cp` in a workflow** — subtree records each sync as a
  squashed merge commit referencing the upstream SHA. `git log --grep
  "Squashed 'databricks-skills/imported/'"` shows the full sync history;
  you can `git blame` an imported skill back to its upstream commit.
- **vs hard fork** — subtree pulls are automated and visible in CI; a fork
  would diverge silently.

## Known limitations

- `git subtree pull --squash` produces a merge commit and a squash commit on
  every sync, even when there is no drift. The auto-PR step short-circuits
  in that case so no noise reaches reviewers.
- The `experimental-only` branch on d-a-s is force-pushed by the split
  workflow. Subtree handles this because each pull is squashed against the
  prior squash commit; there is no shared linear history to preserve.
