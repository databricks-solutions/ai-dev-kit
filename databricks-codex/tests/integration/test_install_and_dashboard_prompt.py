"""Integration tests for Codex skill/MCP installer and dashboard prompting."""

import os
import shutil
import subprocess
import json
from pathlib import Path

import pytest

from databricks_codex.models import CodexExecOptions, ExecutionStatus, SandboxMode

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - py39 fallback
    import tomli as tomllib  # type: ignore[no-redef]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _installer_script() -> Path:
    return _repo_root() / "databricks-codex" / "scripts" / "install_codex_skills_and_mcp.sh"


def _project_codex_config() -> Path:
    return _repo_root() / ".codex" / "config.toml"


def _first_databricks_profile() -> str:
    result = subprocess.run(
        ["databricks", "auth", "profiles", "--output", "json"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"Unable to read Databricks profiles: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    profiles = data.get("profiles") or []
    if not profiles:
        pytest.skip("No Databricks CLI profiles configured")
    profile_name = profiles[0].get("name")
    if not profile_name:
        pytest.skip("First Databricks profile has no name")
    return profile_name


def _run_installer(codex_home: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    return subprocess.run(
        ["bash", str(_installer_script()), *args],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )


def _seed_codex_auth(codex_home: Path) -> None:
    """Copy local Codex auth artifacts into isolated CODEX_HOME for integration tests."""
    src_home = Path.home() / ".codex"
    if not src_home.exists():
        pytest.skip("Local ~/.codex not found; cannot seed Codex auth for isolated CODEX_HOME")

    codex_home.mkdir(parents=True, exist_ok=True)
    copied = 0
    for filename in ("auth.json", "credentials.json", "oauth.json", "config.toml"):
        src = src_home / filename
        dst = codex_home / filename
        if src.exists():
            shutil.copy2(src, dst)
            copied += 1

    if copied == 0:
        pytest.skip("No Codex auth artifacts found in ~/.codex to seed isolated CODEX_HOME")


@pytest.mark.integration
def test_install_script_uses_first_databricks_profile_by_default(tmp_path):
    """Installer should use the first Databricks CLI profile when --profile is omitted."""
    config_path = _project_codex_config()
    original_config = config_path.read_bytes() if config_path.exists() else None
    codex_home = tmp_path / "codex-home"
    first_profile = _first_databricks_profile()

    try:
        _seed_codex_auth(codex_home)
        result = _run_installer(codex_home, ["databricks-dbsql", "aibi-dashboards"])
        assert result.returncode == 0, result.stderr or result.stdout

        skill_a = codex_home / "skills" / "databricks-dbsql" / "SKILL.md"
        skill_b = codex_home / "skills" / "aibi-dashboards" / "SKILL.md"
        assert skill_a.exists(), "databricks-dbsql skill was not installed"
        assert skill_b.exists(), "aibi-dashboards skill was not installed"

        config_data = tomllib.loads(config_path.read_text())
        server = config_data["mcp_servers"]["databricks"]
        assert server["command"] in {"uv", "python3", "python"}
        assert server.get("args")
        assert server.get("env", {}).get("DATABRICKS_CONFIG_PROFILE") == first_profile
    finally:
        if original_config is None:
            config_path.unlink(missing_ok=True)
        else:
            config_path.write_bytes(original_config)
        shutil.rmtree(codex_home, ignore_errors=True)


@pytest.mark.integration
@pytest.mark.timeout(240)
def test_codex_prompt_generates_dashboard_sql_after_install(executor, tmp_path):
    """Install skills/MCP, then send a Codex prompt to generate dashboard SQL."""
    config_path = _project_codex_config()
    original_config = config_path.read_bytes() if config_path.exists() else None
    codex_home = tmp_path / "codex-home"
    output_file = _repo_root() / "databricks-codex" / "tests" / ".tmp_dashboard_queries.sql"
    first_profile = _first_databricks_profile()

    try:
        _seed_codex_auth(codex_home)
        install_result = _run_installer(codex_home, ["aibi-dashboards", "databricks-dbsql"])
        assert install_result.returncode == 0, install_result.stderr or install_result.stdout

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.unlink(missing_ok=True)

        prompt = (
            "Create a file at databricks-codex/tests/.tmp_dashboard_queries.sql with exactly three "
            "Databricks SQL queries for an AI/BI dashboard over users.rlgarris.loan_data_2: "
            "(1) total loan applications and average loan amount, "
            "(2) loan_status distribution, "
            "(3) top 10 occupations by average applicant_income. "
            "Output only the file creation action."
        )
        options = CodexExecOptions(
            prompt=prompt,
            sandbox_mode=SandboxMode.WORKSPACE_WRITE,
            timeout=180,
            working_dir=str(_repo_root()),
            env_vars={"CODEX_HOME": str(codex_home)},
            inject_databricks_env=True,
            databricks_profile=first_profile,
        )
        result = executor.exec_sync(options)
        assert result.status == ExecutionStatus.COMPLETED, result.stderr or result.stdout
        assert output_file.exists(), "Codex did not create dashboard SQL file"
        sql_text = output_file.read_text()
        assert "users.rlgarris.loan_data_2" in sql_text
        assert "loan_status" in sql_text
    finally:
        output_file.unlink(missing_ok=True)
        if original_config is None:
            config_path.unlink(missing_ok=True)
        else:
            config_path.write_bytes(original_config)
        shutil.rmtree(codex_home, ignore_errors=True)
