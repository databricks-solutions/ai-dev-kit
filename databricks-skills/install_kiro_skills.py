#!/usr/bin/env python3
"""
Databricks + MLflow + APX Skills Installer for Kiro
(adapted from ai-dev-kit install_skills.sh)

- Databricks skills: copied from local ai-dev-kit repo
- MLflow skills: downloaded from github.com/mlflow/skills
- APX skills: downloaded from github.com/databricks-solutions/apx

All installed to ~/.kiro/skills/ (user-level, available globally).

Usage:
    python install_kiro_skills.py                          # Install/update all
    python install_kiro_skills.py --list                   # List available
    python install_kiro_skills.py databricks-jobs          # Install specific
    python install_kiro_skills.py agent-evaluation         # MLflow skill
    python install_kiro_skills.py --dry-run                # Preview changes
    python install_kiro_skills.py --only databricks        # Only Databricks
    python install_kiro_skills.py --only mlflow            # Only MLflow
    python install_kiro_skills.py --only apx               # Only APX
    python install_kiro_skills.py --mlflow-ref v1.0.0      # Pin MLflow version
"""
import os
import sys
import shutil
import argparse
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ── Configuration ──────────────────────────────────────────────────────────────
# Auto-detect ai-dev-kit root: this script lives in <ai-dev-kit>/databricks-skills/
SCRIPT_DIR = Path(__file__).resolve().parent
AI_DEV_KIT = Path(os.environ.get("AI_DEV_KIT_PATH", str(SCRIPT_DIR.parent)))
SKILLS_SOURCE = AI_DEV_KIT / "databricks-skills"
KIRO_SKILLS_DIR = Path.home() / ".kiro" / "skills"

MLFLOW_BASE_URL = "https://raw.githubusercontent.com/mlflow/skills"
MLFLOW_REF = "main"
APX_BASE_URL = "https://raw.githubusercontent.com/databricks-solutions/apx"
APX_REF = "main"
APX_SKILL_PATH = "skills/apx"

# ── Skill Definitions ─────────────────────────────────────────────────────────
DATABRICKS_SKILLS = [
    "databricks-agent-bricks",
    "databricks-ai-functions",
    "databricks-aibi-dashboards",
    "databricks-app-python",
    "databricks-bundles",
    "databricks-config",
    "databricks-dbsql",
    "databricks-docs",
    "databricks-execution-compute",
    "databricks-genie",
    "databricks-iceberg",
    "databricks-jobs",
    "databricks-lakebase-autoscale",
    "databricks-lakebase-provisioned",
    "databricks-metric-views",
    "databricks-mlflow-evaluation",
    "databricks-model-serving",
    "databricks-python-sdk",
    "databricks-spark-declarative-pipelines",
    "databricks-spark-structured-streaming",
    "databricks-synthetic-data-gen",
    "databricks-unity-catalog",
    "databricks-unstructured-pdf-generation",
    "databricks-vector-search",
    "databricks-zerobus-ingest",
    "spark-python-data-source",
]

MLFLOW_SKILLS = [
    "agent-evaluation",
    "analyze-mlflow-chat-session",
    "analyze-mlflow-trace",
    "instrumenting-with-mlflow-tracing",
    "mlflow-onboarding",
    "querying-mlflow-metrics",
    "retrieving-mlflow-traces",
    "searching-mlflow-docs",
]

MLFLOW_EXTRA_FILES = {
    "agent-evaluation": [
        "references/dataset-preparation.md",
        "references/scorers-constraints.md",
        "references/scorers.md",
        "references/setup-guide.md",
        "references/tracing-integration.md",
        "references/troubleshooting.md",
        "scripts/analyze_results.py",
        "scripts/create_dataset_template.py",
        "scripts/list_datasets.py",
        "scripts/run_evaluation_template.py",
        "scripts/setup_mlflow.py",
        "scripts/validate_agent_tracing.py",
        "scripts/validate_auth.py",
        "scripts/validate_environment.py",
        "scripts/validate_tracing_runtime.py",
    ],
    "analyze-mlflow-chat-session": [
        "scripts/discover_schema.sh",
        "scripts/inspect_turn.sh",
    ],
    "analyze-mlflow-trace": ["references/trace-structure.md"],
    "instrumenting-with-mlflow-tracing": [
        "references/advanced-patterns.md",
        "references/distributed-tracing.md",
        "references/feedback-collection.md",
        "references/production.md",
        "references/python.md",
        "references/typescript.md",
    ],
    "querying-mlflow-metrics": [
        "references/api_reference.md",
        "scripts/fetch_metrics.py",
    ],
}

APX_SKILLS = ["databricks-app-apx"]
APX_EXTRA_FILES = {
    "databricks-app-apx": [
        "backend-patterns.md",
        "best-practices.md",
        "frontend-patterns.md",
    ],
}

ALL_SKILLS = DATABRICKS_SKILLS + MLFLOW_SKILLS + APX_SKILLS


def get_source_type(skill_name):
    if skill_name in DATABRICKS_SKILLS:
        return "databricks"
    elif skill_name in MLFLOW_SKILLS:
        return "mlflow"
    elif skill_name in APX_SKILLS:
        return "apx"
    return None


# ── Download Helper ────────────────────────────────────────────────────────────
def download_file(url, dest_path):
    """Download a file from URL. Returns True on success, False on 404/error."""
    try:
        req = Request(url, headers={"User-Agent": "kiro-skills-installer/1.0"})
        with urlopen(req, timeout=30) as resp:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(resp.read())
        return True
    except HTTPError as e:
        if e.code == 404:
            return False
        print(f"    HTTP {e.code} downloading {url}")
        return False
    except (URLError, OSError) as e:
        print(f"    Network error: {e}")
        return False


# ── Install Functions ──────────────────────────────────────────────────────────
def install_databricks_skill(skill_name, dry_run=False):
    src = SKILLS_SOURCE / skill_name
    dst = KIRO_SKILLS_DIR / skill_name
    if not src.exists() or not (src / "SKILL.md").exists():
        print(f"  SKIP {skill_name} - source not found")
        return False
    if dry_run:
        fc = sum(1 for _ in src.rglob("*") if _.is_file())
        print(f"  [DRY-RUN] {skill_name} ({fc} files) [local]")
        return True
    # Overwrite file-by-file (avoids lock issues when Kiro has files open)
    dst.mkdir(parents=True, exist_ok=True)
    fc = 0
    for src_file in src.rglob("*"):
        if src_file.is_file():
            rel = src_file.relative_to(src)
            dst_file = dst / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            fc += 1
    print(f"  OK {skill_name} ({fc} files) [local]")
    return True


def install_remote_skill(
    skill_name, base_url, ref, extra_files_map, skill_path="", dry_run=False
):
    dst = KIRO_SKILLS_DIR / skill_name
    prefix = (
        f"{base_url}/{ref}/{skill_path}"
        if skill_path
        else f"{base_url}/{ref}/{skill_name}"
    )
    if dry_run:
        extras = extra_files_map.get(skill_name, [])
        print(f"  [DRY-RUN] {skill_name} (1 + {len(extras)} files) [remote]")
        return True
    dst.mkdir(parents=True, exist_ok=True)
    if not download_file(f"{prefix}/SKILL.md", dst / "SKILL.md"):
        print(f"  FAIL {skill_name} - SKILL.md not found")
        return False
    fc = 1
    for extra in extra_files_map.get(skill_name, []):
        if download_file(f"{prefix}/{extra}", dst / extra):
            fc += 1
        else:
            print(f"    optional: {extra} not found")
    print(f"  OK {skill_name} ({fc} files) [remote]")
    return True


def install_skill(skill_name, dry_run=False, mlflow_ref="main", apx_ref="main"):
    stype = get_source_type(skill_name)
    if stype == "databricks":
        return install_databricks_skill(skill_name, dry_run)
    elif stype == "mlflow":
        return install_remote_skill(
            skill_name, MLFLOW_BASE_URL, mlflow_ref, MLFLOW_EXTRA_FILES, dry_run=dry_run
        )
    elif stype == "apx":
        return install_remote_skill(
            skill_name,
            APX_BASE_URL,
            apx_ref,
            APX_EXTRA_FILES,
            skill_path=APX_SKILL_PATH,
            dry_run=dry_run,
        )
    print(f"  SKIP {skill_name} - unknown source")
    return False


# ── List ───────────────────────────────────────────────────────────────────────
def list_skills():
    print(f"\nLocal source: {SKILLS_SOURCE}")
    print(f"Target:       {KIRO_SKILLS_DIR}\n")
    for label, skills in [
        ("Databricks", DATABRICKS_SKILLS),
        ("MLflow", MLFLOW_SKILLS),
        ("APX", APX_SKILLS),
    ]:
        print(f"  [{label}]")
        for skill in skills:
            status = (
                "installed" if (KIRO_SKILLS_DIR / skill / "SKILL.md").exists() else "-"
            )
            print(f"    {skill:<45} {status}")
        print()


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Install Databricks/MLflow/APX skills for Kiro"
    )
    parser.add_argument("skills", nargs="*", help="Specific skills (default: all)")
    parser.add_argument(
        "--list", "-l", action="store_true", help="List available skills"
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true", help="Preview without installing"
    )
    parser.add_argument(
        "--only",
        choices=["databricks", "mlflow", "apx"],
        help="Install only one category",
    )
    parser.add_argument(
        "--mlflow-ref", default=MLFLOW_REF, help="MLflow repo ref (default: main)"
    )
    parser.add_argument(
        "--apx-ref", default=APX_REF, help="APX repo ref (default: main)"
    )
    args = parser.parse_args()

    if args.list:
        list_skills()
        return

    KIRO_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    if args.skills:
        skills = args.skills
        for s in skills:
            if s not in ALL_SKILLS:
                print(
                    f"ERROR: Unknown skill '{s}'. Use --list to see available skills."
                )
                sys.exit(1)
    elif args.only == "databricks":
        skills = DATABRICKS_SKILLS
    elif args.only == "mlflow":
        skills = MLFLOW_SKILLS
    elif args.only == "apx":
        skills = APX_SKILLS
    else:
        skills = ALL_SKILLS

    has_db = any(get_source_type(s) == "databricks" for s in skills)
    if has_db and not SKILLS_SOURCE.exists():
        print(f"ERROR: ai-dev-kit not found at {SKILLS_SOURCE}")
        print(
            f"Set AI_DEV_KIT_PATH env var or ensure this script is inside ai-dev-kit/databricks-skills/"
        )
        sys.exit(1)

    action = "DRY-RUN" if args.dry_run else "Installing"
    db = sum(1 for s in skills if get_source_type(s) == "databricks")
    ml = sum(1 for s in skills if get_source_type(s) == "mlflow")
    ax = sum(1 for s in skills if get_source_type(s) == "apx")
    print(f"\n{action} {len(skills)} skills ({db} databricks, {ml} mlflow, {ax} apx)")
    print(f"Target: {KIRO_SKILLS_DIR}\n")

    ok, fail = 0, 0
    for skill in skills:
        try:
            if install_skill(skill, args.dry_run, args.mlflow_ref, args.apx_ref):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            print(f"  FAIL {skill}: {e}")
            fail += 1

    print(f"\nDone: {ok} installed, {fail} failed\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
