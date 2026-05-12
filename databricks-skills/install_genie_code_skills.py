# Databricks notebook source
# MAGIC %md
# MAGIC # Install Genie Code Skills
# MAGIC
# MAGIC This notebook downloads AI Dev Kit skills from GitHub and uploads them to your workspace so Genie Code can use them.
# MAGIC
# MAGIC Skills are installed to `/Workspace/Users/<your_username>/.assistant/skills/`.
# MAGIC
# MAGIC **How to use:** Run all cells top to bottom. Edit the configuration cell below if you want to install a subset of skills.
# MAGIC
# MAGIC Skills are auto-discovered from GitHub — no hardcoded lists to maintain.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration
# MAGIC
# MAGIC By default, all skills are installed. To install only specific skills, replace `INSTALL_SKILLS` with a list of skill names.

# COMMAND ----------

# -- Configuration ----------------------------------------------------------
# Set to "all" to install everything, or provide a list of specific skill names.
INSTALL_SKILLS = "all"

# Examples:
# INSTALL_SKILLS = "all"
# INSTALL_SKILLS = ["databricks-dbsql", "databricks-jobs", "databricks-unity-catalog"]
# INSTALL_SKILLS = ["databricks-agent-bricks", "agent-evaluation"]

# Source branch or tag (change to pin a specific release)
GITHUB_REF = "main"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Install Skills

# COMMAND ----------

import urllib.request
import json
import posixpath
import base64
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat

# ── Skill sources ──────────────────────────────────────────────────────────
# Skills are auto-discovered: any subdirectory containing SKILL.md is a skill.

SKILL_SOURCES = [
    {"owner": "databricks-solutions", "repo": "ai-dev-kit", "path": "databricks-skills",
     "skip": {"TEMPLATE"}},
    {"owner": "mlflow",               "repo": "skills",      "path": ""},
    {"owner": "databricks-solutions", "repo": "apx",         "path": "skills",
     "name_overrides": {"apx": "databricks-app-apx"}},
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _github_api(url):
    """Fetch JSON from the GitHub API."""
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  WARN GitHub API error: {e}")
        return None


def _download(url):
    """Download raw file bytes. Returns bytes on success, None on failure."""
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read()
    except Exception:
        return None


def _upload(w, workspace_path, content):
    """Upload a file to the Databricks workspace."""
    w.workspace.mkdirs(posixpath.dirname(workspace_path))
    w.workspace.import_(
        path=workspace_path,
        content=base64.b64encode(content).decode(),
        format=ImportFormat.AUTO,
        overwrite=True,
    )


def _discover_from_source(source, ref):
    """Discover skills in a GitHub repo using the Git Trees API.

    Returns list of (install_name, raw_url_prefix, [extra_file_paths]).
    """
    owner, repo = source["owner"], source["repo"]
    base_path = source["path"]
    overrides = source.get("name_overrides", {})
    skip = source.get("skip", set())

    data = _github_api(
        f"https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
    )
    if data is None:
        return []

    all_files = {item["path"] for item in data.get("tree", []) if item["type"] == "blob"}
    prefix = f"{base_path}/" if base_path else ""

    # Find directories that directly contain SKILL.md
    skill_dirs = set()
    for f in all_files:
        if not f.startswith(prefix):
            continue
        rel = f[len(prefix):]
        parts = rel.split("/")
        if len(parts) == 2 and parts[1] == "SKILL.md" and parts[0] not in skip:
            skill_dirs.add(parts[0])

    # Build result with extra files for each skill
    raw_base = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}"
    results = []
    for dir_name in sorted(skill_dirs):
        skill_prefix = f"{prefix}{dir_name}/"
        extras = sorted(
            f[len(skill_prefix):]
            for f in all_files
            if f.startswith(skill_prefix) and not f.endswith("/SKILL.md")
        )
        install_name = overrides.get(dir_name, dir_name)
        source_url = f"{raw_base}/{prefix}{dir_name}"
        results.append((install_name, source_url, extras))

    return results


def _install_skill(w, name, source_url, extras, skills_path):
    """Download and upload one skill (SKILL.md + extra files)."""
    skill_md = _download(f"{source_url}/SKILL.md")
    if skill_md is None:
        print(f"  SKIP {name} (could not download SKILL.md)")
        return False

    dest = f"{skills_path}/{name}"
    _upload(w, f"{dest}/SKILL.md", skill_md)
    uploaded = 1

    for extra in extras:
        data = _download(f"{source_url}/{extra}")
        if data is not None:
            _upload(w, f"{dest}/{extra}", data)
            uploaded += 1

    print(f"  OK   {name} ({uploaded} file{'s' if uploaded != 1 else ''})")
    return True


# ── Main ─────────────────────────────────────────────────────────────────────

w = WorkspaceClient()
username = w.current_user.me().user_name
skills_path = f"/Users/{username}/.assistant/skills"

print(f"Username:  {username}")
print(f"Target:    {skills_path}")
print()

# Discover skills from all sources
print("Discovering skills from GitHub...")
all_skills = []
for source in SKILL_SOURCES:
    discovered = _discover_from_source(source, GITHUB_REF)
    label = f"{source['owner']}/{source['repo']}"
    print(f"  {label}: {len(discovered)} skills")
    all_skills.extend(discovered)

print(f"\nTotal: {len(all_skills)} skills available\n")

# Filter to requested skills
if INSTALL_SKILLS == "all":
    selected = all_skills
else:
    wanted = set(INSTALL_SKILLS)
    selected = [s for s in all_skills if s[0] in wanted]
    missing = wanted - {s[0] for s in selected}
    if missing:
        print(f"  WARN: skills not found in any source: {', '.join(sorted(missing))}\n")

# Install
w.workspace.mkdirs(skills_path)

installed = 0
failed = 0
for name, source_url, extras in selected:
    ok = _install_skill(w, name, source_url, extras, skills_path)
    installed += ok
    failed += not ok

print()
print(f"Done. {installed} installed, {failed} failed.")
print(f"Skills are at: /Workspace{skills_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify Installation
# MAGIC
# MAGIC Run this cell to list the skills installed in your workspace.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
username = w.current_user.me().user_name
skills_path = f"/Users/{username}/.assistant/skills"

try:
    entries = list(w.workspace.list(skills_path))
    subdirs = sorted([
        e.path.split("/")[-1]
        for e in entries
        if str(e.object_type) == "ObjectType.DIRECTORY"
    ])
    if subdirs:
        print(f"Found {len(subdirs)} skills in {skills_path}:\n")
        for name in subdirs:
            print(f"  {name}")
    else:
        print(f"No skills found in {skills_path}.")
except Exception as e:
    print(f"Could not list skills: {e}")
