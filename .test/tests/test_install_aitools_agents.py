"""Tests for the version-gated `aitools --agents` mapping in install.sh and install.ps1.

`gemini` and `kiro` are only valid `databricks aitools install --agents` values on
newer CLIs, and an unknown agent fails the whole install. The installers only pass
them when the installed CLI is new enough. Neither installer can be sourced (both
run on load), so the functions under test are extracted and run against a stub CLI.
The bash dry run is the exception: it is cheap and offline, so it runs end to end.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"
INSTALL_PS1 = REPO_ROOT / "install.ps1"
SYSTEM_PATH = "/usr/bin:/bin"
PWSH = shutil.which("pwsh")  # resolved here: the tests run pwsh with a stub-only PATH
TOOLS = "cursor gemini windsurf kiro"
ANSI = re.compile(r"\x1b\[[0-9;]*m")

# (installed CLI version or None for "not installed", expected --agents value)
CASES = [
    (None, "cursor"),
    ("1.11.9", "cursor"),
    ("1.12.0", "cursor,gemini"),
    ("1.19.9", "cursor,gemini"),
    ("1.20.0", "cursor,gemini,kiro"),
    ("1.100.0", "cursor,gemini,kiro"),
]


def _bash_functions(*names: str) -> str:
    src = INSTALL_SH.read_text()
    consts = re.findall(r"(?m)^MIN_AITOOLS_(?:GEMINI|KIRO)_CLI_VERSION=.*$", src)
    fns = []
    for name in names:
        match = re.search(rf"(?ms)^{name}\(\) \{{.*?^\}}$", src)
        assert match, f"{name} not found in install.sh"
        fns.append(match.group(0))
    assert len(consts) == 2, "CLI floor constants not found in install.sh"
    return "\n".join(consts + fns)


def _stub_cli(tmp_path: Path, version: str | None, body: str | None = None) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    if version is not None or body is not None:
        stub = bin_dir / "databricks"
        stub.write_text(body or f'#!/bin/sh\necho "Databricks CLI v{version}"\n')
        stub.chmod(0o755)
    return bin_dir


@pytest.fixture(autouse=True)
def _no_system_cli():
    if shutil.which("databricks", path=SYSTEM_PATH):
        pytest.skip("a databricks CLI on the system PATH would shadow the stub")


def _run_bash(tmp_path: Path, version: str | None, script: str, env: dict | None = None) -> subprocess.CompletedProcess:
    fns = tmp_path / "fns.sh"
    fns.write_text(
        _bash_functions(
            "version_gte",
            "databricks_cli_version",
            "map_aitools_agents",
            "gemini_global_skills_dir",
            "gemini_relocated_skills_dir",
            "agent_skill_target_dirs",
            "install_skills",
        )
    )
    return subprocess.run(
        ["bash", "-c", f'set -e\n. "{fns}"\n{script}'],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": f"{_stub_cli(tmp_path, version)}:{SYSTEM_PATH}", "HOME": str(tmp_path), **(env or {})},
    )


def _map_agents(tools: str, version_arg: str = "") -> str:
    return f'TOOLS="{tools}"\nmap_aitools_agents {version_arg}\necho "$AITOOLS_AGENTS"\n'


@pytest.mark.parametrize("version,expected", CASES)
def test_install_sh_maps_agents_by_cli_version(tmp_path, version, expected):
    result = _run_bash(tmp_path, version, _map_agents(TOOLS))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_install_sh_skipped_last_agent_does_not_trip_set_e(tmp_path):
    # kiro is the last tool and below its floor: the mapping must still return 0 under `set -e`
    result = _run_bash(tmp_path, "1.19.9", _map_agents("cursor kiro"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "cursor"


# (stub `databricks` script, expected --agents for TOOLS="cursor kiro")
NOISY_CLI_CASES = [
    # an update notice on stderr: PS merged it with 2>&1 into an array (and throws on PS 5.1)
    pytest.param(
        '#!/bin/sh\necho "A new release is available" >&2\necho "Databricks CLI v1.20.0"\n',
        "cursor,kiro",
        id="stderr-notice",
    ),
    # two stdout lines: PS -match on an array filters it and never sets $Matches
    pytest.param(
        '#!/bin/sh\necho "Databricks CLI v1.20.0"\necho "Update available"\n',
        "cursor,kiro",
        id="multi-line-stdout",
    ),
    # no semver at all: version unknown, so the gated agents are left out
    pytest.param('#!/bin/sh\necho "dev build"\n', "cursor", id="no-semver"),
    # a newer version in a notice before the version line must not lift an old CLI over the floors
    pytest.param(
        '#!/bin/sh\necho "Version 1.21.0 is available"\necho "Databricks CLI v1.11.0"\n',
        "cursor",
        id="notice-before-version",
    ),
]


@pytest.mark.parametrize("stub,expected", NOISY_CLI_CASES)
def test_install_sh_cli_version_survives_noisy_output(tmp_path, stub, expected):
    _stub_cli(tmp_path, None, stub)
    result = _run_bash(tmp_path, None, _map_agents("cursor kiro"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_install_sh_version_argument_overrides_installed_cli(tmp_path):
    # the dry run passes the version a real run would end up with after the CLI upgrade
    result = _run_bash(tmp_path, "1.11.9", _map_agents(TOOLS, "1.20.0"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "cursor,gemini,kiro"


# (scope, GEMINI_CLI_HOME relative to tmp_path or None, Gemini skills dir relative to tmp_path)
GEMINI_DIR_CASES = [
    ("global", None, ".gemini/skills"),
    ("global", "gem", "gem/.gemini/skills"),
    ("project", "gem", "proj/.gemini/skills"),
]


def _gemini_env(tmp_path: Path, gemini_home: str | None) -> dict:
    return {"GEMINI_CLI_HOME": str(tmp_path / gemini_home)} if gemini_home else {}


@pytest.mark.parametrize("scope,gemini_home,expected", GEMINI_DIR_CASES)
def test_install_sh_gemini_skills_dir_follows_gemini_cli_home(tmp_path, scope, gemini_home, expected):
    base = tmp_path if scope == "global" else tmp_path / "proj"
    script = f'SCOPE={scope}\nTOOLS="gemini"\nagent_skill_target_dirs "{base}"\n'
    result = _run_bash(tmp_path, None, script, _gemini_env(tmp_path, gemini_home))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(tmp_path / expected)


# (GEMINI_CLI_HOME as a template over {home}, or None for unset; relocated?)
RELOCATED_CASES = [
    pytest.param(None, False, id="unset"),
    pytest.param("{home}", False, id="same-as-home"),
    pytest.param("{home}/", False, id="same-as-home-trailing-slash"),
    pytest.param("{home}/.", False, id="same-as-home-dot-segment"),
    pytest.param("{home}//", False, id="same-as-home-double-slash"),
    pytest.param("{home}/gem", True, id="relocated"),
]


@pytest.mark.parametrize("gemini_home,relocated", RELOCATED_CASES)
def test_install_sh_relocated_gemini_dir_only_when_moved(tmp_path, gemini_home, relocated):
    # GEMINI_CLI_HOME naming $HOME is not a relocation, so scans must not count ~/.gemini twice.
    # The scans skip missing dirs, so the spelling only matters once ~/.gemini/skills exists.
    home = str(tmp_path.resolve())
    (tmp_path / ".gemini" / "skills").mkdir(parents=True)
    env = {"HOME": home} | ({"GEMINI_CLI_HOME": gemini_home.format(home=home)} if gemini_home else {})
    result = _run_bash(tmp_path, None, "gemini_relocated_skills_dir\n", env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (f"{home}/gem/.gemini/skills" if relocated else "")


@pytest.mark.parametrize("home_suffix", ["", "/"], ids=["home", "home-trailing-slash"])
def test_install_sh_unmoved_gemini_dir_is_not_reported_before_it_exists(tmp_path, home_suffix):
    # a fresh machine: no ~/.gemini yet and GEMINI_CLI_HOME unset is still "not moved"
    env = {"HOME": f"{tmp_path.resolve()}{home_suffix}"}
    result = _run_bash(tmp_path, None, "gemini_relocated_skills_dir\n", env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_install_sh_trailing_slash_home_is_not_a_relocation(tmp_path):
    # HOME="/x/" with GEMINI_CLI_HOME unset names the same ~/.gemini/skills as HOME="/x"
    home = tmp_path.resolve()
    (home / ".gemini" / "skills").mkdir(parents=True)
    result = _run_bash(tmp_path, None, "gemini_relocated_skills_dir\n", {"HOME": f"{home}/"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_install_sh_gemini_cli_home_symlinked_to_home_is_not_a_relocation(tmp_path):
    # a spelling no string compare can catch: the same directory reached through a symlink
    home = tmp_path.resolve()
    (home / ".gemini" / "skills").mkdir(parents=True)
    (home / "home-link").symlink_to(home, target_is_directory=True)
    env = {"HOME": str(home), "GEMINI_CLI_HOME": str(home / "home-link")}
    result = _run_bash(tmp_path, None, "gemini_relocated_skills_dir\n", env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_install_sh_install_skills_uses_gemini_cli_home(tmp_path):
    # MLflow skills land where Gemini reads them, not in a second, unread copy under ~/.gemini
    script = (
        "step() { :; }; msg() { :; }; ok() { :; }\n"
        "_count() { echo $#; }\n"
        "_in_list() { echo \"$2\" | tr ' ' '\\n' | grep -Fxq \"$1\"; }\n"
        f'SCOPE=global TOOLS=gemini STATE_DIR="{tmp_path}/state" INSTALL_DIR="{tmp_path}/state"\n'
        'SELECTED_MLFLOW_SKILLS="" MLFLOW_BASE_URL=unused\n'
        'install_skills "$HOME"\n'
    )
    result = _run_bash(tmp_path, None, script, {"GEMINI_CLI_HOME": str(tmp_path / "gem")})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "gem" / ".gemini" / "skills").is_dir()
    assert not (tmp_path / ".gemini").exists()


# (installed CLI version or None, expected --agents, expected upgrade warning or None)
DRY_RUN_CASES = [
    (None, "kiro,gemini", "Databricks CLI not found: a real run first offers to upgrade"),
    ("0.280.0", "kiro,gemini", "Databricks CLI v0.280.0 is too old: a real run first offers to upgrade"),
    ("1.19.9", "gemini", None),
    ("1.20.0", "kiro,gemini", None),
]


def _run_installer(tmp_path: Path, cmd: list[str], version: str | None, env: dict | None, cwd: Path | None) -> str:
    """Run a real installer offline with HOME/USERPROFILE at tmp_path/home and a stub CLI."""
    bin_dir = _stub_cli(tmp_path, version)
    for tool in ("curl", "git"):  # keep the run offline; the installers tolerate both failing
        offline = bin_dir / tool
        offline.write_text("#!/bin/sh\nexit 7\n")
        offline.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd or tmp_path,
        timeout=120,
        env={
            "PATH": f"{bin_dir}:{SYSTEM_PATH}",
            "HOME": str(home),
            "USERPROFILE": str(home),
            "TERM": "dumb",
            **(env or {}),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return ANSI.sub("", result.stdout)


AGENT_TOOLS = ("--global", "--tools", "kiro,gemini,windsurf")


def _run_sh_dry_run(tmp_path, version, env=None, args=AGENT_TOOLS, cwd=None) -> str:
    return _run_installer(tmp_path, ["bash", str(INSTALL_SH), "--dry-run", *args], version, env, cwd)


def _run_ps1_dry_run(tmp_path, args, env=None, cwd=None) -> str:
    cmd = [str(PWSH), "-NoProfile", "-NonInteractive", "-File", str(INSTALL_PS1), "--dry-run", *args]
    return _run_installer(tmp_path, cmd, None, env, cwd)


def _seed_relocated_gemini_skill(tmp_path: Path) -> Path:
    skill = tmp_path / "gem" / ".gemini" / "skills" / "databricks-jobs"
    skill.mkdir(parents=True)
    return skill


@pytest.mark.parametrize("version,agents,warning", DRY_RUN_CASES)
def test_install_sh_dry_run_previews_what_a_real_run_does(tmp_path, version, agents, warning):
    out = _run_sh_dry_run(tmp_path, version)
    assert f"aitools install --scope global --agents {agents} " in out
    if warning:
        assert warning in out
    else:
        assert "a real run first offers to upgrade" not in out


def test_install_sh_dry_run_lists_relocated_gemini_dir(tmp_path):
    out = _run_sh_dry_run(tmp_path, "1.20.0", {"GEMINI_CLI_HOME": str(tmp_path / "gem")})
    assert f"→ {tmp_path / 'gem' / '.gemini' / 'skills'}" in out
    assert f"→ {tmp_path / 'home' / '.gemini' / 'skills'}" not in out


def test_install_sh_uninstall_finds_both_gemini_dirs(tmp_path):
    # skills under a relocated GEMINI_CLI_HOME are removed, and so is a copy an older install left in ~/.gemini
    relocated = tmp_path / "gem" / ".gemini" / "skills" / "databricks-jobs"
    legacy = tmp_path / "home" / ".gemini" / "skills" / "databricks-jobs"
    for skill in (relocated, legacy):
        skill.mkdir(parents=True)
    out = _run_sh_dry_run(tmp_path, None, {"GEMINI_CLI_HOME": str(tmp_path / "gem")}, args=("--global", "--uninstall"))
    assert "Skill folders (2):" in out
    assert str(relocated) in out
    assert "~/.gemini/skills/databricks-jobs" in out


def test_install_sh_uninstall_lists_gemini_skills_once_with_trailing_slash_home(tmp_path):
    # the user-visible effect: a respelled HOME used to plan every ~/.gemini skill twice
    home = tmp_path / "home"
    skill = home / ".gemini" / "skills" / "databricks-jobs"
    skill.mkdir(parents=True)
    out = _run_sh_dry_run(tmp_path, None, {"HOME": f"{home}/"}, args=("--global", "--uninstall"))
    assert "Skill folders (1):" in out
    assert out.count(".gemini/skills/databricks-jobs") == 1


def test_install_sh_dry_run_explicit_agent_skills_previews_upgrade(tmp_path):
    out = _run_sh_dry_run(tmp_path, None, args=("--global", "--tools", "kiro,gemini", "--skills", "databricks-jobs"))
    assert "--agents kiro,gemini --skills databricks-jobs --skills-only" in out
    assert "a real run first offers to upgrade" in out


def test_install_sh_dry_run_without_agent_skills_skips_cli_check(tmp_path):
    # MLflow skills only: a real run never gates on the CLI, so neither does the preview
    out = _run_sh_dry_run(tmp_path, None, args=("--global", "--tools", "kiro,gemini", "--skills", "agent-evaluation"))
    assert "Agent skills: <none>" in out
    assert "a real run first offers to upgrade" not in out


def test_install_sh_project_uninstall_warns_about_relocated_gemini_leftovers(tmp_path):
    _seed_relocated_gemini_skill(tmp_path)
    (tmp_path / "proj").mkdir()
    env = {"GEMINI_CLI_HOME": str(tmp_path / "gem")}
    out = _run_sh_dry_run(tmp_path, None, env, args=("--uninstall",), cwd=tmp_path / "proj")
    assert "GLOBAL AI DEV KIT FILES STILL REMAIN" in out
    assert "1 skill folder(s)" in out


def test_install_sh_flags_old_copy_in_relocated_gemini_dir(tmp_path):
    # a real (non-symlink) skill folder there predates aitools, so the installer offers cleanup
    _seed_relocated_gemini_skill(tmp_path)
    env = {"GEMINI_CLI_HOME": str(tmp_path / "gem")}
    out = _run_sh_dry_run(tmp_path, "1.20.0", env, args=("--global", "--tools", "gemini"))
    assert "PREVIOUS AI DEV KIT INSTALL DETECTED" in out
    assert "1 directly-installed skill folder(s)" in out


# Extracts the named functions plus the CLI floor constants from install.ps1, then
# dot-sources -Body so it runs with those functions in scope.
PS_HARNESS = r"""
param([string]$Path, [string]$Names, [string]$Body)
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) { throw "install.ps1 has parse errors" }
$wanted = $Names -split ','
$fns = $ast.FindAll({ param($n)
    $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -in $wanted }, $true)
$consts = $ast.FindAll({ param($n)
    $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $n.Left.Extent.Text -match '^\$MinAitools(Gemini|Kiro)?CliVersion$' }, $false)
if ($fns.Count -ne $wanted.Count -or $consts.Count -ne 3) { throw "functions or CLI floors not found" }
foreach ($node in @($consts) + @($fns)) { . ([scriptblock]::Create($node.Extent.Text)) }
. ([scriptblock]::Create($Body))
"""


def _run_pwsh(tmp_path: Path, names: list[str], body: str, env: dict | None = None) -> subprocess.CompletedProcess:
    harness = tmp_path / "harness.ps1"
    harness.write_text(PS_HARNESS)
    return subprocess.run(
        [str(PWSH), "-NoProfile", "-NonInteractive", "-File", str(harness)]
        + ["-Path", str(INSTALL_PS1), "-Names", ",".join(names), "-Body", body],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": f"{_stub_cli(tmp_path, None)}:{SYSTEM_PATH}",
            "HOME": str(tmp_path),
            "USERPROFILE": str(tmp_path),
            **(env or {}),
        },
    )


needs_pwsh = pytest.mark.skipif(PWSH is None, reason="pwsh not installed")


@needs_pwsh
@pytest.mark.parametrize("version,expected", CASES)
def test_install_ps1_maps_agents_by_cli_version(tmp_path, version, expected):
    stub = f'function databricks {{ "Databricks CLI v{version}" }}\n' if version else ""
    body = f'{stub}$script:Tools = "{TOOLS}"\nResolve-AitoolsAgents\n$script:AitoolsAgents\n'
    result = _run_pwsh(tmp_path, ["Get-DatabricksCliVersion", "Resolve-AitoolsAgents"], body)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


@needs_pwsh
@pytest.mark.parametrize("stub,expected", NOISY_CLI_CASES)
def test_install_ps1_cli_version_survives_noisy_output(tmp_path, stub, expected):
    _stub_cli(tmp_path, None, stub)
    body = '$ErrorActionPreference = "Stop"\n$script:Tools = "cursor kiro"\n'
    body += "Resolve-AitoolsAgents\n$script:AitoolsAgents\n"
    result = _run_pwsh(tmp_path, ["Get-DatabricksCliVersion", "Resolve-AitoolsAgents"], body)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


@needs_pwsh
@pytest.mark.parametrize("scope,gemini_home,expected", GEMINI_DIR_CASES)
def test_install_ps1_gemini_skills_dir_follows_gemini_cli_home(tmp_path, scope, gemini_home, expected):
    base = tmp_path if scope == "global" else tmp_path / "proj"
    body = f'$script:Scope = "{scope}"\n$script:Tools = "gemini"\nGet-AgentSkillTargetDirs -BaseDir "{base}"\n'
    names = ["Get-GeminiGlobalSkillsDir", "Get-AgentSkillTargetDirs"]
    result = _run_pwsh(tmp_path, names, body, _gemini_env(tmp_path, gemini_home))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().replace("\\", "/") == str(tmp_path / expected)


PS_DRY_RUN_FNS = [
    "Write-Msg",
    "Write-Warn",
    "Get-DatabricksCliVersion",
    "Resolve-AitoolsAgents",
    "Get-GeminiGlobalSkillsDir",
    "Get-AgentSkillTargetDirs",
    "Test-AgentBNeedsExperimental",
    "Show-DryRunReport",
]


def _ps_dry_run(tmp_path: Path, version: str | None, all_agent_skills: bool, agent_skills: tuple = ()) -> str:
    stub = f'function databricks {{ "Databricks CLI v{version}" }}\n' if version else ""
    skills = ", ".join(f"'{name}'" for name in agent_skills)
    body = (
        f"{stub}$script:Tools = 'kiro gemini windsurf'; $script:Scope = 'global'; $script:Profile_ = 'DEFAULT'\n"
        f"$script:SelectedAllAgentB = ${str(all_agent_skills).lower()}; $script:SelectedAgentBSkills = @({skills})\n"
        "$script:SelectedMlflowSkills = @(); $script:InstallExperimental = $false; $script:AgentBRelease = ''\n"
        "$script:AgentBExperimental = @()\n"
        "Show-DryRunReport\n"
    )
    result = _run_pwsh(tmp_path, PS_DRY_RUN_FNS, body)
    assert result.returncode == 0, result.stderr
    return ANSI.sub("", result.stdout)


@needs_pwsh
@pytest.mark.parametrize("version,agents,warning", DRY_RUN_CASES)
def test_install_ps1_dry_run_previews_what_a_real_run_does(tmp_path, version, agents, warning):
    out = _ps_dry_run(tmp_path, version, all_agent_skills=True)
    assert f"aitools install --scope global --agents {agents} " in out
    if warning:
        assert warning in out
    else:
        assert "a real run first offers to upgrade" not in out


@needs_pwsh
@pytest.mark.parametrize("gemini_home,relocated", RELOCATED_CASES)
def test_install_ps1_relocated_gemini_dir_only_when_moved(tmp_path, gemini_home, relocated):
    home = str(tmp_path.resolve())
    env = {"USERPROFILE": home} | ({"GEMINI_CLI_HOME": gemini_home.format(home=home)} if gemini_home else {})
    names = ["Get-GeminiGlobalSkillsDir", "Get-GeminiRelocatedSkillsDir"]
    result = _run_pwsh(tmp_path, names, "Get-GeminiRelocatedSkillsDir\n", env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().replace("\\", "/") == (f"{home}/gem/.gemini/skills" if relocated else "")


@needs_pwsh
def test_install_ps1_install_skills_uses_gemini_cli_home(tmp_path):
    body = (
        f"$script:Scope = 'global'; $script:Tools = 'gemini'; $script:StateDir = '{tmp_path / 'state'}'\n"
        f"$script:InstallDir = '{tmp_path / 'state'}'; $script:SelectedMlflowSkills = @()\n"
        "$script:UserSkills = ''; $script:SkillsProfile = ''; $script:Silent = $true\n"
        "Install-Skills -BaseDir $env:USERPROFILE\n"
    )
    names = ["Write-Step", "Write-Msg", "Write-Ok", "Get-GeminiGlobalSkillsDir", "Install-Skills"]
    result = _run_pwsh(tmp_path, names, body, {"GEMINI_CLI_HOME": str(tmp_path / "gem")})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "gem" / ".gemini" / "skills").is_dir()
    assert not (tmp_path / ".gemini").exists()


@needs_pwsh
def test_install_ps1_uninstall_finds_both_gemini_dirs(tmp_path):
    # runs the real install.ps1 uninstall dry run, like the bash twin
    relocated = _seed_relocated_gemini_skill(tmp_path)
    legacy = tmp_path / "home" / ".gemini" / "skills" / "databricks-jobs"
    legacy.mkdir(parents=True)
    out = _run_ps1_dry_run(tmp_path, ("--uninstall", "--global"), {"GEMINI_CLI_HOME": str(tmp_path / "gem")})
    assert "Skill folders (2):" in out
    assert str(relocated) in out
    assert str(legacy) in out


@needs_pwsh
def test_install_ps1_dry_run_explicit_agent_skills_previews_upgrade(tmp_path):
    out = _ps_dry_run(tmp_path, None, all_agent_skills=False, agent_skills=("databricks-jobs",))
    assert "--agents kiro,gemini --skills databricks-jobs --skills-only" in out
    assert "a real run first offers to upgrade" in out


@needs_pwsh
def test_install_ps1_dry_run_without_agent_skills_skips_cli_check(tmp_path):
    out = _ps_dry_run(tmp_path, None, all_agent_skills=False)
    assert "Agent skills: <none>" in out
    assert "a real run first offers to upgrade" not in out


@needs_pwsh
def test_install_ps1_project_uninstall_warns_about_relocated_gemini_leftovers(tmp_path):
    _seed_relocated_gemini_skill(tmp_path)
    (tmp_path / "proj").mkdir()
    env = {"GEMINI_CLI_HOME": str(tmp_path / "gem")}
    out = _run_ps1_dry_run(tmp_path, ("--uninstall",), env, cwd=tmp_path / "proj")
    assert "GLOBAL AI DEV KIT FILES STILL REMAIN" in out
    assert "1 skill folder(s)" in out


@needs_pwsh
def test_install_ps1_flags_old_copy_in_relocated_gemini_dir(tmp_path):
    _seed_relocated_gemini_skill(tmp_path)
    body = (
        "function Get-PluginKeysGlobal { @() }\n"
        "$script:Scope = 'global'; $script:UninstallSkillNames = @('databricks-jobs')\n"
        "Test-PriorInstall\n$script:PriorInstallKind\n"
    )
    names = ["Get-GeminiGlobalSkillsDir", "Get-GeminiRelocatedSkillsDir", "Test-PriorInstall"]
    result = _run_pwsh(tmp_path, names, body, {"GEMINI_CLI_HOME": str(tmp_path / "gem")})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "legacy-skills"


@needs_pwsh
@pytest.mark.parametrize(
    "version,expected",
    [
        ("0.200.0", "Databricks CLI v0.200.0 is outdated (minimum: v0.278.0)"),
        ("1.20.0", "Databricks CLI v1.20.0"),
        (None, "Could not determine Databricks CLI version"),
        # a component past Int32 makes the [version] cast throw under EAP=Stop
        ("99999999999.0.0", "Could not determine Databricks CLI version"),
    ],
)
def test_install_ps1_test_dependencies_reports_cli_version(tmp_path, version, expected):
    # None = a CLI whose --version has no semver at all
    _stub_cli(tmp_path, None, f'#!/bin/sh\necho "Databricks CLI v{version}"\n' if version else "#!/bin/sh\necho dev\n")
    names = ["Write-Msg", "Write-Ok", "Write-Warn", "Write-Err", "Get-DatabricksCliVersion", "Test-Dependencies"]
    result = _run_pwsh(tmp_path, names, '$MinCliVersion = "0.278.0"\nTest-Dependencies\n')
    assert result.returncode == 0, result.stderr
    assert expected in ANSI.sub("", result.stdout)
