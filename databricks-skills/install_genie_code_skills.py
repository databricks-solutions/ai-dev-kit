# Databricks notebook source
# MAGIC %md
# MAGIC # Install Genie Code Skills
# MAGIC
# MAGIC This notebook downloads AI Dev Kit skills from GitHub and uploads them to your workspace so Genie Code can use them.
# MAGIC
# MAGIC Skills are installed to `/Workspace/Users/<your_username>/.assistant/skills/`.
# MAGIC
# MAGIC **How to use:** Run all cells top to bottom. Edit the configuration cell below if you want to install a subset of skills.

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
# INSTALL_SKILLS = ["databricks-agent-bricks", "databricks-vector-search"]

# Source branch or tag (change to pin a specific release)
GITHUB_REF = "main"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Install Skills

# COMMAND ----------

import urllib.request
import json
import posixpath
from databricks.sdk import WorkspaceClient

# ── Skill registry (synced with install_skills.sh) ──────────────────────────

REPO_RAW = f"https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/{GITHUB_REF}"
MLFLOW_RAW = f"https://raw.githubusercontent.com/mlflow/skills/{GITHUB_REF}"
APX_RAW = f"https://raw.githubusercontent.com/databricks-solutions/apx/{GITHUB_REF}/skills/apx"

DATABRICKS_SKILLS = [
    "databricks-agent-bricks", "databricks-ai-functions", "databricks-aibi-dashboards",
    "databricks-bundles", "databricks-app-python", "databricks-config", "databricks-dbsql",
    "databricks-docs", "databricks-genie", "databricks-iceberg", "databricks-jobs",
    "databricks-lakebase-autoscale", "databricks-lakebase-provisioned", "databricks-metric-views",
    "databricks-mlflow-evaluation", "databricks-model-serving", "databricks-python-sdk",
    "databricks-execution-compute", "databricks-spark-declarative-pipelines",
    "databricks-spark-structured-streaming", "databricks-synthetic-data-gen",
    "databricks-unity-catalog", "databricks-unstructured-pdf-generation",
    "databricks-vector-search", "databricks-zerobus-ingest", "spark-python-data-source",
]

MLFLOW_SKILLS = [
    "agent-evaluation", "analyze-mlflow-chat-session", "analyze-mlflow-trace",
    "instrumenting-with-mlflow-tracing", "mlflow-onboarding", "querying-mlflow-metrics",
    "retrieving-mlflow-traces", "searching-mlflow-docs",
]

APX_SKILLS = ["databricks-app-apx"]

DATABRICKS_EXTRA_FILES = {
    "databricks-agent-bricks": ["1-knowledge-assistants.md", "2-supervisor-agents.md"],
    "databricks-ai-functions": ["1-task-functions.md", "2-ai-query.md", "3-ai-forecast.md", "4-document-processing-pipeline.md"],
    "databricks-aibi-dashboards": ["widget-reference.md", "sql-patterns.md"],
    "databricks-genie": ["spaces.md", "conversation.md"],
    "databricks-bundles": ["alerts_guidance.md", "SDP_guidance.md"],
    "databricks-iceberg": ["1-managed-iceberg-tables.md", "2-uniform-and-compatibility.md", "3-iceberg-rest-catalog.md", "4-snowflake-interop.md", "5-external-engine-interop.md"],
    "databricks-app-python": ["1-authorization.md", "2-app-resources.md", "3-frameworks.md", "4-deployment.md", "5-lakebase.md", "6-mcp-approach.md", "examples/llm_config.py", "examples/fm-minimal-chat.py", "examples/fm-parallel-calls.py", "examples/fm-structured-outputs.py"],
    "databricks-jobs": ["task-types.md", "triggers-schedules.md", "notifications-monitoring.md", "examples.md"],
    "databricks-python-sdk": ["doc-index.md", "examples/1-authentication.py", "examples/2-clusters-and-jobs.py", "examples/3-sql-and-warehouses.py", "examples/4-unity-catalog.py", "examples/5-serving-and-vector-search.py"],
    "databricks-unity-catalog": ["5-system-tables.md"],
    "databricks-lakebase-autoscale": ["projects.md", "branches.md", "computes.md", "connection-patterns.md", "reverse-etl.md"],
    "databricks-lakebase-provisioned": ["connection-patterns.md", "reverse-etl.md"],
    "databricks-metric-views": ["yaml-reference.md", "patterns.md"],
    "databricks-model-serving": ["1-classical-ml.md", "2-custom-pyfunc.md", "3-genai-agents.md", "4-tools-integration.md", "5-development-testing.md", "6-logging-registration.md", "7-deployment.md", "8-querying-endpoints.md", "9-package-requirements.md"],
    "databricks-mlflow-evaluation": ["references/CRITICAL-interfaces.md", "references/GOTCHAS.md", "references/patterns-context-optimization.md", "references/patterns-datasets.md", "references/patterns-evaluation.md", "references/patterns-scorers.md", "references/patterns-trace-analysis.md", "references/user-journeys.md"],
    "databricks-spark-declarative-pipelines": ["1-ingestion-patterns.md", "2-streaming-patterns.md", "3-scd-patterns.md", "4-performance-tuning.md", "5-python-api.md", "6-dlt-migration.md", "7-advanced-configuration.md", "8-project-initialization.md"],
    "databricks-spark-structured-streaming": ["checkpoint-best-practices.md", "kafka-streaming.md", "merge-operations.md", "multi-sink-writes.md", "stateful-operations.md", "stream-static-joins.md", "stream-stream-joins.md", "streaming-best-practices.md", "trigger-and-cost-optimization.md"],
    "databricks-vector-search": ["index-types.md", "end-to-end-rag.md"],
    "databricks-zerobus-ingest": ["1-setup-and-authentication.md", "2-python-client.md", "3-multilanguage-clients.md", "4-protobuf-schema.md", "5-operations-and-limits.md"],
}

MLFLOW_EXTRA_FILES = {
    "agent-evaluation": ["references/dataset-preparation.md", "references/scorers-constraints.md", "references/scorers.md", "references/setup-guide.md", "references/tracing-integration.md", "references/troubleshooting.md", "scripts/analyze_results.py", "scripts/create_dataset_template.py", "scripts/list_datasets.py", "scripts/run_evaluation_template.py", "scripts/setup_mlflow.py", "scripts/validate_agent_tracing.py", "scripts/validate_auth.py", "scripts/validate_environment.py", "scripts/validate_tracing_runtime.py"],
    "analyze-mlflow-chat-session": ["scripts/discover_schema.sh", "scripts/inspect_turn.sh"],
    "analyze-mlflow-trace": ["references/trace-structure.md"],
    "instrumenting-with-mlflow-tracing": ["references/advanced-patterns.md", "references/distributed-tracing.md", "references/feedback-collection.md", "references/production.md", "references/python.md", "references/typescript.md"],
    "querying-mlflow-metrics": ["references/api_reference.md", "scripts/fetch_metrics.py"],
}

APX_EXTRA_FILES = {
    "databricks-app-apx": ["backend-patterns.md", "frontend-patterns.md"],
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _download(url: str) -> bytes | None:
    """Download a file from a URL. Returns bytes on success, None on failure."""
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read()
    except Exception:
        return None


def _upload(w: WorkspaceClient, workspace_path: str, content: bytes):
    """Upload a file to the Databricks workspace."""
    import base64
    from databricks.sdk.service.workspace import ImportFormat
    parent = posixpath.dirname(workspace_path)
    w.workspace.mkdirs(parent)
    w.workspace.import_(
        path=workspace_path,
        content=base64.b64encode(content).decode(),
        format=ImportFormat.AUTO,
        overwrite=True,
    )


def install_skill(w: WorkspaceClient, skill_name: str, base_url: str, extra_files: list[str], skills_path: str, source_path: str | None = "") -> bool:
    """Download and upload one skill (SKILL.md + extra files).
    source_path: "" = use skill_name as subdirectory (default), None = files at base_url root, str = custom subdirectory.
    """
    if source_path is None:
        skill_url = base_url
    elif source_path:
        skill_url = f"{base_url}/{source_path}"
    else:
        skill_url = f"{base_url}/{skill_name}"
    skill_md = _download(f"{skill_url}/SKILL.md")
    if skill_md is None:
        print(f"  SKIP {skill_name} (could not download SKILL.md)")
        return False

    dest = f"{skills_path}/{skill_name}"
    _upload(w, f"{dest}/SKILL.md", skill_md)
    uploaded = 1

    for extra in extra_files:
        data = _download(f"{skill_url}/{extra}")
        if data is not None:
            _upload(w, f"{dest}/{extra}", data)
            uploaded += 1

    print(f"  OK   {skill_name} ({uploaded} file{'s' if uploaded != 1 else ''})")
    return True


# ── Main ─────────────────────────────────────────────────────────────────────

w = WorkspaceClient()
username = w.current_user.me().user_name
skills_path = f"/Users/{username}/.assistant/skills"

print(f"Username:  {username}")
print(f"Target:    {skills_path}")
print()

# Determine which skills to install
if INSTALL_SKILLS == "all":
    selected = DATABRICKS_SKILLS + MLFLOW_SKILLS + APX_SKILLS
else:
    selected = INSTALL_SKILLS

w.workspace.mkdirs(skills_path)

installed = 0
failed = 0

# Databricks skills
db_base = f"{REPO_RAW}/databricks-skills"
for skill in selected:
    if skill in DATABRICKS_SKILLS:
        extras = DATABRICKS_EXTRA_FILES.get(skill, [])
        ok = install_skill(w, skill, db_base, extras, skills_path)
        installed += ok
        failed += (not ok)

# MLflow skills
for skill in selected:
    if skill in MLFLOW_SKILLS:
        extras = MLFLOW_EXTRA_FILES.get(skill, [])
        ok = install_skill(w, skill, MLFLOW_RAW, extras, skills_path)
        installed += ok
        failed += (not ok)

# APX skills (files are at the repo root, not in a skill-name subdirectory)
for skill in selected:
    if skill in APX_SKILLS:
        extras = APX_EXTRA_FILES.get(skill, [])
        ok = install_skill(w, skill, APX_RAW, extras, skills_path, source_path=None)
        installed += ok
        failed += (not ok)

print()
print(f"Done. {installed} skills installed, {failed} failed.")
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
    entries = w.workspace.list(skills_path)
    skill_dirs = sorted([e.path.split("/")[-1] for e in entries if e.is_directory])
    print(f"Found {len(skill_dirs)} skills in {skills_path}:\n")
    for name in skill_dirs:
        print(f"  {name}")
except Exception as e:
    print(f"Could not list skills: {e}")
