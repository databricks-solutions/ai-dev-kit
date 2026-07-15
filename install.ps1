#
# Databricks AI Dev Kit - Unified Installer (Windows)
#
# Installs skills, MCP server, and configuration for Claude Code, Cursor, OpenAI Codex, GitHub Copilot, Gemini CLI, Antigravity, Windsurf, OpenCode, and Kiro.
#
# Usage: irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 -OutFile install.ps1
#        .\install.ps1 [OPTIONS]
#
# Examples:
#   # Basic installation (uses DEFAULT profile, project scope, latest release)
#   irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 | iex
#
#   # Download and run with options
#   irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 -OutFile install.ps1
#
#   # Global installation with force reinstall
#   .\install.ps1 -Global -Force
#
#   # Specify profile and force reinstall
#   .\install.ps1 -Profile DEFAULT -Force
#
#   # Install for specific tools only
#   .\install.ps1 -Tools cursor
#
#   # Skills only (skip MCP server)
#   .\install.ps1 -SkillsOnly
#
#   # Install specific branch or tag
#   $env:AIDEVKIT_BRANCH = '0.1.0'; .\install.ps1
#

$ErrorActionPreference = "Stop"

# ─── Configuration ────────────────────────────────────────────
$Owner = "databricks-solutions"
$Repo  = "ai-dev-kit"

# Determine branch/tag to use. AIDEVKIT_BRANCH is canonical here; DEVKIT_BRANCH
# is accepted as an alias so the bash and PowerShell installers honor the same var.
# $script:BranchExplicit tracks whether the user asked for a specific ref (vs the
# auto-resolved latest release) — an explicit ref triggers the branch hand-off.
$script:BranchExplicit = [bool]($env:AIDEVKIT_BRANCH -or $env:DEVKIT_BRANCH)
if ($env:AIDEVKIT_BRANCH -or $env:DEVKIT_BRANCH) {
    $Branch = if ($env:AIDEVKIT_BRANCH) { $env:AIDEVKIT_BRANCH } else { $env:DEVKIT_BRANCH }
} else {
    try {
        $latestReleaseUri = "https://api.github.com/repos/$Owner/$Repo/releases/latest"
        $latestRelease = Invoke-WebRequest -Uri $latestReleaseUri -Headers @{ "Accept" = "application/json" } -UseBasicParsing -ErrorAction Stop
        $Branch = ($latestRelease.Content | ConvertFrom-Json).tag_name
    } catch {
        $Branch = "main"
    }
}

$RepoUrl   = "https://github.com/$Owner/$Repo.git"
$RawUrl    = "https://raw.githubusercontent.com/$Owner/$Repo/$Branch"
$InstallDir = if ($env:AIDEVKIT_HOME) { $env:AIDEVKIT_HOME } else { Join-Path $env:USERPROFILE ".ai-dev-kit" }
$RepoDir   = Join-Path $InstallDir "repo"
$VenvDir   = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$McpEntry  = Join-Path $RepoDir "databricks-mcp-server\run_server.py"

# Minimum required versions
$MinCliVersion = "0.278.0"
# (MCP server SDK minimum is enforced by databricks-mcp-server/setup.ps1)
# Agent skills are delegated to `databricks aitools`, which ships with CLI v1.0.0+
$MinAitoolsCliVersion = "1.0.0"

# ─── Defaults ─────────────────────────────────────────────────
# DEVKIT_* env vars mirror the bash installer so both honor the same config.
$script:Profile_     = if ($env:DEVKIT_PROFILE) { $env:DEVKIT_PROFILE } else { "DEFAULT" }
$script:Scope        = if ($env:DEVKIT_SCOPE) { $env:DEVKIT_SCOPE } else { "project" }
$script:ScopeExplicit = [bool]$env:DEVKIT_SCOPE  # Track if scope was explicitly set
# The MCP server is deprecated/optional — skills work via the Databricks CLI, so
# MCP defaults OFF and is opt-in (-Mcp / --mcp / DEVKIT_INSTALL_MCP=true). When
# opted in, the venv build is delegated to databricks-mcp-server/setup.ps1.
$script:InstallSkills = $true
$script:InstallMcp   = ($env:DEVKIT_INSTALL_MCP -in @("true", "1"))
$script:Force        = ($env:DEVKIT_FORCE -in @("true", "1"))
$script:Silent       = ($env:DEVKIT_SILENT -in @("true", "1"))
$script:UserTools    = if ($env:DEVKIT_TOOLS) { $env:DEVKIT_TOOLS } else { "" }
$script:Tools        = ""
$script:UserMcpPath  = if ($env:DEVKIT_MCP_PATH) { $env:DEVKIT_MCP_PATH } else { "" }
$script:ProfileProvided = [bool]$env:DEVKIT_PROFILE
$script:SkillsProfile = if ($env:DEVKIT_SKILLS_PROFILE) { $env:DEVKIT_SKILLS_PROFILE } else { "" }
$script:UserSkills   = if ($env:DEVKIT_SKILLS) { $env:DEVKIT_SKILLS } else { "" }
$script:ListSkills   = $false
$script:DryRun       = ($env:DRY_RUN -in @("true", "1"))
$script:Uninstall    = $false
$script:AssumeYes    = $false
# Include experimental agent skills in profile/"all" selections (default: true).
# Pass --experimental false (or DEVKIT_EXPERIMENTAL=false) for stable only.
# Explicit --skills requests are always honored as named.
$script:InstallExperimental = ($env:DEVKIT_EXPERIMENTAL -notin @("false", "0"))

# -McpPath / DEVKIT_MCP_PATH implies opting into the MCP server
if ($script:UserMcpPath) { $script:InstallMcp = $true }

# Raw-fetch ref override for MLflow skills (mlflow/skills is tagless -- main is intentional)
$script:MlflowRef = if ($env:MLFLOW_REF) { $env:MLFLOW_REF } else { "main" }
$script:IncludePrereleases = ($env:INCLUDE_PRERELEASES -in @("true", "1"))

# MLflow skills (fetched from mlflow/skills repo; MLFLOW_REF defaults to main -- the repo is tagless)
$script:MlflowSkills = @(
    "agent-evaluation", "analyze-mlflow-chat-session", "analyze-mlflow-trace",
    "instrumenting-with-mlflow-tracing", "mlflow-onboarding", "querying-mlflow-metrics",
    "retrieving-mlflow-traces", "searching-mlflow-docs"
)
$MlflowBaseUrl = "https://raw.githubusercontent.com/mlflow/skills"

# Agent skills (from databricks/databricks-agent-skills, installed and managed by
# `databricks aitools`, which ships with the Databricks CLI v1.0.0+).
# The live inventory is discovered at runtime via `databricks aitools list -o json`
# (see Get-AgentBInventory); these lists are the fallback snapshot (v0.2.3).
$script:AgentBStableFallback = @(
    "databricks-apps", "databricks-core", "databricks-dabs", "databricks-jobs",
    "databricks-lakebase", "databricks-model-serving", "databricks-pipelines",
    "databricks-serverless-migration", "databricks-vector-search"
)
$script:AgentBExperimentalFallback = @(
    "databricks-agent-bricks", "databricks-ai-functions", "databricks-aibi-dashboards",
    "databricks-apps-python", "databricks-dbsql", "databricks-docs",
    "databricks-execution-compute", "databricks-genie", "databricks-iceberg", "databricks-lakeflow-connect",
    "databricks-metric-views", "databricks-mlflow-evaluation", "databricks-python-sdk",
    "databricks-spark-structured-streaming", "databricks-synthetic-data-gen",
    "databricks-unity-catalog", "databricks-unstructured-pdf-generation",
    "databricks-zerobus-ingest", "spark-python-data-source"
)
# Skills never installed by default (excluded from "all" and profile selections;
# still installable via an explicit --skills request)
$script:AgentBExcluded = @("databricks-execution-compute")
# Populated by Get-AgentBInventory (live or fallback)
$script:AgentBStable = @()
$script:AgentBExperimental = @()
$script:AgentBRelease = ""

# Old skill names -> new names (breaking rename when sourcing moved to
# databricks-agent-skills). Explicit requests for old names are migrated with a warning.
$script:RenamedSkills = @{
    "databricks-bundles"                     = "databricks-dabs"
    "databricks-spark-declarative-pipelines" = "databricks-pipelines"
    "databricks-config"                      = "databricks-core"
    "databricks"                             = "databricks-core"
    "databricks-lakebase-autoscale"          = "databricks-lakebase"
    "databricks-lakebase-provisioned"        = "databricks-lakebase"
}

# ─── Skill profiles ──────────────────────────────────────────
# Core skills always installed regardless of profile selection (all from databricks-agent-skills)
$script:CoreSkills = @("databricks-core", "databricks-docs", "databricks-python-sdk", "databricks-unity-catalog")

# Profile definitions (non-core skills only -- core skills are always added).
# Names may come from any source; Resolve-Skills buckets them.
$script:ProfileDataEngineer = @(
    "databricks-pipelines", "databricks-spark-structured-streaming", "databricks-jobs",
    "databricks-dabs", "databricks-dbsql", "databricks-iceberg", "databricks-lakeflow-connect",
    "databricks-zerobus-ingest", "spark-python-data-source", "databricks-metric-views",
    "databricks-synthetic-data-gen"
)
$script:ProfileAnalyst = @(
    "databricks-aibi-dashboards", "databricks-dbsql", "databricks-genie", "databricks-metric-views"
)
$script:ProfileAiMlEngineer = @(
    "databricks-agent-bricks", "databricks-ai-functions", "databricks-vector-search",
    "databricks-model-serving", "databricks-genie", "databricks-unstructured-pdf-generation",
    "databricks-mlflow-evaluation", "databricks-synthetic-data-gen", "databricks-jobs"
)
$script:ProfileAiMlMlflow = @(
    "agent-evaluation", "analyze-mlflow-chat-session", "analyze-mlflow-trace",
    "instrumenting-with-mlflow-tracing", "mlflow-onboarding", "querying-mlflow-metrics",
    "retrieving-mlflow-traces", "searching-mlflow-docs"
)
$script:ProfileAppDeveloper = @(
    "databricks-apps", "databricks-apps-python", "databricks-lakebase",
    "databricks-model-serving", "databricks-dbsql", "databricks-jobs", "databricks-dabs"
)

# Selected skills (populated during profile selection)
$script:SelectedMlflowSkills = @()
$script:SelectedAgentBSkills = @()

# Resolved raw-fetch refs (populated by Resolve-FetchRefs)
$script:MlflowResolvedRef = ""

# aitools agent mapping (populated by Resolve-AitoolsAgents)
$script:AitoolsAgents = ""

# ─── --list-skills handler ────────────────────────────────────
# (function -- needs Get-AgentBInventory; invoked from Invoke-Main)

# Number of skills the "all" profile installs (excluded agent skills omitted)
function Get-AllSkillsCount {
    $n = $script:MlflowSkills.Count +
         $script:AgentBStable.Count + $script:AgentBExperimental.Count
    foreach ($skill in $script:AgentBExcluded) {
        if (($script:AgentBStable -contains $skill) -or ($script:AgentBExperimental -contains $skill)) { $n-- }
    }
    return $n
}

function Show-SkillsList {
    Get-AgentBInventory

    $allCount = Get-AllSkillsCount
    $deCount = $script:CoreSkills.Count + $script:ProfileDataEngineer.Count
    $anCount = $script:CoreSkills.Count + $script:ProfileAnalyst.Count
    $aiCount = $script:CoreSkills.Count + $script:ProfileAiMlEngineer.Count + $script:ProfileAiMlMlflow.Count
    $apCount = $script:CoreSkills.Count + $script:ProfileAppDeveloper.Count

    Write-Host ""
    Write-Host "Available Skill Profiles" -ForegroundColor White
    Write-Host "--------------------------------"
    Write-Host ""
    Write-Host "  all              " -ForegroundColor White -NoNewline; Write-Host "All $allCount skills (default)"
    Write-Host "  data-engineer    " -ForegroundColor White -NoNewline; Write-Host "Pipelines, Spark, Jobs, Streaming ($deCount skills)"
    Write-Host "  analyst          " -ForegroundColor White -NoNewline; Write-Host "Dashboards, SQL, Genie, Metrics ($anCount skills)"
    Write-Host "  ai-ml-engineer   " -ForegroundColor White -NoNewline; Write-Host "Agents, RAG, Vector Search, MLflow ($aiCount skills)"
    Write-Host "  app-developer    " -ForegroundColor White -NoNewline; Write-Host "Apps, Lakebase, Deployment ($apCount skills)"
    Write-Host ""
    Write-Host "Core Skills (always installed)" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:CoreSkills) { Write-Host "  " -NoNewline; Write-Host "v" -ForegroundColor Green -NoNewline; Write-Host " $s" }
    Write-Host ""
    Write-Host "Data Engineer" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:ProfileDataEngineer) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "Business Analyst" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:ProfileAnalyst) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "AI/ML Engineer" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:ProfileAiMlEngineer) { Write-Host "    $s" }
    Write-Host "  + MLflow skills:" -ForegroundColor DarkGray
    foreach ($s in $script:ProfileAiMlMlflow) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "App Developer" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:ProfileAppDeveloper) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "MLflow Skills (from mlflow/skills repo @ $($script:MlflowRef))" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:MlflowSkills) { Write-Host "    $s" }
    Write-Host ""
    $releaseSuffix = if ($script:AgentBRelease) { " @ $($script:AgentBRelease)" } else { "" }
    Write-Host "Agent Skills (from databricks/databricks-agent-skills$releaseSuffix -- managed by databricks aitools)" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:AgentBStable) { Write-Host "    $s" }
    Write-Host "  experimental:" -ForegroundColor DarkGray
    foreach ($s in $script:AgentBExperimental) {
        if ($script:AgentBExcluded -contains $s) {
            Write-Host "    $s (excluded by default -- request explicitly via --skills)" -ForegroundColor DarkGray
        } else {
            Write-Host "    $s"
        }
    }
    Write-Host ""
    Write-Host "Usage: .\install.ps1 --skills-profile data-engineer,ai-ml-engineer" -ForegroundColor DarkGray
    Write-Host "       .\install.ps1 --skills databricks-jobs,databricks-dbsql" -ForegroundColor DarkGray
    Write-Host ""
}

# ─── Ensure tools are in PATH ────────────────────────────────
# Chocolatey-installed tools may not be in PATH for SSH sessions
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath    = [System.Environment]::GetEnvironmentVariable("Path", "User")
if ($machinePath -or $userPath) {
    $env:Path = "$machinePath;$userPath;$env:Path"
    # Deduplicate
    $env:Path = (($env:Path -split ';' | Select-Object -Unique | Where-Object { $_ }) -join ';')
}

# ─── Output helpers ───────────────────────────────────────────
function Write-Msg  { param([string]$Text) if (-not $script:Silent) { Write-Host "  $Text" } }
function Write-Ok   { param([string]$Text) if (-not $script:Silent) { Write-Host "  " -NoNewline; Write-Host "v" -ForegroundColor Green -NoNewline; Write-Host " $Text" } }
function Write-Warn { param([string]$Text) if (-not $script:Silent) { Write-Host "  " -NoNewline; Write-Host "!" -ForegroundColor Yellow -NoNewline; Write-Host " $Text" } }
function Write-Err  {
    param([string]$Text)
    Write-Host "  " -NoNewline; Write-Host "x" -ForegroundColor Red -NoNewline; Write-Host " $Text"
    Write-Host ""
    Write-Host "  Press any key to exit..." -ForegroundColor DarkGray
    try { $null = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") } catch {}
    exit 1
}
function Write-Step { param([string]$Text) if (-not $script:Silent) { Write-Host ""; Write-Host "$Text" -ForegroundColor White } }

# Deprecation notice - shown on every install/upgrade while skills still ship
# from this repo. The next major release installs skills via the Databricks CLI
# from the official databricks/databricks-agent-skills set.
function Show-DeprecationNotice {
    if ($script:Silent) { return }
    $bar = "  ------------------------------------------------------------"
    Write-Host ""
    Write-Host $bar -ForegroundColor Yellow
    Write-Host "  !  Heads up: skills are moving" -ForegroundColor Yellow
    Write-Host "  In the next release, the skills for AI Dev Kit will be" -ForegroundColor DarkGray
    Write-Host "  promoted to a shared, engineering-supported repository." -ForegroundColor DarkGray
    Write-Host "  In future releases, this installer will set up skills" -ForegroundColor DarkGray
    Write-Host "  using the Databricks CLI." -ForegroundColor DarkGray
    Write-Host $bar -ForegroundColor Yellow
}

# ─── Parse arguments ─────────────────────────────────────────
$i = 0
while ($i -lt $args.Count) {
    switch ($args[$i]) {
        { $_ -in "-b", "--branch", "-Branch" } { $Branch = $args[$i + 1]; $script:BranchExplicit = $true; $RawUrl = "https://raw.githubusercontent.com/$Owner/$Repo/$Branch"; $i += 2 }
        { $_ -in "-p", "--profile" }  { $script:Profile_ = $args[$i + 1]; $script:ProfileProvided = $true; $i += 2 }
        { $_ -in "-g", "--global", "-Global" }  { $script:Scope = "global"; $script:ScopeExplicit = $true; $i++ }
        { $_ -in "--skills-only", "-SkillsOnly" } { $script:InstallMcp = $false; $i++ }
        { $_ -in "--mcp", "-Mcp" }              { $script:InstallMcp = $true; $i++ }
        { $_ -in "--mcp-only", "-McpOnly" }    { $script:InstallSkills = $false; $script:InstallMcp = $true; $i++ }
        { $_ -in "--mcp-path", "-McpPath" }    { $script:UserMcpPath = $args[$i + 1]; $script:InstallMcp = $true; $i += 2 }
        { $_ -in "--silent", "-Silent" }       { $script:Silent = $true; $i++ }
        { $_ -in "--tools", "-Tools" }         { $script:UserTools = $args[$i + 1]; $i += 2 }
        { $_ -in "--skills-profile", "-SkillsProfile" } { $script:SkillsProfile = $args[$i + 1]; $i += 2 }
        { $_ -in "--skills", "-Skills" }       { $script:UserSkills = $args[$i + 1]; $i += 2 }
        { $_ -in "--list-skills", "-ListSkills" } { $script:ListSkills = $true; $i++ }
        { $_ -in "--experimental", "-Experimental" } {
            switch ("$($args[$i + 1])".ToLower()) {
                { $_ -in "false", "0" } { $script:InstallExperimental = $false; $i += 2 }
                { $_ -in "true", "1" }  { $script:InstallExperimental = $true; $i += 2 }
                default                 { $script:InstallExperimental = $true; $i++ }
            }
        }
        { $_ -in "--dry-run", "-DryRun" }      { $script:DryRun = $true; $i++ }
        { $_ -in "-f", "--force", "-Force" }   { $script:Force = $true; $i++ }
        { $_ -in "--uninstall", "-Uninstall" } { $script:Uninstall = $true; $i++ }
        { $_ -in "-y", "--yes", "-Yes" }       { $script:AssumeYes = $true; $i++ }
        { $_ -in "-h", "--help", "-Help" } {
            Write-Host "Databricks AI Dev Kit Installer (Windows)"
            Write-Host ""
            Write-Host "Usage: irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 -OutFile install.ps1"
            Write-Host "       .\install.ps1 [OPTIONS]"
            Write-Host ""
            Write-Host "Options:"
            Write-Host "  -b, --branch NAME     Install a specific release/branch (runs that version's own installer)"
            Write-Host "  -p, --profile NAME    Databricks profile (default: DEFAULT)"
            Write-Host "  -g, --global          Install globally for all projects"
            Write-Host "  --skills-only         Install skills only (default; MCP server is opt-in)"
            Write-Host "  --mcp                 Install the deprecated MCP server (default: no)"
            Write-Host "  --mcp-only            Install the MCP server only, skip skills"
            Write-Host "  --mcp-path PATH       MCP server install path (implies --mcp)"
            Write-Host "  --silent              Silent mode (no output except errors)"
            Write-Host "  --tools LIST          Comma-separated: claude,cursor,copilot,codex,gemini,antigravity,windsurf,opencode,kiro"
            Write-Host "  --skills-profile LIST Comma-separated profiles: all,data-engineer,analyst,ai-ml-engineer,app-developer"
            Write-Host "  --skills LIST         Comma-separated skill names to install (overrides profile)"
            Write-Host "  --list-skills         List available skills and profiles, then exit"
            Write-Host "  --experimental BOOL   Include experimental agent skills (default: true; 'false' = stable only)"
            Write-Host "  --dry-run             Print what would be installed (resolved refs, aitools command) and exit"
            Write-Host "  -f, --force           Force reinstall"
            Write-Host "  --uninstall           Remove AI Dev Kit: skills, MCP server runtime, MCP config, and Claude Code plugin"
            Write-Host "  --dry-run             With --uninstall: print what would be removed, change nothing"
            Write-Host "  -y, --yes             With --uninstall: skip the confirmation prompt"
            Write-Host "  -h, --help            Show this help"
            Write-Host ""
            Write-Host "Environment Variables:"
            Write-Host "  AIDEVKIT_BRANCH       Branch or tag to install (alias: DEVKIT_BRANCH; default: latest release)"
            Write-Host "  AIDEVKIT_HOME         Installation directory (default: ~/.ai-dev-kit)"
            Write-Host "  DEVKIT_INSTALL_MCP    Set to 'true' to install the deprecated MCP server (default: false)"
            Write-Host "  DEVKIT_PROFILE/SCOPE/TOOLS/SKILLS/SKILLS_PROFILE/MCP_PATH/FORCE/SILENT  (mirror the bash installer)"
            Write-Host "  DEVKIT_EXPERIMENTAL   'true' (default) or 'false' to skip experimental agent skills"
            Write-Host "  MLFLOW_REF            Ref for MLflow skills fetch (default: main)"
            Write-Host "  DRY_RUN               Set to '1' to print the install plan and exit"
            Write-Host ""
            Write-Host "Notes:"
            Write-Host "  Most Databricks skills are installed via 'databricks aitools' (Databricks CLI v1.0.0+)"
            Write-Host "  and are updated/uninstalled with 'databricks aitools update|uninstall', not this script."
            Write-Host "  The MCP server is deprecated/optional — skills work without it. Opt in with --mcp."
            Write-Host "  Renamed skills: databricks-bundles -> databricks-dabs,"
            Write-Host "  databricks-spark-declarative-pipelines -> databricks-pipelines."
            Write-Host "  Replaced skills: databricks-config -> databricks-core,"
            Write-Host "  databricks-lakebase-autoscale/provisioned -> databricks-lakebase."
            Write-Host ""
            Write-Host "Examples:"
            Write-Host "  # Basic installation"
            Write-Host "  irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 | iex"
            Write-Host ""
            Write-Host "  # Download and run with options"
            Write-Host "  irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 -OutFile install.ps1"
            Write-Host "  .\install.ps1 -Global -Force"
            Write-Host ""
            Write-Host "  # Specify profile and force reinstall"
            Write-Host "  .\install.ps1 -Profile DEFAULT -Force"
            return
        }
        default { Write-Err "Unknown option: $($args[$i]) (use -h for help)"; $i++ }
    }
}

# ─── --uninstall ───────────────────────────────────────────────
# Every skill directory name ever shipped (current + historical renames/removals),
# so old installs — e.g. the removed databricks-lakebase-provisioned or renamed
# databricks-app-python — are swept, not just the current release's skills.
$script:UninstallSkillNames = @(
    "databricks-agent-bricks","databricks-ai-functions","databricks-aibi-dashboards",
    "databricks-bundles","databricks-asset-bundles","databricks-apps-python","databricks-app-python",
    "databricks-app-apx","databricks-config","databricks-dbsql","databricks-docs",
    "databricks-execution-compute","databricks-genie","databricks-iceberg","databricks-jobs",
    "databricks-lakebase-autoscale","databricks-lakebase-provisioned","databricks-metric-views",
    "databricks-ml-training-serving","databricks-model-serving","databricks-mlflow-evaluation",
    "databricks-parsing","databricks-python-sdk","databricks-spark-declarative-pipelines",
    "databricks-spark-structured-streaming","databricks-synthetic-data-gen","databricks-synthetic-data-generation",
    "databricks-unity-catalog","databricks-unstructured-pdf-generation","databricks-vector-search",
    "databricks-zerobus-ingest","spark-python-data-source",
    "databricks","databricks-apps","databricks-lakebase",
    "agent-evaluation","analyze-mlflow-chat-session","analyze-mlflow-trace",
    "instrumenting-with-mlflow-tracing","mlflow-onboarding","querying-mlflow-metrics",
    "retrieving-mlflow-traces","searching-mlflow-docs"
)

# The Claude Code plugin (installed via a marketplace, separate from the skills
# this script drops directly). Its on-disk state lives across several shared files
# (installed_plugins.json, enabledPlugins in settings.json, known_marketplaces.json,
# the cache dir) shared with the user's OTHER plugins — so we never hand-edit them.
# Detection is read-only; removal is delegated to the official `claude` CLI.
#
# The plugin can be installed from ANY marketplace, so we match by plugin name and
# discover the actual "name@marketplace" key(s) rather than assuming a marketplace.
$script:PluginName = "databricks-ai-dev-kit"

# Read-only detection of the plugin per scope. The scope is recorded by which
# settings.json enables it: user scope in ~/.claude/settings.json, project scope in
# the project's .claude/settings.json(.local). (installed_plugins.json is user-level
# and lists ALL scopes together, so it can't distinguish them.) Returns the enabled
# "name@marketplace" key(s) — any marketplace is matched.
function Get-PluginKeys {
    param([string[]]$Files)
    $pattern = '"' + [regex]::Escape($script:PluginName) + '@[A-Za-z0-9._-]+"'
    $keys = @()
    foreach ($f in $Files) {
        if (Test-Path $f) {
            foreach ($m in [regex]::Matches((Get-Content $f -Raw), $pattern)) { $keys += $m.Value.Trim('"') }
        }
    }
    return @($keys | Sort-Object -Unique)
}
function Get-PluginKeysGlobal { Get-PluginKeys -Files @((Join-Path $env:USERPROFILE ".claude\settings.json")) }
function Get-PluginKeysProject { param([string]$Dir) Get-PluginKeys -Files @((Join-Path $Dir ".claude\settings.json"), (Join-Path $Dir ".claude\settings.local.json")) }

# Count skill folders + 'databricks' MCP entries under the given roots/targets, plus
# hook/state/plugin, returning one "  - ..." summary line each. Shared by the project-
# and global-scope summaries below. Read-only.
function Get-LeftoversSummary {
    param([string]$Hook, [string]$StateDir, [string]$StateLabel, [string[]]$PluginKeys, [string[]]$SkillRoots, [hashtable[]]$McpTargets)
    $lines = @()
    $n = 0
    foreach ($root in $SkillRoots) {
        if (Test-Path $root) { foreach ($name in $script:UninstallSkillNames) { if (Test-Path (Join-Path $root $name)) { $n++ } } }
    }
    if ($n -gt 0) { $lines += "  - $n skill folder(s)" }
    $n = 0
    foreach ($t in $McpTargets) {
        if (-not (Test-Path $t.Path)) { continue }
        if ($t.Kind -eq "json" -and (Test-McpJsonHasDatabricks -Path $t.Path -Top $t.Top)) { $n++ }
        elseif ($t.Kind -eq "toml" -and (Select-String -Path $t.Path -Pattern 'mcp_servers\.databricks' -Quiet)) { $n++ }
    }
    if ($n -gt 0) { $lines += "  - $n MCP config file(s) with the 'databricks' server" }
    if ($Hook -and (Test-Path $Hook) -and (Select-String -Path $Hook -Pattern 'check_update' -Quiet)) { $lines += "  - Claude update hook" }
    if ($StateDir -and (Test-Path $StateDir)) { $lines += "  - $StateLabel" }
    if ($PluginKeys.Count -gt 0) { $lines += "  - Claude Code plugin: $($PluginKeys -join ' ')" }
    return @($lines)
}

# Project-scope artifacts under $Dir (what a project uninstall from that dir removes).
function Get-ProjectLeftoversSummary {
    param([string]$Dir)
    $skillRoots = @("\.claude\skills","\.cursor\skills","\.github\skills","\.agents\skills","\.gemini\skills","\.windsurf\skills","\.opencode\skills","\.kiro\skills") | ForEach-Object { Join-Path $Dir $_.TrimStart('\') }
    $mcpTargets = @(
        @{ Path=(Join-Path $Dir ".mcp.json"); Kind="json"; Top="mcpServers" }, @{ Path=(Join-Path $Dir ".cursor\mcp.json"); Kind="json"; Top="mcpServers" }, @{ Path=(Join-Path $Dir ".vscode\mcp.json"); Kind="json"; Top="servers" },
        @{ Path=(Join-Path $Dir ".codex\config.toml"); Kind="toml" }, @{ Path=(Join-Path $Dir ".gemini\settings.json"); Kind="json"; Top="mcpServers" },
        @{ Path=(Join-Path $Dir "opencode.json"); Kind="json"; Top="mcp" }, @{ Path=(Join-Path $Dir ".kiro\settings\mcp.json"); Kind="json"; Top="mcpServers" }
    )
    Get-LeftoversSummary -Hook (Join-Path $Dir ".claude\settings.json") -StateDir (Join-Path $Dir ".ai-dev-kit") -StateLabel "state files (.ai-dev-kit/)" `
        -PluginKeys (Get-PluginKeysProject -Dir $Dir) -SkillRoots $skillRoots -McpTargets $mcpTargets
}

# Global/user-scope artifacts (what a --global uninstall removes).
function Get-GlobalLeftoversSummary {
    $h = $env:USERPROFILE
    $installDir = if ($script:UserMcpPath) { $script:UserMcpPath } elseif ($env:AIDEVKIT_HOME) { $env:AIDEVKIT_HOME } else { Join-Path $h ".ai-dev-kit" }
    $skillRoots = @(".claude\skills",".cursor\skills",".github\skills",".agents\skills",".gemini\skills",".gemini\antigravity\skills",".codeium\windsurf\skills",".config\opencode\skills",".kiro\skills") | ForEach-Object { Join-Path $h $_ }
    $mcpTargets = @(
        @{ Path=(Join-Path $h ".claude.json"); Kind="json"; Top="mcpServers" }, @{ Path=(Join-Path $h ".codex\config.toml"); Kind="toml" }, @{ Path=(Join-Path $h ".gemini\settings.json"); Kind="json"; Top="mcpServers" },
        @{ Path=(Join-Path $h ".gemini\antigravity\mcp_config.json"); Kind="json"; Top="mcpServers" }, @{ Path=(Join-Path $h ".codeium\windsurf\mcp_config.json"); Kind="json"; Top="mcpServers" },
        @{ Path=(Join-Path $h ".config\opencode\opencode.json"); Kind="json"; Top="mcp" }, @{ Path=(Join-Path $h ".kiro\settings\mcp.json"); Kind="json"; Top="mcpServers" }
    )
    Get-LeftoversSummary -Hook (Join-Path $h ".claude\settings.json") -StateDir $installDir -StateLabel "MCP server runtime / state ($installDir)" `
        -PluginKeys (Get-PluginKeysGlobal) -SkillRoots $skillRoots -McpTargets $mcpTargets
}

# Very noticeable end-of-run box warning that files remain in the OTHER scope.
function Show-LeftoversBox {
    param([string]$Headline, [string]$Detail, [string[]]$Summary, [string]$Action)
    $bar = "  ------------------------------------------------------------"
    Write-Host ""
    Write-Host $bar -ForegroundColor Yellow
    Write-Host "  $Headline" -ForegroundColor Yellow
    Write-Host $bar -ForegroundColor Yellow
    Write-Host "  $Detail" -ForegroundColor DarkGray
    foreach ($l in $Summary) { Write-Host $l }
    Write-Host "  $Action" -ForegroundColor Yellow
    Write-Host $bar -ForegroundColor Yellow
}
function Show-ProjectLeftoversWarning {
    param([string]$Dir, [string[]]$Summary)
    Show-LeftoversBox -Headline "!  PROJECT-LEVEL AI DEV KIT FILES STILL REMAIN" `
        -Detail "This global uninstall did not touch project-scoped files in: $Dir" `
        -Summary $Summary -Action "Re-run the uninstaller from that folder WITHOUT --global to remove them."
}
function Show-GlobalLeftoversWarning {
    param([string[]]$Summary)
    Show-LeftoversBox -Headline "!  GLOBAL AI DEV KIT FILES STILL REMAIN" `
        -Detail "This project uninstall did not touch global (user-level) files:" `
        -Summary $Summary -Action "Re-run the uninstaller with --global to remove them."
}

# Remove the plugin from the CURRENT uninstall scope via the official CLI (atomic
# across the shared plugin state - we never hand-edit it). Removes every detected
# "name@marketplace" key (the plugin may come from any marketplace). A project
# install can be 'project' (.claude/settings.json) or 'local' (settings.local.json),
# so a project uninstall tries both CLI scopes. If nothing could be removed this is a
# hard error that reports whether the rest of the uninstall completed and prints the
# exact command to run manually. $OthersRemoved = other artifacts removed this run.
function Remove-ClaudePlugin {
    param([int]$OthersRemoved, [string[]]$Keys)
    if ($script:Scope -eq "project") { $scopes = @("project","local"); $cmdScope = "project" }
    else { $scopes = @("user"); $cmdScope = "user" }
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        $removed = $false
        foreach ($k in $Keys) {
            foreach ($sc in $scopes) {
                # Subcommand name has varied across versions (uninstall vs remove) — try both.
                & claude plugin uninstall $k -y --scope $sc *>$null
                if ($LASTEXITCODE -ne 0) { & claude plugin remove $k -y --scope $sc *>$null }
                if ($LASTEXITCODE -eq 0) { Write-Msg "removed Claude Code plugin $k ($sc scope)"; $removed = $true }
            }
        }
        if ($removed) { return }
    }
    $partial = ""; $alt = ""
    if ($OthersRemoved -gt 0) { $partial = "Skills, MCP server, and config WERE removed (partial uninstall). " }
    if ($script:Scope -eq "project") { $alt = " (or --scope local)" }
    $manual = (($Keys | ForEach-Object { "claude plugin uninstall $_ --scope $cmdScope" }) -join "; ")
    Write-Err "Could not remove the Claude Code plugin. ${partial}Finish it manually: $manual$alt"
}

# Read-only: true only if the EXACT top-level server key ($Top) contains a
# 'databricks' entry - the same thing removal targets. Does NOT match nested
# occurrences (e.g. ~/.claude.json's projects.<path>.mcpServers.databricks, a
# project-scoped server we never touch) that a plain match would flag.
function Test-McpJsonHasDatabricks {
    param([string]$Path, [string]$Top)
    if (-not (Test-Path $Path)) { return $false }
    try { $cfg = Get-Content $Path -Raw | ConvertFrom-Json } catch { return $false }
    return ($cfg.$Top -and $cfg.$Top.PSObject.Properties.Name -contains 'databricks')
}

function Remove-McpJsonKey {
    param([string]$Path, [string]$Top)
    if (-not (Test-Path $Path)) { return $false }
    if (-not (Select-String -Path $Path -Pattern '"databricks"' -Quiet)) { return $false }
    if ($script:DryRun) { return $true }
    try { $cfg = Get-Content $Path -Raw | ConvertFrom-Json } catch { return $false }
    # Only rewrite (and back up) when the exact top-level 'databricks' key is
    # present. Otherwise a stray '"databricks"' elsewhere (a foreign server's
    # path, a project named 'databricks') would trigger a lossy no-op rewrite —
    # and ConvertTo-Json's -Depth would truncate deep configs like ~/.claude.json.
    if (-not ($cfg.$Top -and $cfg.$Top.PSObject.Properties.Name -contains 'databricks')) {
        return $false
    }
    Copy-Item $Path "$Path.bak" -Force
    $cfg.$Top.PSObject.Properties.Remove('databricks')
    if (-not $cfg.$Top.PSObject.Properties.Name) { $cfg.PSObject.Properties.Remove($Top) }
    $cfg | ConvertTo-Json -Depth 100 | Set-Content $Path -Encoding UTF8
    return $true
}

function Remove-McpTomlBlock {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    if (-not (Select-String -Path $Path -Pattern 'mcp_servers\.databricks' -Quiet)) { return $false }
    if ($script:DryRun) { return $true }
    Copy-Item $Path "$Path.bak" -Force
    $out = New-Object System.Collections.Generic.List[string]
    $skip = $false
    foreach ($line in Get-Content "$Path.bak") {
        # Consume the databricks table AND its dotted subtables (e.g. .env);
        # any other section header ends the skip.
        if ($line -match '^\[mcp_servers\.databricks(\.|\])') { $skip = $true; continue }
        if ($line -match '^\[') { $skip = $false }
        if (-not $skip) { $out.Add($line) }
    }
    $out | Set-Content $Path -Encoding UTF8
    return $true
}

function Remove-ClaudeHook {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    if (-not (Select-String -Path $Path -Pattern 'check_update' -Quiet)) { return $false }
    if ($script:DryRun) { return $true }
    try { $cfg = Get-Content $Path -Raw | ConvertFrom-Json } catch { return $false }
    $ss = $cfg.hooks.SessionStart
    if (-not $ss) { return $false }   # nothing to change — don't rewrite/back up
    foreach ($group in $ss) {
        $group.hooks = @($group.hooks | Where-Object { $_.command -notmatch 'check_update' })
    }
    $cfg.hooks.SessionStart = @($ss | Where-Object { $_.hooks -and $_.hooks.Count -gt 0 })
    if (-not $cfg.hooks.SessionStart -or $cfg.hooks.SessionStart.Count -eq 0) {
        $cfg.hooks.PSObject.Properties.Remove('SessionStart')
    }
    Copy-Item $Path "$Path.bak" -Force
    $cfg | ConvertTo-Json -Depth 100 | Set-Content $Path -Encoding UTF8
    return $true
}

function Invoke-Uninstall {
    $home_ = $env:USERPROFILE
    if ($script:Scope -eq "global") { $baseDir = $home_ } else { $baseDir = (Get-Location).Path }
    $installDir = if ($script:UserMcpPath) { $script:UserMcpPath }
                  elseif ($env:AIDEVKIT_HOME) { $env:AIDEVKIT_HOME }
                  else { Join-Path $home_ ".ai-dev-kit" }
    if ($script:Scope -eq "global") { $stateDir = $installDir } else { $stateDir = Join-Path $baseDir ".ai-dev-kit" }

    # Scope strictly gates locations (mirror of install.sh).
    if ($script:Scope -eq "global") {
        $skillRoots = @(
            (Join-Path $home_ ".claude\skills"), (Join-Path $home_ ".cursor\skills"),
            (Join-Path $home_ ".github\skills"), (Join-Path $home_ ".agents\skills"),
            (Join-Path $home_ ".gemini\skills"), (Join-Path $home_ ".gemini\antigravity\skills"),
            (Join-Path $home_ ".codeium\windsurf\skills"), (Join-Path $home_ ".config\opencode\skills"),
            (Join-Path $home_ ".kiro\skills")
        )
        $mcpTargets = @(
            @{ Path=(Join-Path $home_ ".claude\mcp.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $home_ ".codex\config.toml"); Kind="toml" },
            @{ Path=(Join-Path $home_ ".gemini\settings.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $home_ ".gemini\antigravity\mcp_config.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $home_ ".codeium\windsurf\mcp_config.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $home_ ".config\opencode\opencode.json"); Kind="json"; Top="mcp" },
            @{ Path=(Join-Path $home_ ".kiro\settings\mcp.json"); Kind="json"; Top="mcpServers" }
        )
        $hookTargets = @( (Join-Path $home_ ".claude\settings.json") )
    } else {
        $skillRoots = @(
            (Join-Path $baseDir ".claude\skills"), (Join-Path $baseDir ".cursor\skills"),
            (Join-Path $baseDir ".github\skills"), (Join-Path $baseDir ".agents\skills"),
            (Join-Path $baseDir ".gemini\skills"), (Join-Path $baseDir ".windsurf\skills"),
            (Join-Path $baseDir ".opencode\skills"), (Join-Path $baseDir ".kiro\skills")
        )
        $mcpTargets = @(
            @{ Path=(Join-Path $baseDir ".mcp.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $baseDir ".cursor\mcp.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $baseDir ".vscode\mcp.json"); Kind="json"; Top="servers" },
            @{ Path=(Join-Path $baseDir ".codex\config.toml"); Kind="toml" },
            @{ Path=(Join-Path $baseDir ".gemini\settings.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $baseDir "opencode.json"); Kind="json"; Top="mcp" },
            @{ Path=(Join-Path $baseDir ".kiro\settings\mcp.json"); Kind="json"; Top="mcpServers" }
        )
        $hookTargets = @( (Join-Path $baseDir ".claude\settings.json") )
    }

    # Build plan
    $planSkills = @(); $planMcp = @(); $planHooks = @(); $planRuntime = @(); $planState = @()
    foreach ($root in $skillRoots) {
        if (-not (Test-Path $root)) { continue }
        foreach ($name in $script:UninstallSkillNames) {
            $p = Join-Path $root $name
            if (Test-Path $p) { $planSkills += $p }
        }
    }
    foreach ($t in $mcpTargets) {
        if (-not (Test-Path $t.Path)) { continue }
        if ($t.Kind -eq "json" -and (Test-McpJsonHasDatabricks -Path $t.Path -Top $t.Top)) { $planMcp += $t }
        elseif ($t.Kind -eq "toml" -and (Select-String -Path $t.Path -Pattern 'mcp_servers\.databricks' -Quiet)) { $planMcp += $t }
    }
    foreach ($h in $hookTargets) {
        if ((Test-Path $h) -and (Select-String -Path $h -Pattern 'check_update' -Quiet)) { $planHooks += $h }
    }
    if ($script:Scope -eq "global" -or $script:UserMcpPath) {
        if (Test-Path $installDir) { $planRuntime += $installDir }
    }
    # On a global uninstall $stateDir IS the runtime dir; when that dir is already in
    # $planRuntime the state files inside it are removed along with it - planning them
    # separately would make Remove-Item fail on the already-deleted paths.
    if ($planRuntime -notcontains $stateDir) {
        foreach ($s in @((Join-Path $stateDir ".installed-skills"), (Join-Path $stateDir ".skills-profile"), (Join-Path $stateDir "version"))) {
            if (Test-Path $s) { $planState += $s }
        }
    }
    $projMarker = Join-Path $baseDir ".ai-dev-kit"
    if ($script:Scope -eq "project" -and (Test-Path $projMarker)) { $planState += $projMarker }

    # Claude Code plugin at the CURRENT scope — collect the enabled "name@marketplace"
    # key(s) so any marketplace is matched; these are what we remove.
    if ($script:Scope -eq "global") { $pluginKeys = Get-PluginKeysGlobal } else { $pluginKeys = Get-PluginKeysProject -Dir $baseDir }
    $planPlugin = ($pluginKeys.Count -gt 0)

    # Warn about artifacts left behind in the OTHER scope. A global uninstall looks
    # for project-scope files in the current folder; a project uninstall looks for
    # global/user-level files. Skip the $cwd scan when it is $HOME (there project and
    # global paths coincide and are already handled by the global side).
    $projectLeftovers = @(); $globalLeftovers = @()
    $cwd = (Get-Location).Path
    if ($script:Scope -eq "global") {
        if ($cwd -ne $env:USERPROFILE) { $projectLeftovers = Get-ProjectLeftoversSummary -Dir $cwd }
    } else {
        if ($baseDir -ne $env:USERPROFILE) { $globalLeftovers = Get-GlobalLeftoversSummary }
    }

    $total = $planSkills.Count + $planMcp.Count + $planHooks.Count + $planRuntime.Count + $planState.Count + $pluginKeys.Count
    if ($total -eq 0) {
        Write-Ok "Nothing to uninstall for $($script:Scope) scope at $baseDir - no AI Dev Kit artifacts found."
        if ($script:Scope -eq "project" -and -not $globalLeftovers.Count) { Write-Msg "Tip: pass --global to remove a global install." }
        if ($projectLeftovers.Count) { Show-ProjectLeftoversWarning -Dir $cwd -Summary $projectLeftovers }
        if ($globalLeftovers.Count)  { Show-GlobalLeftoversWarning -Summary $globalLeftovers }
        return
    }

    Write-Step "Uninstall plan ($($script:Scope) scope)"
    if ($planSkills.Count) { Write-Host "  Skill folders ($($planSkills.Count)):" -ForegroundColor White; $planSkills | ForEach-Object { Write-Host "    $_" } }
    if ($planMcp.Count)    { Write-Host "  MCP config - remove 'databricks' entry ($($planMcp.Count)):" -ForegroundColor White; $planMcp | ForEach-Object { Write-Host "    $($_.Path)" } }
    if ($planHooks.Count)  { Write-Host "  Claude update hook ($($planHooks.Count)):" -ForegroundColor White; $planHooks | ForEach-Object { Write-Host "    $_" } }
    if ($planRuntime.Count){ Write-Host "  MCP server runtime:" -ForegroundColor White; $planRuntime | ForEach-Object { Write-Host "    $_" } }
    if ($planState.Count)  { Write-Host "  State files:" -ForegroundColor White; $planState | ForEach-Object { Write-Host "    $_" } }
    if ($planPlugin) {
        Write-Host "  Claude Code plugin:" -ForegroundColor White
        foreach ($k in $pluginKeys) { Write-Host "    $k (removed via the claude CLI, $($script:Scope) scope)" -ForegroundColor DarkGray }
        Write-Host "  !  Heads up: the AI Dev Kit Claude Code plugin will also be removed." -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Msg "Config files are backed up to <file>.bak before editing."

    if ($script:DryRun) {
        if ($projectLeftovers.Count) { Show-ProjectLeftoversWarning -Dir $cwd -Summary $projectLeftovers }
        if ($globalLeftovers.Count)  { Show-GlobalLeftoversWarning -Summary $globalLeftovers }
        Write-Ok "Dry run - nothing was changed. Re-run without --dry-run to apply."
        return
    }

    if (-not $script:AssumeYes) {
        $reply = Read-Host "  Remove these $total item(s)? [y/N]"
        if ($reply -notmatch '^(y|yes)$') { Write-Warn "Aborted - nothing removed."; return }
    }

    Write-Step "Removing"
    foreach ($p in $planSkills)  { Remove-Item -Recurse -Force $p; Write-Msg "removed $p" }
    foreach ($t in $planMcp) {
        if ($t.Kind -eq "json") { if (Remove-McpJsonKey -Path $t.Path -Top $t.Top) { Write-Msg "cleaned $($t.Path)" } }
        else { if (Remove-McpTomlBlock -Path $t.Path) { Write-Msg "cleaned $($t.Path)" } }
    }
    foreach ($p in $planHooks)   { if (Remove-ClaudeHook -Path $p) { Write-Msg "cleaned hook in $p" } }
    foreach ($p in $planRuntime) { Remove-Item -Recurse -Force $p; Write-Msg "removed $p" }
    foreach ($p in $planState)   { Remove-Item -Recurse -Force $p; Write-Msg "removed $p" }
    if ($planPlugin) { Remove-ClaudePlugin -OthersRemoved ($total - $pluginKeys.Count) -Keys $pluginKeys }

    Write-Host ""
    Write-Ok "AI Dev Kit uninstalled ($($script:Scope) scope)."
    Write-Msg "Other scopes and per-editor .bak backups were left untouched."
    if ($projectLeftovers.Count) { Show-ProjectLeftoversWarning -Dir $cwd -Summary $projectLeftovers }
    if ($globalLeftovers.Count)  { Show-GlobalLeftoversWarning -Summary $globalLeftovers }
}

if ($script:Uninstall) { Invoke-Uninstall; return }

# ─── Interactive helpers ──────────────────────────────────────

function Test-Interactive {
    if ($script:Silent) { return $false }
    try {
        $host.UI.RawUI.KeyAvailable | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Read-Prompt {
    param([string]$PromptText, [string]$Default)

    if ($script:Silent) { return $Default }

    $isInteractive = Test-Interactive
    if ($isInteractive) {
        Write-Host "  $PromptText [$Default]: " -NoNewline
        $result = Read-Host
        if ([string]::IsNullOrWhiteSpace($result)) { return $Default }
        return $result
    } else {
        return $Default
    }
}

# Interactive checkbox selector using arrow keys + space/enter
# Returns space-separated selected values
function Select-Checkbox {
    param(
        [array]$Items  # Each: @{ Label; Value; State; Hint; Locked }
    )

    $count  = $Items.Count
    $cursor = 0
    $states = @()
    $locked = @()
    foreach ($item in $Items) {
        if ($item.Locked) {
            $locked += $true
            $states += $true   # locked items are always selected
        } else {
            $locked += $false
            $states += [bool]$item.State
        }
    }

    $isInteractive = Test-Interactive

    if (-not $isInteractive) {
        # Fallback: show numbered list, accept comma-separated numbers
        Write-Host ""
        for ($j = 0; $j -lt $count; $j++) {
            $mark = if ($states[$j]) { "[X]" } else { "[ ]" }
            $hint = $Items[$j].Hint
            Write-Host "  $($j + 1). $mark $($Items[$j].Label)  ($hint)"
        }
        Write-Host ""
        Write-Host "  Enter numbers to toggle (e.g. 1,3), or press Enter to accept defaults: " -NoNewline
        $input_ = Read-Host
        if (-not [string]::IsNullOrWhiteSpace($input_)) {
            # Reset all states
            for ($j = 0; $j -lt $count; $j++) { $states[$j] = $false }
            $nums = $input_ -split ',' | ForEach-Object { $_.Trim() }
            foreach ($n in $nums) {
                $idx = [int]$n - 1
                if ($idx -ge 0 -and $idx -lt $count) { $states[$idx] = $true }
            }
        }
        # Locked items are always selected
        for ($j = 0; $j -lt $count; $j++) { if ($locked[$j]) { $states[$j] = $true } }
        $selected = @()
        for ($j = 0; $j -lt $count; $j++) {
            if ($states[$j]) { $selected += $Items[$j].Value }
        }
        return ($selected -join ' ')
    }

    # Full interactive mode
    Write-Host ""
    Write-Host "  Up/Down navigate, Space toggle, Enter on Confirm to finish" -ForegroundColor DarkGray
    Write-Host ""

    $totalRows = $count + 2  # items + blank + Confirm

    # Hide cursor
    try { [Console]::CursorVisible = $false } catch {}

    # Draw function — uses relative cursor movement to handle terminal scroll
    $drawCheckbox = {
        [Console]::SetCursorPosition(0, [Math]::Max(0, [Console]::CursorTop - $totalRows))
        for ($j = 0; $j -lt $count; $j++) {
            $line = "  "
            if ($j -eq $cursor) {
                Write-Host "  " -NoNewline
                Write-Host ">" -ForegroundColor Blue -NoNewline
                Write-Host " " -NoNewline
            } else {
                Write-Host "    " -NoNewline
            }
            if ($states[$j]) {
                Write-Host "[" -NoNewline
                Write-Host "v" -ForegroundColor Green -NoNewline
                Write-Host "]" -NoNewline
            } else {
                Write-Host "[ ]" -NoNewline
            }
            $padLabel = $Items[$j].Label.PadRight(16)
            Write-Host " $padLabel " -NoNewline
            # Truncate the hint so the line can't wrap past the window width
            # (a wrapped line would desync the cursor-relative redraw).
            $hint = $Items[$j].Hint
            $avail = [Console]::WindowWidth - [Console]::CursorLeft - 1
            if ($avail -lt 0) { $avail = 0 }
            if ($hint.Length -gt $avail) { $hint = $hint.Substring(0, $avail) }
            if ($states[$j]) {
                Write-Host $hint -ForegroundColor Green -NoNewline
            } else {
                Write-Host $hint -ForegroundColor DarkGray -NoNewline
            }
            # Clear rest of line
            $pos = [Console]::CursorLeft
            $remaining = [Console]::WindowWidth - $pos - 1
            if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
            Write-Host ""
        }
        # Blank line
        Write-Host (' ' * ([Console]::WindowWidth - 1))
        # Confirm button
        if ($cursor -eq $count) {
            Write-Host "  " -NoNewline
            Write-Host ">" -ForegroundColor Blue -NoNewline
            Write-Host " " -NoNewline
            Write-Host "[ Confirm ]" -ForegroundColor Green -NoNewline
        } else {
            Write-Host "    " -NoNewline
            Write-Host "[ Confirm ]" -ForegroundColor DarkGray -NoNewline
        }
        $pos = [Console]::CursorLeft
        $remaining = [Console]::WindowWidth - $pos - 1
        if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
        Write-Host ""
    }

    # Initial draw — reserve lines first
    for ($j = 0; $j -lt $totalRows; $j++) { Write-Host "" }
    & $drawCheckbox

    # Input loop
    while ($true) {
        $key = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

        switch ($key.VirtualKeyCode) {
            38 { # Up arrow
                if ($cursor -gt 0) { $cursor-- }
            }
            40 { # Down arrow
                if ($cursor -lt $count) { $cursor++ }
            }
            32 { # Space
                if ($cursor -lt $count -and -not $locked[$cursor]) {
                    $states[$cursor] = -not $states[$cursor]
                }
            }
            13 { # Enter
                if ($cursor -lt $count) {
                    if (-not $locked[$cursor]) { $states[$cursor] = -not $states[$cursor] }
                } else {
                    # On Confirm — done
                    & $drawCheckbox
                    break
                }
            }
        }
        if ($key.VirtualKeyCode -eq 13 -and $cursor -eq $count) { break }

        & $drawCheckbox
    }

    # Show cursor
    try { [Console]::CursorVisible = $true } catch {}

    $selected = @()
    for ($j = 0; $j -lt $count; $j++) {
        if ($states[$j]) { $selected += $Items[$j].Value }
    }
    return ($selected -join ' ')
}

# Interactive radio selector using arrow keys + enter
# Returns the selected value
function Select-Radio {
    param(
        [array]$Items  # Each: @{ Label; Value; Selected; Hint }
    )

    $count    = $Items.Count
    $cursor   = 0
    $selected = 0

    for ($j = 0; $j -lt $count; $j++) {
        if ($Items[$j].Selected) { $selected = $j }
    }

    $isInteractive = Test-Interactive

    if (-not $isInteractive) {
        # Fallback: numbered list
        Write-Host ""
        for ($j = 0; $j -lt $count; $j++) {
            $mark = if ($j -eq $selected) { "(*)" } else { "( )" }
            $hint = $Items[$j].Hint
            Write-Host "  $($j + 1). $mark $($Items[$j].Label)  $hint"
        }
        Write-Host ""
        Write-Host "  Enter number to select (or press Enter for default): " -NoNewline
        $input_ = Read-Host
        if (-not [string]::IsNullOrWhiteSpace($input_)) {
            $idx = [int]$input_ - 1
            if ($idx -ge 0 -and $idx -lt $count) { $selected = $idx }
        }
        return $Items[$selected].Value
    }

    # Full interactive mode
    Write-Host ""
    Write-Host "  Up/Down navigate, Enter confirm" -ForegroundColor DarkGray
    Write-Host ""

    $totalRows = $count + 2  # items + blank + Confirm

    try { [Console]::CursorVisible = $false } catch {}

    # Draw function — uses relative cursor movement to handle terminal scroll
    $drawRadio = {
        [Console]::SetCursorPosition(0, [Math]::Max(0, [Console]::CursorTop - $totalRows))
        for ($j = 0; $j -lt $count; $j++) {
            if ($j -eq $cursor) {
                Write-Host "  " -NoNewline
                Write-Host ">" -ForegroundColor Blue -NoNewline
                Write-Host " " -NoNewline
            } else {
                Write-Host "    " -NoNewline
            }
            if ($j -eq $selected) {
                Write-Host "(*)" -ForegroundColor Green -NoNewline
            } else {
                Write-Host "( )" -ForegroundColor DarkGray -NoNewline
            }
            $padLabel = $Items[$j].Label.PadRight(20)
            Write-Host " $padLabel " -NoNewline
            # Truncate the hint so the line can't wrap past the window width
            # (a wrapped line would desync the cursor-relative redraw).
            $hint = $Items[$j].Hint
            $avail = [Console]::WindowWidth - [Console]::CursorLeft - 1
            if ($avail -lt 0) { $avail = 0 }
            if ($hint.Length -gt $avail) { $hint = $hint.Substring(0, $avail) }
            if ($j -eq $selected) {
                Write-Host $hint -ForegroundColor Green -NoNewline
            } else {
                Write-Host $hint -ForegroundColor DarkGray -NoNewline
            }
            $pos = [Console]::CursorLeft
            $remaining = [Console]::WindowWidth - $pos - 1
            if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
            Write-Host ""
        }
        Write-Host (' ' * ([Console]::WindowWidth - 1))
        if ($cursor -eq $count) {
            Write-Host "  " -NoNewline
            Write-Host ">" -ForegroundColor Blue -NoNewline
            Write-Host " " -NoNewline
            Write-Host "[ Confirm ]" -ForegroundColor Green -NoNewline
        } else {
            Write-Host "    " -NoNewline
            Write-Host "[ Confirm ]" -ForegroundColor DarkGray -NoNewline
        }
        $pos = [Console]::CursorLeft
        $remaining = [Console]::WindowWidth - $pos - 1
        if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
        Write-Host ""
    }

    # Reserve lines
    for ($j = 0; $j -lt $totalRows; $j++) { Write-Host "" }
    & $drawRadio

    while ($true) {
        $key = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

        switch ($key.VirtualKeyCode) {
            38 { if ($cursor -gt 0) { $cursor-- } }
            40 { if ($cursor -lt $count) { $cursor++ } }
            32 { # Space — select but keep browsing
                if ($cursor -lt $count) { $selected = $cursor }
            }
            13 { # Enter — select and confirm
                if ($cursor -lt $count) { $selected = $cursor }
                & $drawRadio
                break
            }
        }
        if ($key.VirtualKeyCode -eq 13) { break }

        & $drawRadio
    }

    try { [Console]::CursorVisible = $true } catch {}

    return $Items[$selected].Value
}

# ─── Tool detection & selection ───────────────────────────────
function Invoke-DetectTools {
    if (-not [string]::IsNullOrWhiteSpace($script:UserTools)) {
        $script:Tools = $script:UserTools -replace ',', ' '
        return
    }

    $hasClaude  = $null -ne (Get-Command claude -ErrorAction SilentlyContinue)
    $hasCursor  = ($null -ne (Get-Command cursor -ErrorAction SilentlyContinue)) -or
                  (Test-Path "$env:LOCALAPPDATA\Programs\cursor\Cursor.exe")
    $hasCodex   = $null -ne (Get-Command codex -ErrorAction SilentlyContinue)
    $hasCopilot = ($null -ne (Get-Command code -ErrorAction SilentlyContinue)) -or
                  (Test-Path "$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe")
    $hasGemini  = $null -ne (Get-Command gemini -ErrorAction SilentlyContinue)
    $hasAntigravity = ($null -ne (Get-Command antigravity -ErrorAction SilentlyContinue)) -or
                      (Test-Path "$env:LOCALAPPDATA\Programs\Antigravity\Antigravity.exe")
    $hasWindsurf = ($null -ne (Get-Command windsurf -ErrorAction SilentlyContinue)) -or
                   (Test-Path "$env:LOCALAPPDATA\Programs\Windsurf\Windsurf.exe")
    $hasOpencode = $null -ne (Get-Command opencode -ErrorAction SilentlyContinue)
    $hasKiro    = ($null -ne (Get-Command kiro -ErrorAction SilentlyContinue)) -or
                  (Test-Path "$env:LOCALAPPDATA\Programs\Kiro\Kiro.exe")

    $claudeState  = $hasClaude;  $claudeHint  = if ($hasClaude)  { "detected" } else { "not found" }
    $cursorState  = $hasCursor;  $cursorHint  = if ($hasCursor)  { "detected" } else { "not found" }
    $codexState   = $hasCodex;   $codexHint   = if ($hasCodex)   { "detected" } else { "not found" }
    $copilotState = $hasCopilot; $copilotHint = if ($hasCopilot) { "detected" } else { "not found" }
    $geminiState  = $hasGemini;  $geminiHint  = if ($hasGemini)  { "detected" } else { "not found" }
    $antigravityState = $hasAntigravity; $antigravityHint = if ($hasAntigravity) { "detected" } else { "not found" }
    $windsurfState = $hasWindsurf; $windsurfHint = if ($hasWindsurf) { "detected" } else { "not found" }
    $opencodeState = $hasOpencode; $opencodeHint = if ($hasOpencode) { "detected" } else { "not found" }
    $kiroState    = $hasKiro;    $kiroHint    = if ($hasKiro)    { "detected" } else { "not found" }

    # If nothing detected, default to claude
    if (-not $hasClaude -and -not $hasCursor -and -not $hasCodex -and -not $hasCopilot -and -not $hasGemini -and -not $hasAntigravity -and -not $hasWindsurf -and -not $hasOpencode -and -not $hasKiro) {
        $claudeState = $true
        $claudeHint  = "default"
    }

    if (-not $script:Silent) {
        Write-Host ""
        Write-Host "  Select tools to install for:" -ForegroundColor White
    }

    $items = @(
        @{ Label = "Claude Code";    Value = "claude";       State = $claudeState;       Hint = $claudeHint }
        @{ Label = "Cursor";         Value = "cursor";       State = $cursorState;       Hint = $cursorHint }
        @{ Label = "GitHub Copilot"; Value = "copilot";      State = $copilotState;      Hint = $copilotHint }
        @{ Label = "OpenAI Codex";   Value = "codex";        State = $codexState;        Hint = $codexHint }
        @{ Label = "Gemini CLI";     Value = "gemini";       State = $geminiState;       Hint = $geminiHint }
        @{ Label = "Antigravity";    Value = "antigravity";  State = $antigravityState;  Hint = $antigravityHint }
        @{ Label = "Windsurf";       Value = "windsurf";     State = $windsurfState;     Hint = $windsurfHint }
        @{ Label = "OpenCode";       Value = "opencode";     State = $opencodeState;     Hint = $opencodeHint }
        @{ Label = "Kiro";           Value = "kiro";         State = $kiroState;         Hint = $kiroHint }
    )

    $result = Select-Checkbox -Items $items

    if ([string]::IsNullOrWhiteSpace($result)) {
        Write-Warn "No tools selected, defaulting to Claude Code"
        $result = "claude"
    }

    $script:Tools = $result
}

# ─── Databricks profile selection ────────────────────────────
function Invoke-PromptProfile {
    if ($script:ProfileProvided) { return }
    if ($script:Silent) { return }

    $cfgFile = Join-Path $env:USERPROFILE ".databrickscfg"
    $profiles = @()

    if (Test-Path $cfgFile) {
        $lines = Get-Content $cfgFile
        foreach ($line in $lines) {
            if ($line -match '^\[([a-zA-Z0-9_-]+)\]$') {
                $profiles += $Matches[1]
            }
        }
    }

    Write-Host ""
    Write-Host "  Select Databricks profile" -ForegroundColor White

    if ($profiles.Count -gt 0) {
        $items = @()
        $hasDefault = $profiles -contains "DEFAULT"
        foreach ($p in $profiles) {
            $sel  = $false
            $hint = ""
            if ($p -eq "DEFAULT") { $sel = $true; $hint = "default" }
            $items += @{ Label = $p; Value = $p; Selected = $sel; Hint = $hint }
        }
        
        # Add custom profile option at the end
        $items += @{ Label = "Custom profile name..."; Value = "__CUSTOM__"; Selected = $false; Hint = "Enter a custom profile name" }
        
        if (-not $hasDefault -and $items.Count -gt 1) {
            $items[0].Selected = $true
        }

        $selectedProfile = Select-Radio -Items $items
        
        # If custom was selected, prompt for name
        if ($selectedProfile -eq "__CUSTOM__") {
            Write-Host ""
            $script:Profile_ = Read-Prompt -PromptText "Enter profile name" -Default "DEFAULT"
        } else {
            $script:Profile_ = $selectedProfile
        }
    } else {
        Write-Host "  No ~/.databrickscfg found. You can authenticate after install." -ForegroundColor DarkGray
        Write-Host ""
        $script:Profile_ = Read-Prompt -PromptText "Profile name" -Default "DEFAULT"
    }
}

# ─── MCP path selection ──────────────────────────────────────
# ─── MCP server installation prompt (deprecated/optional) ──────
# Skills work via the Databricks CLI, so MCP is opt-in. Matches the radio-style
# prompt used on the experimental branch and defaults to "Do not install".
function Invoke-PromptMcpInstall {
    # Already opted in via -Mcp / -McpPath / -McpOnly / env var
    if ($script:InstallMcp) { return }
    # Silent or non-interactive runs leave MCP off
    if ($script:Silent -or -not (Test-Interactive)) { return }

    Write-Host ""
    Write-Host "  Deprecated MCP Server" -ForegroundColor White
    Write-Host "  Skills now work via the Databricks CLI for better performance. The MCP" -ForegroundColor DarkGray
    Write-Host "  server is optional and only needed for backwards compatibility." -ForegroundColor DarkGray

    $items = @(
        @{ Label = "Do not install";     Value = "no";  Selected = $true;  Hint = "Recommended -- skills work without MCP" }
        @{ Label = "Install MCP server"; Value = "yes"; Selected = $false; Hint = "Legacy -- requires a Python venv (uv)" }
    )
    $selected = Select-Radio -Items $items
    if ($selected -eq "yes") { $script:InstallMcp = $true }
}

function Invoke-PromptMcpPath {
    if (-not [string]::IsNullOrWhiteSpace($script:UserMcpPath)) {
        $script:InstallDir = $script:UserMcpPath
    } elseif (-not $script:Silent) {
        Write-Host ""
        Write-Host "  MCP server location" -ForegroundColor White
        Write-Host "  The MCP server runtime (Python venv + source) will be installed here." -ForegroundColor DarkGray
        Write-Host "  Shared across all your projects -- only the config files are per-project." -ForegroundColor DarkGray
        Write-Host ""

        $selected = Read-Prompt -PromptText "Install path" -Default $InstallDir
        $script:InstallDir = $selected
    }

    # Update derived paths
    $script:RepoDir    = Join-Path $script:InstallDir "repo"
    $script:VenvDir    = Join-Path $script:InstallDir ".venv"
    $script:VenvPython = Join-Path $script:VenvDir "Scripts\python.exe"
    $script:McpEntry   = Join-Path $script:RepoDir "databricks-mcp-server\run_server.py"
}

# ─── Check prerequisites ─────────────────────────────────────
function Test-Dependencies {
    # Git
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Err "git required. Install: choco install git -y"
    }
    Write-Ok "git"

    # Databricks CLI
    if (Get-Command databricks -ErrorAction SilentlyContinue) {
        try {
            $cliOutput = & databricks --version 2>&1
            if ($cliOutput -match '(\d+\.\d+\.\d+)') {
                $cliVersion = $Matches[1]
                if ([version]$cliVersion -ge [version]$MinCliVersion) {
                    Write-Ok "Databricks CLI v$cliVersion"
                } else {
                    Write-Warn "Databricks CLI v$cliVersion is outdated (minimum: v$MinCliVersion)"
                    Write-Msg "  Upgrade: winget upgrade Databricks.DatabricksCLI"
                }
            } else {
                Write-Warn "Could not determine Databricks CLI version"
            }
        } catch {
            Write-Warn "Could not determine Databricks CLI version"
        }
    } else {
        Write-Warn "Databricks CLI not found. Install: winget install Databricks.DatabricksCLI"
        Write-Msg "You can still install, but authentication will require the CLI later."
    }

    # The MCP server's Python environment (and its uv/pip requirement) is built
    # by databricks-mcp-server/setup.ps1 when the user opts in — not here.
}

# ─── Check version ───────────────────────────────────────────
function Test-Version {
    $verFile = Join-Path $script:InstallDir "version"
    if ($script:Scope -eq "project") {
        $verFile = Join-Path (Get-Location) ".ai-dev-kit\version"
    }

    if (-not (Test-Path $verFile)) { return }
    if ($script:Force) { return }

    # Skip version gate if user explicitly wants a different skill profile
    if (-not [string]::IsNullOrWhiteSpace($script:SkillsProfile) -or -not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
        $savedProfileFile = Join-Path $script:StateDir ".skills-profile"
        if (-not (Test-Path $savedProfileFile) -and $script:Scope -eq "project") {
            $savedProfileFile = Join-Path $script:InstallDir ".skills-profile"
        }
        if (Test-Path $savedProfileFile) {
            $savedProfile = (Get-Content $savedProfileFile -Raw).Trim()
            $requested = if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) { "custom:$($script:UserSkills)" } else { $script:SkillsProfile }
            if ($savedProfile -ne $requested) { return }
        }
    }

    $localVer = (Get-Content $verFile -Raw).Trim()

    try {
        $remoteVer = (Invoke-WebRequest -Uri "$RawUrl/VERSION" -UseBasicParsing -ErrorAction Stop).Content.Trim()
    } catch {
        return
    }

    if ($remoteVer -and $remoteVer -notmatch '(404|Not Found|error)') {
        if ($localVer -eq $remoteVer) {
            Write-Ok "Already up to date (v$localVer)"
            Write-Msg "Use --force to reinstall or --skills-profile to change profiles"
            exit 0
        }
    }
}

# ─── Clone repo sources ──────────────────────────────────────
# Needed for bundled skills and the MCP server setup script. Idempotent.
function Get-RepoSources {
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    if (Test-Path (Join-Path $script:RepoDir ".git")) {
        & git -C $script:RepoDir fetch -q --depth 1 origin $Branch 2>&1 | Out-Null
        & git -C $script:RepoDir reset --hard FETCH_HEAD 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Remove-Item -Recurse -Force $script:RepoDir -ErrorAction SilentlyContinue
            & git -c advice.detachedHead=false clone -q --depth 1 --branch $Branch $RepoUrl $script:RepoDir 2>&1 | Out-Null
        }
    } else {
        if (-not (Test-Path $script:InstallDir)) {
            New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null
        }
        & git -c advice.detachedHead=false clone -q --depth 1 --branch $Branch $RepoUrl $script:RepoDir 2>&1 | Out-Null
    }
    if ($LASTEXITCODE -ne 0) {
        $ErrorActionPreference = $prevEAP
        Write-Err "Failed to clone repository"
    }
    $ErrorActionPreference = $prevEAP
    Write-Ok "Repository cloned ($Branch)"
}

# ─── Setup MCP server (deprecated, opt-in) ───────────────────
# Delegates the venv build to databricks-mcp-server/setup.ps1 — the single
# source of truth for the Python environment — so the installer doesn't
# duplicate venv/pip logic here.
function Install-McpServer {
    Write-Step "Setting up MCP server"
    Get-RepoSources

    $setupScript = Join-Path $script:RepoDir "databricks-mcp-server\setup.ps1"
    if (-not (Test-Path $setupScript)) {
        Write-Err "MCP setup script not found at $setupScript"
    }

    Write-Msg "Building MCP server environment (databricks-mcp-server/setup.ps1)..."
    $setupArgs = @("-VenvDir", $script:VenvDir)
    if ($script:Silent) { $setupArgs += "-Quiet" }

    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $setupScript @setupArgs
    $setupOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEAP
    if (-not $setupOk) { Write-Err "MCP server setup failed" }
    Write-Ok "MCP server ready"
}

# ─── Skill profile selection ──────────────────────────────────

# Bucket one skill name into its source (returns "mlflow"/"agentb", or "" for unknown)
function Get-SkillBucket {
    param([string]$Name)
    if ($script:MlflowSkills -contains $Name) { return "mlflow" }
    if (($script:AgentBStable -contains $Name) -or ($script:AgentBExperimental -contains $Name)) { return "agentb" }
    return ""
}

# Resolve selected skills from profile names or explicit skill list,
# bucketing each name into its source (mlflow / agent-skills).
function Resolve-Skills {
    Get-AgentBInventory

    $mlflowSkills = @()
    $agentBSkills = @()

    # Agent skills selected by default: everything except the excluded list (and
    # experimental skills when --experimental false)
    $defaultAgentB = @()
    foreach ($skill in ($script:AgentBStable + $script:AgentBExperimental)) {
        if ($script:AgentBExcluded -contains $skill) { continue }
        if (-not $script:InstallExperimental -and ($script:AgentBExperimental -contains $skill)) { continue }
        $defaultAgentB += $skill
    }

    # Priority 1: Explicit --skills flag (comma-separated skill names)
    if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
        foreach ($skill in ($script:UserSkills -split ',')) {
            $skill = $skill.Trim()
            if ([string]::IsNullOrWhiteSpace($skill)) { continue }
            $bucket = Get-SkillBucket -Name $skill
            if (-not $bucket -and $script:RenamedSkills.ContainsKey($skill)) {
                $newName = $script:RenamedSkills[$skill]
                Write-Warn "Skill '$skill' was renamed/replaced by '$newName' -- installing '$newName'"
                $skill = $newName
                $bucket = Get-SkillBucket -Name $skill
            }
            switch ($bucket) {
                "mlflow" { $mlflowSkills += $skill }
                "agentb" { $agentBSkills += $skill }
                default  { Write-Err "Unknown skill: '$skill' (run with --list-skills to see available skills)" }
            }
        }
        $script:SelectedMlflowSkills = @($mlflowSkills | Select-Object -Unique)
        $script:SelectedAgentBSkills = @($agentBSkills | Select-Object -Unique)
        return
    }

    # Priority 2: --skills-profile flag or interactive selection
    if ([string]::IsNullOrWhiteSpace($script:SkillsProfile) -or $script:SkillsProfile -eq "all" -or ($script:SkillsProfile -split ',' | ForEach-Object { $_.Trim() }) -contains "all") {
        $script:SelectedMlflowSkills = @($script:MlflowSkills)
        $script:SelectedAgentBSkills = @($defaultAgentB)
        return
    }

    # Build union of selected profiles (comma-separated, flat name lists bucketed per name)
    $names = @() + $script:CoreSkills
    foreach ($profile in ($script:SkillsProfile -split ',')) {
        $profile = $profile.Trim()
        switch ($profile) {
            "data-engineer"  { $names += $script:ProfileDataEngineer }
            "analyst"        { $names += $script:ProfileAnalyst }
            "ai-ml-engineer" { $names += $script:ProfileAiMlEngineer + $script:ProfileAiMlMlflow }
            "app-developer"  { $names += $script:ProfileAppDeveloper }
            default          { Write-Warn "Unknown skill profile: $profile (ignored)" }
        }
    }

    foreach ($skill in $names) {
        # Drop experimental agent skills from profiles when --experimental false
        if (-not $script:InstallExperimental -and ($script:AgentBExperimental -contains $skill)) { continue }
        switch (Get-SkillBucket -Name $skill) {
            "mlflow" { $mlflowSkills += $skill }
            "agentb" { $agentBSkills += $skill }
            default  { Write-Warn "Skill '$skill' not found in any source (skipped)" }
        }
    }

    $script:SelectedMlflowSkills = @($mlflowSkills | Select-Object -Unique)
    $script:SelectedAgentBSkills = @($agentBSkills | Select-Object -Unique)
}

function Invoke-PromptSkillsProfile {
    # If provided via --skills or --skills-profile, skip interactive prompt
    if (-not [string]::IsNullOrWhiteSpace($script:UserSkills) -or -not [string]::IsNullOrWhiteSpace($script:SkillsProfile)) {
        return
    }

    # Skip in silent mode
    if ($script:Silent) {
        $script:SkillsProfile = "all"
        return
    }

    # Check for previous selection (scope-local first, then global fallback for upgrades)
    $profileFile = Join-Path $script:StateDir ".skills-profile"
    if (-not (Test-Path $profileFile) -and $script:Scope -eq "project") {
        $profileFile = Join-Path $script:InstallDir ".skills-profile"
    }
    if (Test-Path $profileFile) {
        $prevProfile = (Get-Content $profileFile -Raw).Trim()
        if (-not $script:Force) {
            Write-Host ""
            $displayProfile = $prevProfile -replace ',', ', '
            $keep = Read-Prompt -PromptText "Previous skill profile: $displayProfile. Keep? (Y/n)" -Default "y"
            if ($keep -in @("y", "Y", "yes", "")) {
                $script:SkillsProfile = $prevProfile
                return
            }
        }
    }

    Write-Host ""
    Write-Host "  Select skill profile(s)" -ForegroundColor White

    # Custom checkbox with mutual exclusion: "All" deselects others, others deselect "All"
    $allCount = Get-AllSkillsCount
    $deCount = $script:CoreSkills.Count + $script:ProfileDataEngineer.Count
    $anCount = $script:CoreSkills.Count + $script:ProfileAnalyst.Count
    $aiCount = $script:CoreSkills.Count + $script:ProfileAiMlEngineer.Count + $script:ProfileAiMlMlflow.Count
    $apCount = $script:CoreSkills.Count + $script:ProfileAppDeveloper.Count
    $pLabels = @("All Skills", "Data Engineer", "Business Analyst", "AI/ML Engineer", "App Developer", "Custom")
    $pValues = @("all", "data-engineer", "analyst", "ai-ml-engineer", "app-developer", "custom")
    $pHints  = @("Install everything ($allCount skills)", "Pipelines, Spark, Jobs, Streaming ($deCount skills)", "Dashboards, SQL, Genie, Metrics ($anCount skills)", "Agents, RAG, Vector Search, MLflow ($aiCount skills)", "Apps, Lakebase, Deployment ($apCount skills)", "Pick individual skills")
    $pStates = @($true, $false, $false, $false, $false, $false)
    $pCount  = 6
    $pCursor = 0
    $pTotalRows = $pCount + 2

    $isInteractive = Test-Interactive

    if (-not $isInteractive) {
        # Fallback: numbered list
        Write-Host ""
        for ($j = 0; $j -lt $pCount; $j++) {
            $mark = if ($pStates[$j]) { "[X]" } else { "[ ]" }
            Write-Host "  $($j + 1). $mark $($pLabels[$j])  ($($pHints[$j]))"
        }
        Write-Host ""
        Write-Host "  Enter numbers to toggle (e.g. 2,4), or press Enter for All: " -NoNewline
        $input_ = Read-Host
        if (-not [string]::IsNullOrWhiteSpace($input_)) {
            for ($j = 0; $j -lt $pCount; $j++) { $pStates[$j] = $false }
            $nums = $input_ -split ',' | ForEach-Object { $_.Trim() }
            foreach ($n in $nums) {
                $idx = [int]$n - 1
                if ($idx -ge 0 -and $idx -lt $pCount) { $pStates[$idx] = $true }
            }
        }
    } else {
        Write-Host ""
        Write-Host "  Up/Down navigate, Space toggle, Enter on Confirm to finish" -ForegroundColor DarkGray
        Write-Host ""

        try { [Console]::CursorVisible = $false } catch {}

        $drawProfiles = {
            [Console]::SetCursorPosition(0, [Math]::Max(0, [Console]::CursorTop - $pTotalRows))
            for ($j = 0; $j -lt $pCount; $j++) {
                if ($j -eq $pCursor) {
                    Write-Host "  " -NoNewline; Write-Host ">" -ForegroundColor Blue -NoNewline; Write-Host " " -NoNewline
                } else {
                    Write-Host "    " -NoNewline
                }
                if ($pStates[$j]) {
                    Write-Host "[" -NoNewline; Write-Host "v" -ForegroundColor Green -NoNewline; Write-Host "]" -NoNewline
                } else {
                    Write-Host "[ ]" -NoNewline
                }
                $padLabel = $pLabels[$j].PadRight(20)
                Write-Host " $padLabel " -NoNewline
                # Truncate the hint so the line can't wrap past the window width
                # (a wrapped line would desync the cursor-relative redraw).
                $hint = $pHints[$j]
                $avail = [Console]::WindowWidth - [Console]::CursorLeft - 1
                if ($avail -lt 0) { $avail = 0 }
                if ($hint.Length -gt $avail) { $hint = $hint.Substring(0, $avail) }
                if ($pStates[$j]) {
                    Write-Host $hint -ForegroundColor Green -NoNewline
                } else {
                    Write-Host $hint -ForegroundColor DarkGray -NoNewline
                }
                $pos = [Console]::CursorLeft
                $remaining = [Console]::WindowWidth - $pos - 1
                if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
                Write-Host ""
            }
            Write-Host (' ' * ([Console]::WindowWidth - 1))
            if ($pCursor -eq $pCount) {
                Write-Host "  " -NoNewline; Write-Host ">" -ForegroundColor Blue -NoNewline
                Write-Host " " -NoNewline; Write-Host "[ Confirm ]" -ForegroundColor Green -NoNewline
            } else {
                Write-Host "    " -NoNewline; Write-Host "[ Confirm ]" -ForegroundColor DarkGray -NoNewline
            }
            $pos = [Console]::CursorLeft
            $remaining = [Console]::WindowWidth - $pos - 1
            if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
            Write-Host ""
        }

        for ($j = 0; $j -lt $pTotalRows; $j++) { Write-Host "" }
        & $drawProfiles

        while ($true) {
            $key = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

            switch ($key.VirtualKeyCode) {
                38 { if ($pCursor -gt 0) { $pCursor-- } }
                40 { if ($pCursor -lt $pCount) { $pCursor++ } }
                32 { # Space
                    if ($pCursor -lt $pCount) {
                        $pStates[$pCursor] = -not $pStates[$pCursor]
                        if ($pStates[$pCursor]) {
                            if ($pCursor -eq 0) {
                                # Selected "All" → deselect others
                                for ($j = 1; $j -lt $pCount; $j++) { $pStates[$j] = $false }
                            } else {
                                # Selected individual → deselect "All"
                                $pStates[0] = $false
                            }
                        }
                    }
                }
                13 { # Enter
                    if ($pCursor -lt $pCount) {
                        $pStates[$pCursor] = -not $pStates[$pCursor]
                        if ($pStates[$pCursor]) {
                            if ($pCursor -eq 0) {
                                for ($j = 1; $j -lt $pCount; $j++) { $pStates[$j] = $false }
                            } else {
                                $pStates[0] = $false
                            }
                        }
                    } else {
                        & $drawProfiles
                        break
                    }
                }
            }
            if ($key.VirtualKeyCode -eq 13 -and $pCursor -eq $pCount) { break }
            & $drawProfiles
        }

        try { [Console]::CursorVisible = $true } catch {}
    }

    # Build result from states
    $selectedProfiles = @()
    for ($j = 0; $j -lt $pCount; $j++) {
        if ($pStates[$j]) { $selectedProfiles += $pValues[$j] }
    }
    $selected = $selectedProfiles -join ' '

    # Nothing selected -- drop into the individual skill picker (custom) rather
    # than silently installing everything.
    if ([string]::IsNullOrWhiteSpace($selected)) {
        Invoke-PromptCustomSkills -PreselectedProfiles ""
        return
    }

    if ($selected -match '\ball\b') {
        $script:SkillsProfile = "all"
        return
    }

    if ($selected -match '\bcustom\b') {
        Invoke-PromptCustomSkills -PreselectedProfiles $selected
        return
    }

    $script:SkillsProfile = ($selectedProfiles -join ',')
}

function Invoke-PromptCustomSkills {
    param([string]$PreselectedProfiles)

    # Build pre-selection set from any profiles that were also checked
    # (core skills start pre-selected -- they are recommended for every profile)
    $preselected = @() + $script:CoreSkills
    foreach ($profile in ($PreselectedProfiles -split ' ')) {
        switch ($profile) {
            "data-engineer"  { $preselected += $script:ProfileDataEngineer }
            "analyst"        { $preselected += $script:ProfileAnalyst }
            "ai-ml-engineer" { $preselected += $script:ProfileAiMlEngineer + $script:ProfileAiMlMlflow }
            "app-developer"  { $preselected += $script:ProfileAppDeveloper }
        }
    }

    Write-Host ""
    Write-Host "  Select individual skills" -ForegroundColor White
    Write-Host "  Core skills (core, docs, python-sdk, unity-catalog) are recommended for all profiles" -ForegroundColor DarkGray

    # Friendly label + hint per skill. Unknown/new skills (as the upstream
    # inventory grows) fall back to the bare name so they still appear.
    $meta = @{
        "databricks-core"                       = @("Core", "CLI auth, data exploration")
        "databricks-docs"                       = @("Docs", "Databricks documentation")
        "databricks-python-sdk"                 = @("Python SDK", "SDK, Connect, REST API")
        "databricks-unity-catalog"              = @("Unity Catalog", "System tables, volumes")
        "databricks-pipelines"                  = @("Spark Pipelines", "SDP/LDP, CDC, SCD Type 2")
        "databricks-spark-structured-streaming" = @("Structured Streaming", "Real-time streaming")
        "databricks-jobs"                       = @("Jobs & Workflows", "Multi-task orchestration")
        "databricks-dabs"                       = @("Asset Bundles", "DABs deployment")
        "databricks-dbsql"                      = @("Databricks SQL", "SQL warehouse queries")
        "databricks-iceberg"                    = @("Iceberg", "Apache Iceberg tables")
        "databricks-lakeflow-connect"           = @("Lakeflow Connect", "Managed ingestion connectors")
        "databricks-zerobus-ingest"             = @("Zerobus Ingest", "Streaming ingestion")
        "spark-python-data-source"              = @("Python Data Source", "Custom Spark data sources")
        "databricks-metric-views"               = @("Metric Views", "Metric definitions")
        "databricks-aibi-dashboards"            = @("AI/BI Dashboards", "Dashboard creation")
        "databricks-genie"                      = @("Genie", "Natural language SQL")
        "databricks-agent-bricks"               = @("Agent Bricks", "Build AI agents")
        "databricks-vector-search"              = @("Vector Search", "Similarity search")
        "databricks-model-serving"              = @("Model Serving", "Deploy models/agents")
        "databricks-mlflow-evaluation"          = @("MLflow Evaluation", "Model evaluation")
        "databricks-ai-functions"               = @("AI Functions", "AI Functions, document parsing & RAG")
        "databricks-unstructured-pdf-generation" = @("Unstructured PDF", "Synthetic PDFs for RAG")
        "databricks-synthetic-data-gen"         = @("Synthetic Data", "Generate test data")
        "databricks-lakebase"                   = @("Lakebase", "Managed PostgreSQL (OLTP)")
        "databricks-serverless-migration"       = @("Serverless Migration", "Migrate to serverless compute")
        "databricks-apps"                       = @("Apps", "AppKit + all frameworks")
        "databricks-apps-python"                = @("App (AppKit + Python)", "AppKit, Dash, Streamlit, Flask")
        "mlflow-onboarding"                     = @("MLflow Onboarding", "Getting started")
        "agent-evaluation"                      = @("Agent Evaluation", "Evaluate AI agents")
        "instrumenting-with-mlflow-tracing"     = @("MLflow Tracing", "Instrument with tracing")
        "analyze-mlflow-trace"                  = @("Analyze Traces", "Analyze trace data")
        "retrieving-mlflow-traces"              = @("Retrieve Traces", "Search & retrieve traces")
        "analyze-mlflow-chat-session"           = @("Analyze Chat Session", "Chat session analysis")
        "querying-mlflow-metrics"               = @("Query Metrics", "MLflow metrics queries")
        "searching-mlflow-docs"                 = @("Search MLflow Docs", "MLflow documentation")
    }

    # Build the picker from the live inventory so new upstream skills appear
    # automatically. Order: agent skills (stable, then experimental), then MLflow.
    $items = @()
    $seen = @()
    foreach ($skill in ($script:AgentBStable + $script:AgentBExperimental + $script:MlflowSkills)) {
        if ($seen -contains $skill) { continue }
        $seen += $skill
        $label = if ($meta.ContainsKey($skill)) { $meta[$skill][0] } else { $skill }
        $hint  = if ($meta.ContainsKey($skill)) { $meta[$skill][1] } else { "" }
        # databricks-core is required -- show it locked on (can't be deselected)
        if ($skill -eq "databricks-core") {
            $items += @{ Label = $label; Value = $skill; State = $true; Hint = "$hint (required)".Trim(); Locked = $true }
        } else {
            $items += @{ Label = $label; Value = $skill; State = ($preselected -contains $skill); Hint = $hint }
        }
    }

    $selected = Select-Checkbox -Items $items
    $picked = @($selected -split ' ' | Where-Object { $_ })

    # databricks-core is always required. This also guarantees a non-empty
    # selection -- otherwise UserSkills would be empty and Resolve-Skills would
    # fall back to installing ALL skills.
    if ($picked -notcontains "databricks-core") {
        $picked = @("databricks-core") + $picked
    }
    if (@($picked | Where-Object { $_ -ne "databricks-core" }).Count -eq 0) {
        Write-Warn "Only databricks-core selected -- installing it alone (no other skills)"
    }

    $script:UserSkills = ($picked -join ',')
}

# ─── Agent skills (databricks/databricks-agent-skills via `databricks aitools`) ───

# Discover the live skill inventory from `databricks aitools list -o json`.
# Falls back to the hardcoded snapshot when the CLI is missing/old/offline.
# Idempotent -- only fetches once.
function Get-AgentBInventory {
    if ($script:AgentBStable.Count -gt 0) { return }

    $inventory = $null
    if (Get-Command databricks -ErrorAction SilentlyContinue) {
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        try {
            $raw = & databricks aitools list -o json 2>$null
            if ($LASTEXITCODE -eq 0 -and $raw) {
                $inventory = (@($raw) -join "`n") | ConvertFrom-Json
            }
        } catch {
            $inventory = $null
        }
        $ErrorActionPreference = $prevEAP
    }

    if ($inventory -and $inventory.skills) {
        $script:AgentBRelease = if ($inventory.release) { [string]$inventory.release } else { "" }
        $script:AgentBStable = @($inventory.skills | Where-Object { -not $_.experimental } | ForEach-Object { $_.name })
        $script:AgentBExperimental = @($inventory.skills | Where-Object { $_.experimental } | ForEach-Object { $_.name })
    }

    if ($script:AgentBStable.Count -eq 0) {
        $script:AgentBStable = @($script:AgentBStableFallback)
        $script:AgentBExperimental = @($script:AgentBExperimentalFallback)
        $script:AgentBRelease = ""
    }
}

# Gate for `databricks aitools` (ships with the Databricks CLI v1.0.0+).
# Interactive: offers to run the upgrade and re-checks in a loop.
# Silent/non-interactive: errors out with instructions.
# Returns $false if the user chose to skip agent skills.
function Confirm-AitoolsCli {
    $attempts = 0
    while ($true) {
        $cliVersion = ""
        if (Get-Command databricks -ErrorAction SilentlyContinue) {
            try {
                $cliOutput = & databricks --version 2>&1
                if ($cliOutput -match '(\d+\.\d+\.\d+)') { $cliVersion = $Matches[1] }
            } catch {}
        }
        if ($cliVersion -and ([version]$cliVersion -ge [version]$MinAitoolsCliVersion)) {
            return $true
        }

        $foundMsg = if ($cliVersion) { "Databricks CLI v$cliVersion is too old." } else { "Databricks CLI not found." }

        if ($script:Silent -or -not (Test-Interactive)) {
            Write-Err "$foundMsg Agent skills are installed via 'databricks aitools', which requires Databricks CLI v$MinAitoolsCliVersion+. Upgrade: winget upgrade Databricks.DatabricksCLI (or winget install Databricks.DatabricksCLI). Then re-run this installer. (Or pass --skills with only non-agent skills to skip this requirement.)"
        }

        $attempts++
        if ($attempts -gt 5) {
            Write-Warn "Databricks CLI still not at v$MinAitoolsCliVersion+ after several attempts -- skipping agent skills"
            return $false
        }

        Write-Warn "$foundMsg Agent skills are installed via 'databricks aitools', which requires Databricks CLI v$MinAitoolsCliVersion+."
        Write-Msg "Upgrade command: winget upgrade Databricks.DatabricksCLI (or winget install Databricks.DatabricksCLI if not yet installed)"
        Write-Host ""
        $choice = Read-Prompt -PromptText "Upgrade the Databricks CLI now? (y = run upgrade, r = re-check, s = skip agent skills, a = abort)" -Default "y"
        switch -Regex ($choice) {
            '^(y|yes)$' {
                $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
                if (Get-Command databricks -ErrorAction SilentlyContinue) {
                    & winget upgrade Databricks.DatabricksCLI
                } else {
                    & winget install Databricks.DatabricksCLI
                }
                if ($LASTEXITCODE -ne 0) { Write-Warn "CLI upgrade failed -- you can retry or skip" }
                $ErrorActionPreference = $prevEAP
                # Refresh PATH so a newly installed CLI is found
                $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
                $userPath    = [System.Environment]::GetEnvironmentVariable("Path", "User")
                if ($machinePath -or $userPath) {
                    $env:Path = "$machinePath;$userPath;$env:Path"
                    $env:Path = (($env:Path -split ';' | Select-Object -Unique | Where-Object { $_ }) -join ';')
                }
            }
            '^r$' { }
            '^s$' { return $false }
            '^a$' { Write-Err "Installation aborted (Databricks CLI v$MinAitoolsCliVersion+ required for agent skills)" }
        }
    }
}

# Map selected tools to `aitools --agents` tokens. Tools aitools doesn't install
# for are handled by Send-AgentSkills (which links every selected tool's dir).
function Resolve-AitoolsAgents {
    $agents = @()
    foreach ($tool in ($script:Tools -split ' ')) {
        switch ($tool) {
            "claude"      { $agents += "claude-code" }
            "cursor"      { $agents += "cursor" }
            "copilot"     { $agents += "copilot" }
            "codex"       { $agents += "codex" }
            "opencode"    { $agents += "opencode" }
            "antigravity" { $agents += "antigravity" }
        }
    }
    $script:AitoolsAgents = ($agents -join ',')
}

# Skills dir for every selected tool (deduped). aitools only fans out to some
# agents (e.g. project scope: just Claude Code + Cursor), so we link the
# canonical store into every selected tool's dir ourselves.
function Get-AgentSkillTargetDirs {
    param([string]$BaseDir)
    $dirs = @()
    foreach ($tool in ($script:Tools -split ' ')) {
        switch ($tool) {
            "claude"   { $dirs += Join-Path $BaseDir ".claude\skills" }
            "cursor"   { $dirs += Join-Path $BaseDir ".cursor\skills" }
            "copilot"  { $dirs += Join-Path $BaseDir ".github\skills" }
            "codex"    { $dirs += Join-Path $BaseDir ".agents\skills" }
            "gemini"   { $dirs += Join-Path $BaseDir ".gemini\skills" }
            "antigravity" {
                if ($script:Scope -eq "global") { $dirs += Join-Path $env:USERPROFILE ".gemini\antigravity\skills" }
                else { $dirs += Join-Path $BaseDir ".agents\skills" }
            }
            "windsurf" {
                if ($script:Scope -eq "global") { $dirs += Join-Path $env:USERPROFILE ".codeium\windsurf\skills" }
                else { $dirs += Join-Path $BaseDir ".windsurf\skills" }
            }
            "opencode" {
                if ($script:Scope -eq "global") { $dirs += Join-Path $env:USERPROFILE ".config\opencode\skills" }
                else { $dirs += Join-Path $BaseDir ".opencode\skills" }
            }
            "kiro" {
                if ($script:Scope -eq "global") { $dirs += Join-Path $env:USERPROFILE ".kiro\skills" }
                else { $dirs += Join-Path $BaseDir ".kiro\skills" }
            }
        }
    }
    return @($dirs | Select-Object -Unique)
}

# True if any selected agent skill is experimental
function Test-AgentBNeedsExperimental {
    foreach ($skill in $script:SelectedAgentBSkills) {
        if ($script:AgentBExperimental -contains $skill) { return $true }
    }
    return $false
}

# Install agent skills by delegating to `databricks aitools install`.
# aitools owns these skills afterwards (list/update/uninstall) -- they are NOT
# tracked in this installer's manifest, except for the symlinks/copies created
# for tools aitools can't target.
function Install-AgentBSkills {
    param([string]$BaseDir)

    $prevFile = Join-Path $script:StateDir ".agent-b-skills"
    if ($script:SelectedAgentBSkills.Count -eq 0 -and -not (Test-Path $prevFile)) { return }

    Write-Step "Installing agent skills (via databricks aitools)"

    # Uninstall agent skills dropped since the previous run
    if (Test-Path $prevFile) {
        $dropped = @()
        foreach ($line in (Get-Content $prevFile)) {
            $prevSkill = "$line".Trim()
            if ([string]::IsNullOrWhiteSpace($prevSkill)) { continue }
            if ($script:SelectedAgentBSkills -notcontains $prevSkill) { $dropped += $prevSkill }
        }
        if ($dropped.Count -gt 0 -and (Get-Command databricks -ErrorAction SilentlyContinue)) {
            $droppedCsv = $dropped -join ','
            $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
            & databricks aitools uninstall --scope $script:Scope --skills $droppedCsv 2>&1 | Out-Null
            $uninstallOk = ($LASTEXITCODE -eq 0)
            $ErrorActionPreference = $prevEAP
            if ($uninstallOk) {
                Write-Msg "Removed deselected agent skills: $droppedCsv"
            } else {
                Write-Warn "Could not remove deselected agent skills -- run: databricks aitools uninstall --skills $droppedCsv"
            }
        }
    }

    if ($script:SelectedAgentBSkills.Count -eq 0) {
        Remove-Item $prevFile -Force -ErrorAction SilentlyContinue
        return
    }

    if (-not (Confirm-AitoolsCli)) {
        Write-Warn "Agent skills skipped -- install later with: databricks aitools install"
        return
    }

    Resolve-AitoolsAgents
    # We always install a named subset via --skills, which the CLI only allows
    # with --skills-only (or --path): the default plugin install is all-or-nothing.
    # --skills-only writes raw skill files and the .databricks/aitools/skills store
    # that deliver logic mirrors into every other selected tool.
    $skillsCsv = $script:SelectedAgentBSkills -join ','
    $needsExperimental = Test-AgentBNeedsExperimental
    $count = $script:SelectedAgentBSkills.Count

    if ($script:AitoolsAgents) {
        Write-Msg "Delegating $count agent skills to databricks aitools (agents: $($script:AitoolsAgents))"
        $aitoolsArgs = @("aitools", "install", "--scope", $script:Scope, "--agents", $script:AitoolsAgents, "--skills", $skillsCsv, "--skills-only")
        if ($needsExperimental) { $aitoolsArgs += "--experimental" }
        $aitoolsArgs += @("-p", $script:Profile_)
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        # Capture so we can drop aitools' "Skipped <agent>: does not support
        # project-scoped skills" notices -- Send-AgentSkills below covers
        # those agents itself, so that alone isn't a real failure.
        $aitoolsOut = & databricks @aitoolsArgs 2>&1
        $installOk = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prevEAP
        $aitoolsResidual = $aitoolsOut | Where-Object { "$_" -notmatch 'does not support project-scoped skills' }
        if (-not $script:Silent -and $aitoolsResidual) {
            $aitoolsResidual | ForEach-Object { Write-Host "$_" }
        }
        if (-not $installOk -and ($aitoolsResidual | Where-Object { "$_" -match '^Error:' })) {
            if ($script:Silent) { Write-Err "databricks aitools install failed" }
            Write-Warn "databricks aitools install failed -- agent skills not installed"
            return
        }
        Write-Ok "Agent skills ($count) installed -- manage with databricks aitools list|update|uninstall"
    }

    # aitools only installs for some agents (project scope: just Claude Code +
    # Cursor). Link the canonical store into every other selected tool's dir.
    Send-AgentSkills -BaseDir $BaseDir -SkillsCsv $skillsCsv -NeedsExperimental $needsExperimental

    # Record the selection so a future profile change can uninstall dropped skills
    if (-not (Test-Path $script:StateDir)) {
        New-Item -ItemType Directory -Path $script:StateDir -Force | Out-Null
    }
    Set-Content -Path $prevFile -Value ($script:SelectedAgentBSkills -join "`n") -Encoding UTF8
}

# Link the agent skills into every selected tool's skills dir from the canonical
# store, so tools aitools doesn't install for (project scope: everything except
# Claude Code + Cursor; plus Gemini/Windsurf/Kiro, which aitools never targets)
# still get the skills. Entries aitools already created are left to aitools.
# Symlink creation can require elevated privileges on Windows, so fall back to
# copying. If no aitools-supported agent was selected there is no persistent
# store, so stage a throwaway install in a temp dir and copy real files from it.
function Send-AgentSkills {
    param([string]$BaseDir, [string]$SkillsCsv, [bool]$NeedsExperimental)

    $manifest = Join-Path $script:StateDir ".installed-skills"
    if (-not (Test-Path $script:StateDir)) {
        New-Item -ItemType Directory -Path $script:StateDir -Force | Out-Null
    }

    $mode = "link"
    $tmpDir = $null
    if ($script:Scope -eq "global") {
        $store = Join-Path $env:USERPROFILE ".databricks\aitools\skills"
    } else {
        $store = Join-Path $BaseDir ".databricks\aitools\skills"
    }

    if (-not $script:AitoolsAgents) {
        $mode = "copy"
        $tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-dev-kit-aitools-" + [System.IO.Path]::GetRandomFileName())
        New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
        $stageArgs = @("aitools", "install", "--scope", "project", "--agents", "claude-code", "--skills", $SkillsCsv, "--skills-only")
        if ($NeedsExperimental) { $stageArgs += "--experimental" }
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        Push-Location $tmpDir
        & databricks @stageArgs 2>&1 | Out-Null
        $stageOk = ($LASTEXITCODE -eq 0)
        Pop-Location
        $ErrorActionPreference = $prevEAP
        if (-not $stageOk) {
            Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
            Write-Warn "Could not stage agent skills for: $(($script:Tools -split ' ') -join ',')"
            return
        }
        $store = Join-Path $tmpDir ".databricks\aitools\skills"
    }

    foreach ($dir in (Get-AgentSkillTargetDirs -BaseDir $BaseDir)) {
        if ([string]::IsNullOrWhiteSpace($dir)) { continue }
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        $usedMode = $mode
        $made = 0
        foreach ($skill in $script:SelectedAgentBSkills) {
            $srcPath = Join-Path $store $skill
            if (-not (Test-Path $srcPath)) {
                Write-Warn "Agent skill '$skill' missing from aitools store -- skipped"
                continue
            }
            $destPath = Join-Path $dir $skill
            $destItem = Get-Item -LiteralPath $destPath -Force -ErrorAction SilentlyContinue
            # In link mode, leave anything aitools already placed (e.g. Claude
            # Code / Cursor) to aitools -- it owns and updates those.
            if ($mode -eq "link" -and $destItem) { continue }
            if ($destItem) {
                if ($destItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                    $destItem.Delete()
                } else {
                    Remove-Item -LiteralPath $destPath -Recurse -Force
                }
            }
            if ($mode -eq "link") {
                # Project-scope dirs are all <base>\.<tool>\skills (2 levels deep),
                # so a relative link survives moving the project directory.
                $target = $srcPath
                if ($script:Scope -eq "project") { $target = "..\..\.databricks\aitools\skills\$skill" }
                try {
                    New-Item -ItemType SymbolicLink -Path $destPath -Target $target -ErrorAction Stop | Out-Null
                } catch {
                    # Symlinks may require Developer Mode / admin on Windows -- copy instead
                    Copy-Item -Recurse $srcPath $destPath
                    $usedMode = "copy"
                }
            } else {
                Copy-Item -Recurse $srcPath $destPath
            }
            Add-Content -Path $manifest -Value "$dir|$skill" -Encoding UTF8
            $made++
        }
        if ($made -gt 0) {
            $shortDir = $dir -replace [regex]::Escape($env:USERPROFILE), '~'
            Write-Ok "Agent skills ($made, $usedMode) -> $shortDir"
        }
    }

    if ($tmpDir) { Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue }
}

# ─── Raw-fetch ref resolution (mlflow) ───────────────────────

# Resolve-Ref -Repo <owner/repo> -Requested <ref>
#   ""/"latest" -> highest stable semver tag (prereleases excluded unless
#                  INCLUDE_PRERELEASES=1; falls back to main if no tags).
#   main/master -> passed through.
#   anything else -> verified to exist as a tag/branch/SHA (fails loud).
# Uses `git ls-remote` (no API rate limits; git is a hard prerequisite).
function Resolve-Ref {
    param([string]$Repo, [string]$Requested)

    $gitUrl = "https://github.com/$Repo.git"
    $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"

    if ([string]::IsNullOrWhiteSpace($Requested) -or $Requested -eq "latest") {
        $tags = @(& git ls-remote --tags --refs $gitUrl 2>$null | ForEach-Object {
            ("$_" -split "`t")[-1] -replace '^refs/tags/', ''
        })
        $ErrorActionPreference = $prevEAP
        $pattern = '^v?\d+\.\d+\.\d+$'
        if ($script:IncludePrereleases) { $pattern = '^v?\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?$' }
        $best = $tags | Where-Object { $_ -match $pattern } |
            Sort-Object { [version](($_ -replace '^v', '') -replace '-.*$', '') } |
            Select-Object -Last 1
        if ($best) { return $best }
        Write-Warn "Could not resolve latest tag for $Repo -- falling back to main"
        return "main"
    }

    if ($Requested -in @("main", "master")) {
        $ErrorActionPreference = $prevEAP
        return $Requested
    }

    $found = & git ls-remote $gitUrl "refs/tags/$Requested" "refs/heads/$Requested" 2>$null
    $ErrorActionPreference = $prevEAP
    if ($found) { return $Requested }
    try {
        # bare commit SHA (not addressable via ls-remote)
        Invoke-WebRequest -Uri "https://api.github.com/repos/$Repo/commits/$Requested" -UseBasicParsing -ErrorAction Stop | Out-Null
        return $Requested
    } catch {
        Write-Err "Ref '$Requested' not found in $Repo"
    }
}

# Resolve refs for all selected raw-fetch sources (records script vars for the
# fetch URLs, summary, dry run, and lockfile)
function Resolve-FetchRefs {
    if ($script:SelectedMlflowSkills.Count -gt 0) {
        $script:MlflowResolvedRef = Resolve-Ref -Repo "mlflow/skills" -Requested $script:MlflowRef
    }
}

# Best-effort commit SHA for a ref (empty on failure). Prefers the peeled
# tag object (^{}) so annotated tags resolve to the commit they point at.
function Get-GitHubSha {
    param([string]$Repo, [string]$Ref)

    $sha = ""
    $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $lsOut = @(& git ls-remote "https://github.com/$Repo.git" "refs/tags/$Ref^{}" "refs/tags/$Ref" "refs/heads/$Ref" 2>$null)
    $ErrorActionPreference = $prevEAP
    if ($lsOut.Count -gt 0) {
        $peeled = $lsOut | Where-Object { $_ -match '\^\{\}' } | Select-Object -First 1
        $line = if ($peeled) { $peeled } else { $lsOut[0] }
        if ($line) { $sha = ("$line" -split "`t")[0] }
    }
    if (-not $sha) {
        try {
            $resp = Invoke-WebRequest -Uri "https://api.github.com/repos/$Repo/commits/$Ref" -UseBasicParsing -ErrorAction Stop
            $sha = [string](($resp.Content | ConvertFrom-Json).sha)
        } catch {}
    }
    return $sha
}

# Record what was installed and from where (skills.lock in the scope-local state dir)
function Write-Lockfile {
    if (-not (Test-Path $script:StateDir)) {
        New-Item -ItemType Directory -Path $script:StateDir -Force | Out-Null
    }
    $lock = Join-Path $script:StateDir "skills.lock"
    $now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $sources = [ordered]@{}

    if ($script:SelectedMlflowSkills.Count -gt 0) {
        $sha = Get-GitHubSha -Repo "mlflow/skills" -Ref $script:MlflowResolvedRef
        $sources["mlflow/skills"] = [ordered]@{
            requested_ref = $script:MlflowRef
            resolved_kind = "branch"
            resolved_ref  = $script:MlflowResolvedRef
            resolved_sha  = "$sha"
            fetched_at    = $now
        }
    }
    if ($script:SelectedAgentBSkills.Count -gt 0) {
        $cliVersion = ""
        if (Get-Command databricks -ErrorAction SilentlyContinue) {
            try {
                $cliOutput = & databricks --version 2>&1
                if ($cliOutput -match '(\d+\.\d+\.\d+)') { $cliVersion = $Matches[1] }
            } catch {}
        }
        $sources["databricks/databricks-agent-skills"] = [ordered]@{
            install_method = "databricks-aitools"
            cli_version    = $cliVersion
            skills_release = "$($script:AgentBRelease)"
            fetched_at     = $now
        }
    }

    if ($sources.Count -eq 0) { return }
    [ordered]@{ sources = $sources } | ConvertTo-Json -Depth 5 | Set-Content -Path $lock -Encoding UTF8
}

# ─── Dry run ──────────────────────────────────────────────────
function Show-DryRunReport {
    Resolve-AitoolsAgents
    Write-Host ""
    Write-Host "Dry run -- nothing was installed" -ForegroundColor White
    Write-Host "--------------------------------"
    $mlflowList = if ($script:SelectedMlflowSkills.Count -gt 0) { $script:SelectedMlflowSkills -join ' ' } else { "<none>" }
    $mlflowRefDisplay = if ($script:MlflowResolvedRef) { $script:MlflowResolvedRef } else { "n/a" }
    Write-Msg "MLflow skills @ ${mlflowRefDisplay}: $mlflowList"
    if ($script:SelectedAgentBSkills.Count -gt 0) {
        $skillsCsv = $script:SelectedAgentBSkills -join ','
        $expFlag = if (Test-AgentBNeedsExperimental) { " --experimental" } else { "" }
        $releaseSuffix = if ($script:AgentBRelease) { " @ $($script:AgentBRelease)" } else { "" }
        Write-Msg "Agent skills (databricks-agent-skills$releaseSuffix): $($script:SelectedAgentBSkills -join ' ')"
        if ($script:AitoolsAgents) {
            Write-Msg "Would run: databricks aitools install --scope $($script:Scope) --agents $($script:AitoolsAgents) --skills $skillsCsv --skills-only$expFlag -p $($script:Profile_)"
        }
        $mode = if ($script:AitoolsAgents) { "symlink from the aitools canonical store" } else { "copy via a temp-dir aitools install" }
        Write-Msg "Would deliver agent skills to every selected tool ($mode); entries aitools creates are left to aitools:"
        $dryBaseDir = if ($script:Scope -eq "global") { $env:USERPROFILE } else { (Get-Location).Path }
        foreach ($dir in (Get-AgentSkillTargetDirs -BaseDir $dryBaseDir)) {
            Write-Msg "  -> $dir"
        }
    } else {
        Write-Msg "Agent skills: <none>"
    }
    Write-Host ""
}

# ─── Install skills ──────────────────────────────────────────
function Install-Skills {
    param([string]$BaseDir)

    Write-Step "Installing skills"

    $dirs = @()
    foreach ($tool in ($script:Tools -split ' ')) {
        switch ($tool) {
            "claude" { $dirs += Join-Path $BaseDir ".claude\skills" }
            "cursor" { $dirs += Join-Path $BaseDir ".cursor\skills" }
            "copilot" { $dirs += Join-Path $BaseDir ".github\skills" }
            "codex"   { $dirs += Join-Path $BaseDir ".agents\skills" }
            "gemini"  { $dirs += Join-Path $BaseDir ".gemini\skills" }
            "antigravity" {
                if ($script:Scope -eq "global") {
                    $dirs += Join-Path $env:USERPROFILE ".gemini\antigravity\skills"
                } else {
                    $dirs += Join-Path $BaseDir ".agents\skills"
                }
            }
            "windsurf" {
                if ($script:Scope -eq "global") {
                    $dirs += Join-Path $env:USERPROFILE ".codeium\windsurf\skills"
                } else {
                    $dirs += Join-Path $BaseDir ".windsurf\skills"
                }
            }
            "opencode" {
                if ($script:Scope -eq "global") {
                    $dirs += Join-Path $env:USERPROFILE ".config\opencode\skills"
                } else {
                    $dirs += Join-Path $BaseDir ".opencode\skills"
                }
            }
            "kiro" {
                if ($script:Scope -eq "global") {
                    $dirs += Join-Path $env:USERPROFILE ".kiro\skills"
                } else {
                    $dirs += Join-Path $BaseDir ".kiro\skills"
                }
            }
        }
    }
    $dirs = $dirs | Select-Object -Unique

    # Count selected skills for display
    $mlflowCount = $script:SelectedMlflowSkills.Count
    Write-Msg "Installing $mlflowCount MLflow skills (Databricks skills are installed separately via databricks aitools)"

    # Skills this installer manages directly (MLflow). Agent skills are
    # deliberately NOT in this set: any same-named entry from an older install is
    # a stale real copy that must be removed -- `databricks aitools` will not
    # overwrite an existing real directory, so leaving it would shadow the new
    # install. (Symlinks for tools aitools can't target are re-created each run.)
    $allNewSkills = @()
    $allNewSkills += $script:SelectedMlflowSkills

    # Clean up previously installed skills that are no longer selected
    # Check scope-local manifest first, fall back to global for upgrades from older versions
    $manifest = Join-Path $script:StateDir ".installed-skills"
    if (-not (Test-Path $manifest) -and $script:Scope -eq "project" -and (Test-Path (Join-Path $script:InstallDir ".installed-skills"))) {
        $manifest = Join-Path $script:InstallDir ".installed-skills"
    }
    if (Test-Path $manifest) {
        foreach ($line in (Get-Content $manifest)) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            $parts = $line -split '\|', 2
            if ($parts.Count -ne 2) { continue }
            $prevDir = $parts[0]
            $prevSkill = $parts[1]
            # Skip if this skill is still selected
            if ($allNewSkills -contains $prevSkill) { continue }
            # Remove real dirs and symlinks alike
            $prevPath = Join-Path $prevDir $prevSkill
            $prevItem = Get-Item -LiteralPath $prevPath -Force -ErrorAction SilentlyContinue
            if ($prevItem) {
                if ($prevItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                    $prevItem.Delete()
                } else {
                    Remove-Item -LiteralPath $prevPath -Recurse -Force
                }
                Write-Msg "Removed previously installed skill: $prevSkill"
            }
        }
    }

    # Start fresh manifest
    $manifestEntries = @()

    # Raw-fetch URL pinned to the resolved ref
    $mlflowRef = if ($script:MlflowResolvedRef) { $script:MlflowResolvedRef } else { "main" }
    $mlflowRawUrl = "$MlflowBaseUrl/$mlflowRef"

    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        $shortDir = $dir -replace [regex]::Escape($env:USERPROFILE), '~'

        # Install MLflow skills from mlflow/skills repo
        if ($script:SelectedMlflowSkills.Count -gt 0) {
            $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
            foreach ($skill in $script:SelectedMlflowSkills) {
                $destDir = Join-Path $dir $skill
                if (-not (Test-Path $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                $url = "$mlflowRawUrl/$skill/SKILL.md"
                try {
                    Invoke-WebRequest -Uri $url -OutFile (Join-Path $destDir "SKILL.md") -UseBasicParsing -ErrorAction Stop
                    foreach ($ref in @("reference.md", "examples.md", "api.md")) {
                        try {
                            Invoke-WebRequest -Uri "$mlflowRawUrl/$skill/$ref" -OutFile (Join-Path $destDir $ref) -UseBasicParsing -ErrorAction Stop
                        } catch {}
                    }
                    $manifestEntries += "$dir|$skill"
                } catch {
                    Remove-Item -Recurse -Force $destDir -ErrorAction SilentlyContinue
                }
            }
            $ErrorActionPreference = $prevEAP
            Write-Ok "MLflow skills ($mlflowCount, @ $mlflowRef) -> $shortDir"
        }
    }

    # Save manifest and profile to scope-local state directory
    if (-not (Test-Path $script:StateDir)) {
        New-Item -ItemType Directory -Path $script:StateDir -Force | Out-Null
    }
    $manifest = Join-Path $script:StateDir ".installed-skills"
    Set-Content -Path $manifest -Value ($manifestEntries -join "`n") -Encoding UTF8

    # Save selected profile for future reinstalls
    if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
        Set-Content -Path (Join-Path $script:StateDir ".skills-profile") -Value "custom:$($script:UserSkills)" -Encoding UTF8
    } else {
        $profileValue = if ([string]::IsNullOrWhiteSpace($script:SkillsProfile)) { "all" } else { $script:SkillsProfile }
        Set-Content -Path (Join-Path $script:StateDir ".skills-profile") -Value $profileValue -Encoding UTF8
    }
}

# ─── Write MCP configs ───────────────────────────────────────
# Write/merge an MCP server entry into a JSON config.
#   -Path     target config file
#   -RootKey  top-level key: "mcpServers" (Claude/Cursor/Gemini/Windsurf/Kiro)
#             or "servers" (Copilot)
#   -Defer    include Claude's defer_loading hint
# Replaces the old Write-McpJson / Write-CopilotMcpJson / Write-GeminiMcpJson
# trio, which differed only in those two parameters. Merging is decoupled from
# whether the venv exists yet, so an existing config is never clobbered.
function Write-McpJsonConfig {
    param([string]$Path, [string]$RootKey, [bool]$Defer)

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    # Backup existing
    if (Test-Path $Path) {
        Copy-Item $Path "$Path.bak" -Force
        Write-Msg "Backed up $(Split-Path $Path -Leaf) -> $(Split-Path $Path -Leaf).bak"
    }

    # Try to merge with existing config (independent of whether the venv exists)
    $existing = $null
    if (Test-Path $Path) {
        try { $existing = Get-Content $Path -Raw | ConvertFrom-Json } catch { $existing = $null }
    }

    # Use forward slashes for cross-platform JSON compatibility
    $pythonPath = $script:VenvPython -replace '\\', '/'
    $entryPath  = $script:McpEntry -replace '\\', '/'

    if ($existing) {
        if (-not $existing.$RootKey) {
            $existing | Add-Member -NotePropertyName $RootKey -NotePropertyValue ([PSCustomObject]@{}) -Force
        }
        $dbProps = [ordered]@{ command = $pythonPath; args = @($entryPath) }
        if ($Defer) { $dbProps.defer_loading = $true }
        $dbProps.env = [PSCustomObject]@{ DATABRICKS_CONFIG_PROFILE = $script:Profile_ }
        $existing.$RootKey | Add-Member -NotePropertyName "databricks" -NotePropertyValue ([PSCustomObject]$dbProps) -Force
        $existing | ConvertTo-Json -Depth 10 | Set-Content $Path -Encoding UTF8
    } else {
        $deferLine = if ($Defer) { "`n      `"defer_loading`": true," } else { "" }
        $json = @"
{
  "$RootKey": {
    "databricks": {
      "command": "$pythonPath",
      "args": ["$entryPath"],$deferLine
      "env": {"DATABRICKS_CONFIG_PROFILE": "$($script:Profile_)"}
    }
  }
}
"@
        Set-Content -Path $Path -Value $json -Encoding UTF8
    }
}

function Write-McpToml {
    param([string]$Path)

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    # Check if already configured
    if (Test-Path $Path) {
        $content = Get-Content $Path -Raw
        if ($content -match 'mcp_servers\.databricks') { return }
        Copy-Item $Path "$Path.bak" -Force
        Write-Msg "Backed up $(Split-Path $Path -Leaf) -> $(Split-Path $Path -Leaf).bak"
    }

    $pythonPath = $script:VenvPython -replace '\\', '/'
    $entryPath  = $script:McpEntry -replace '\\', '/'
    $tomlBlock = @"

[mcp_servers.databricks]
command = "$pythonPath"
args = ["$entryPath"]
"@
    Add-Content -Path $Path -Value $tomlBlock -Encoding UTF8
}

function Write-OpenCodeJson {
    param([string]$Path)

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    # Backup existing
    if (Test-Path $Path) {
        Copy-Item $Path "$Path.bak" -Force
        Write-Msg "Backed up $(Split-Path $Path -Leaf) -> $(Split-Path $Path -Leaf).bak"
    }

    # Try to merge with existing config
    $existing = $null
    if ((Test-Path $Path) -and (Test-Path $script:VenvPython)) {
        try {
            $existing = Get-Content $Path -Raw | ConvertFrom-Json
        } catch {
            $existing = $null
        }
    }

    if ($existing) {
        if (-not $existing.'$schema') {
            $existing | Add-Member -NotePropertyName '$schema' -NotePropertyValue 'https://opencode.ai/config.json' -Force
        }
        if (-not $existing.mcp) {
            $existing | Add-Member -NotePropertyName "mcp" -NotePropertyValue ([PSCustomObject]@{}) -Force
        }
        $dbEntry = [PSCustomObject]@{
            type        = "local"
            command     = @($script:VenvPython -replace '\\', '/', $script:McpEntry -replace '\\', '/')
            environment = [PSCustomObject]@{ DATABRICKS_CONFIG_PROFILE = $script:Profile_ }
            enabled     = $true
        }
        $existing.mcp | Add-Member -NotePropertyName "databricks" -NotePropertyValue $dbEntry -Force
        $existing | ConvertTo-Json -Depth 10 | Set-Content $Path -Encoding UTF8
    } else {
        $pythonPath = $script:VenvPython -replace '\\', '/'
        $entryPath  = $script:McpEntry -replace '\\', '/'
        $json = @"
{
  "`$schema": "https://opencode.ai/config.json",
  "mcp": {
    "databricks": {
      "type": "local",
      "command": ["$pythonPath", "$entryPath"],
      "environment": {"DATABRICKS_CONFIG_PROFILE": "$($script:Profile_)"},
      "enabled": true
    }
  }
}
"@
        Set-Content -Path $Path -Value $json -Encoding UTF8
    }
}

function Write-GeminiMd {
    param([string]$Path)

    if (Test-Path $Path) { return }  # Don't overwrite existing file

    $content = @"
# Databricks AI Dev Kit

You have access to Databricks skills and MCP tools installed by the Databricks AI Dev Kit.

## Available MCP Tools

The ``databricks`` MCP server provides 50+ tools for interacting with Databricks, including:
- SQL execution and warehouse management
- Unity Catalog operations (tables, volumes, schemas)
- Jobs and workflow management
- Model serving endpoints
- Genie spaces and AI/BI dashboards
- Databricks Apps deployment

## Available Skills

Skills are installed in ``.gemini/skills/`` and provide patterns and best practices for:
- Spark Declarative Pipelines, Structured Streaming
- Databricks Jobs, Asset Bundles
- Unity Catalog, SQL, Genie
- MLflow evaluation and tracing
- Model Serving, Vector Search
- Databricks Apps
- And more

## Getting Started

Try asking: "List my SQL warehouses" or "Show my Unity Catalog schemas"
"@
    Set-Content -Path $Path -Value $content -Encoding UTF8
    Write-Ok "GEMINI.md"
}

# Merge a SessionStart version-check hook into a Claude settings.json (parity
# with the bash installer's write_claude_hook). The command runs check_update.sh
# via bash; forward slashes keep it working under Git Bash on Windows.
function Write-ClaudeHook {
    param([string]$Path, [string]$Script)

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    $cmd = "bash " + ($Script -replace '\\', '/')

    $cfg = $null
    if (Test-Path $Path) {
        try { $cfg = Get-Content $Path -Raw | ConvertFrom-Json } catch { $cfg = $null }
    }
    if (-not $cfg) { $cfg = [PSCustomObject]@{} }

    if (-not $cfg.hooks) {
        $cfg | Add-Member -NotePropertyName "hooks" -NotePropertyValue ([PSCustomObject]@{}) -Force
    }
    if (-not $cfg.hooks.SessionStart) {
        $cfg.hooks | Add-Member -NotePropertyName "SessionStart" -NotePropertyValue @() -Force
    }

    # Already configured? (look for an existing check_update.sh hook)
    foreach ($group in @($cfg.hooks.SessionStart)) {
        foreach ($h in @($group.hooks)) {
            if ($h.command -and ($h.command -match 'check_update\.sh')) { return }
        }
    }

    $hookEntry = [PSCustomObject]@{ type = "command"; command = $cmd; timeout = 5 }
    $cfg.hooks.SessionStart = @($cfg.hooks.SessionStart) + [PSCustomObject]@{ hooks = @($hookEntry) }
    $cfg | ConvertTo-Json -Depth 10 | Set-Content $Path -Encoding UTF8
}

function Write-McpConfigs {
    param([string]$BaseDir)

    Write-Step "Configuring MCP"

    foreach ($tool in ($script:Tools -split ' ')) {
        switch ($tool) {
            "claude" {
                # Global config lives in ~/.claude.json (the file Claude Code reads),
                # matching the bash installer.
                if ($script:Scope -eq "global") {
                    Write-McpJsonConfig (Join-Path $env:USERPROFILE ".claude.json") "mcpServers" $true
                } else {
                    Write-McpJsonConfig (Join-Path $BaseDir ".mcp.json") "mcpServers" $true
                }
                Write-Ok "Claude MCP config"
                # Add the version-check SessionStart hook (parity with bash)
                $checkScript = Join-Path $script:RepoDir ".claude-plugin\check_update.sh"
                if ($script:Scope -eq "global") {
                    Write-ClaudeHook (Join-Path $env:USERPROFILE ".claude\settings.json") $checkScript
                } else {
                    Write-ClaudeHook (Join-Path $BaseDir ".claude\settings.json") $checkScript
                }
                Write-Ok "Claude update check hook"
            }
            "cursor" {
                if ($script:Scope -eq "global") {
                    Write-Warn "Cursor global: manual MCP configuration required"
                    Write-Msg "  1. Open Cursor -> Settings -> Cursor Settings -> Tools & MCP"
                    Write-Msg "  2. Click New MCP Server"
                    Write-Msg "  3. Add the following JSON config:"
                    Write-Msg "     {"
                    Write-Msg "       `"mcpServers`": {"
                    Write-Msg "         `"databricks`": {"
                    Write-Msg "           `"command`": `"$($script:VenvPython)`","
                    Write-Msg "           `"args`": [`"$($script:McpEntry)`"],"
                    Write-Msg "           `"env`": {`"DATABRICKS_CONFIG_PROFILE`": `"$($script:Profile_)`"}"
                    Write-Msg "         }"
                    Write-Msg "       }"
                    Write-Msg "     }"
                } else {
                    Write-McpJsonConfig (Join-Path $BaseDir ".cursor\mcp.json") "mcpServers" $true
                    Write-Ok "Cursor MCP config"
                }
                Write-Warn "Cursor: MCP servers are disabled by default."
                Write-Msg "  Enable in: Cursor -> Settings -> Cursor Settings -> Tools & MCP -> Toggle 'databricks'"
            }
            "copilot" {
                if ($script:Scope -eq "global") {
                    Write-Warn "Copilot global: configure MCP in VS Code settings (Ctrl+Shift+P -> 'MCP: Open User Configuration')"
                    Write-Msg "  Command: $($script:VenvPython) | Args: $($script:McpEntry)"
                } else {
                    Write-McpJsonConfig (Join-Path $BaseDir ".vscode\mcp.json") "servers" $false
                    Write-Ok "Copilot MCP config (.vscode/mcp.json)"
                }
                Write-Warn "Copilot: MCP servers must be enabled manually."
                Write-Msg "  In Copilot Chat, click 'Configure Tools' (tool icon, bottom-right) and enable 'databricks'"
            }
            "codex" {
                if ($script:Scope -eq "global") {
                    Write-McpToml (Join-Path $env:USERPROFILE ".codex\config.toml")
                } else {
                    Write-McpToml (Join-Path $BaseDir ".codex\config.toml")
                }
                Write-Ok "Codex MCP config"
            }
            "gemini" {
                if ($script:Scope -eq "global") {
                    Write-McpJsonConfig (Join-Path $env:USERPROFILE ".gemini\settings.json") "mcpServers" $false
                } else {
                    Write-McpJsonConfig (Join-Path $BaseDir ".gemini\settings.json") "mcpServers" $false
                }
                Write-Ok "Gemini CLI MCP config"
            }
            "antigravity" {
                if ($script:Scope -eq "project") {
                    Write-Warn "Antigravity only supports global MCP configuration."
                    Write-Msg "  Config written to ~/.gemini/antigravity/mcp_config.json"
                }
                Write-McpJsonConfig (Join-Path $env:USERPROFILE ".gemini\antigravity\mcp_config.json") "mcpServers" $false
                Write-Ok "Antigravity MCP config"
            }
            "windsurf" {
                if ($script:Scope -eq "project") {
                    Write-Warn "Windsurf only supports global MCP configuration."
                    Write-Msg "  Config written to ~/.codeium/windsurf/mcp_config.json"
                }
                Write-McpJsonConfig (Join-Path $env:USERPROFILE ".codeium\windsurf\mcp_config.json") "mcpServers" $true
                Write-Ok "Windsurf MCP config"
            }
            "opencode" {
                if ($script:Scope -eq "global") {
                    Write-OpenCodeJson (Join-Path $env:USERPROFILE ".config\opencode\opencode.json")
                } else {
                    Write-OpenCodeJson (Join-Path $BaseDir "opencode.json")
                }
                Write-Ok "OpenCode MCP config"
            }
            "kiro" {
                if ($script:Scope -eq "global") {
                    $kiroSettings = Join-Path $env:USERPROFILE ".kiro\settings"
                } else {
                    $kiroSettings = Join-Path $BaseDir ".kiro\settings"
                }
                if (-not (Test-Path $kiroSettings)) { New-Item -ItemType Directory -Path $kiroSettings -Force | Out-Null }
                Write-McpJsonConfig (Join-Path $kiroSettings "mcp.json") "mcpServers" $true
                Write-Ok "Kiro MCP config"
            }
        }
    }
}

# ─── Save version ────────────────────────────────────────────
function Save-Version {
    try {
        $ver = (Invoke-WebRequest -Uri "$RawUrl/VERSION" -UseBasicParsing -ErrorAction Stop).Content.Trim()
    } catch {
        $ver = "dev"
    }
    if ($ver -match '(404|Not Found|error)') { $ver = "dev" }

    # $script:InstallDir is only created during MCP setup; a skills-only run never
    # clones, so ensure it exists before writing the version file.
    if (-not (Test-Path $script:InstallDir)) {
        New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null
    }
    Set-Content -Path (Join-Path $script:InstallDir "version") -Value $ver -Encoding UTF8

    if ($script:Scope -eq "project") {
        $projDir = Join-Path (Get-Location) ".ai-dev-kit"
        if (-not (Test-Path $projDir)) {
            New-Item -ItemType Directory -Path $projDir -Force | Out-Null
        }
        Set-Content -Path (Join-Path $projDir "version") -Value $ver -Encoding UTF8
    }
}

# ─── Summary ─────────────────────────────────────────────────
function Show-Summary {
    if ($script:Silent) { return }

    Write-Host ""
    Write-Host "Installation complete!" -ForegroundColor Green
    Write-Host "--------------------------------"
    Write-Msg "Location: $($script:InstallDir)"
    Write-Msg "Scope:    $($script:Scope)"
    Write-Msg "Tools:    $(($script:Tools -split ' ') -join ', ')"
    if ($script:SelectedAgentBSkills.Count -gt 0) {
        Write-Msg "Agent skills are managed by databricks aitools -- update with databricks aitools update"
    }
    Write-Host ""
    Write-Msg "Next steps:"
    $step = 1
    if ($script:InstallMcp -and ($script:Tools -match 'cursor')) {
        Write-Msg "$step. Enable MCP in Cursor: Cursor -> Settings -> Cursor Settings -> Tools & MCP -> Toggle 'databricks'"
        $step++
    }
    if ($script:Tools -match 'copilot') {
        if ($script:InstallMcp) {
            Write-Msg "$step. In Copilot Chat, click 'Configure Tools' (tool icon, bottom-right) and enable 'databricks'"
            $step++
        }
        Write-Msg "$step. Use Copilot in Agent mode to access Databricks skills"
        $step++
    }
    if ($script:Tools -match 'gemini') {
        Write-Msg "$step. Launch Gemini CLI in your project: gemini"
        $step++
    }
    if ($script:Tools -match 'antigravity') {
        Write-Msg "$step. Open your project in Antigravity to use Databricks skills and MCP tools"
        $step++
    }
    if ($script:InstallMcp -and ($script:Tools -match 'windsurf')) {
        Write-Msg "$step. Restart Windsurf to pick up the databricks MCP server (Windsurf -> Settings -> Windsurf Settings -> MCP)"
        $step++
    }
    if ($script:Tools -match 'opencode') {
        Write-Msg "$step. Launch OpenCode in your project: opencode"
        $step++
    }
    if ($script:Tools -match 'kiro') {
        Write-Msg "$step. Open your project in Kiro to use Databricks skills and MCP tools"
        $step++
    }
    Write-Msg "$step. Open your project in your tool of choice"
    $step++
    Write-Msg "$step. Start prompting your AI assistant to interact with Databricks"
    Write-Host ""
}

# ─── Scope prompt ─────────────────────────────────────────────
function Invoke-PromptScope {
    if ($script:Silent) { return }

    Write-Host ""
    Write-Host "  Select installation scope" -ForegroundColor White

    # Keep hints short — long ones wrap past the window width and break the
    # cursor repositioning in Select-Radio (each arrow press would stack a copy).
    $items = @(
        @{ Label = "Project"; Value = "project"; Selected = $true;  Hint = "Current directory (.claude/, etc.)" }
        @{ Label = "Global";  Value = "global";  Selected = $false; Hint = "Home directory (~/.claude/, etc.)" }
    )
    $script:Scope = Select-Radio -Items $items
}

# ─── Auth prompt ──────────────────────────────────────────────
function Invoke-PromptAuth {
    if ($script:Silent) { return }

    # Check if profile already has a token
    $cfgFile = Join-Path $env:USERPROFILE ".databrickscfg"
    if (Test-Path $cfgFile) {
        $inProfile = $false
        foreach ($line in (Get-Content $cfgFile)) {
            if ($line -match '^\[([a-zA-Z0-9_-]+)\]$') {
                $inProfile = $Matches[1] -eq $script:Profile_
            } elseif ($inProfile -and $line -match '^token\s*=') {
                Write-Ok "Profile $($script:Profile_) already has a token configured -- skipping auth"
                return
            }
        }
    }

    # Check env var
    if ($env:DATABRICKS_TOKEN) {
        Write-Ok "DATABRICKS_TOKEN is set -- skipping auth"
        return
    }

    # Check for CLI
    if (-not (Get-Command databricks -ErrorAction SilentlyContinue)) {
        Write-Warn "Databricks CLI not installed -- cannot run OAuth login"
        Write-Msg "  Install it, then run: databricks auth login --profile $($script:Profile_)"
        return
    }

    Write-Host ""
    Write-Msg "Authentication"
    Write-Msg "This will run OAuth login for profile $($script:Profile_)"
    Write-Msg "A browser window will open for you to authenticate with your Databricks workspace."
    Write-Host ""
    $runAuth = Read-Prompt -PromptText "Run databricks auth login --profile $($script:Profile_) now? (y/n)" -Default "y"
    if ($runAuth -in @("y", "Y", "yes")) {
        Write-Host ""
        & databricks auth login --profile $script:Profile_
    }
}

# ─── Main ─────────────────────────────────────────────────────
# When a branch/tag is explicitly requested, hand off to THAT branch's own
# installer so its real install steps run -- this script only knows the current
# version's steps. Prints the command and exits without installing.
# DEVKIT_BOOTSTRAPPED (set in the printed command) suppresses the hand-off so
# the target installer proceeds normally.
function Invoke-BranchHandoff {
    if (-not $script:BranchExplicit) { return }
    if ($env:DEVKIT_BOOTSTRAPPED) { return }

    $url = "https://raw.githubusercontent.com/$Owner/$Repo/$Branch/install.ps1"

    # Silent/automated runs can't be handed off interactively -- fail loudly
    # (non-zero, message on stderr) so callers don't mistake it for success.
    if ($script:Silent) {
        [Console]::Error.WriteLine("Cannot install --branch ${Branch}: run that version's own installer (set DEVKIT_BOOTSTRAPPED=1 to bypass).")
        [Console]::Error.WriteLine("  `$env:DEVKIT_BOOTSTRAPPED='1'; `$env:AIDEVKIT_BRANCH='${Branch}'; irm $url -OutFile install.ps1; .\install.ps1 --silent")
        exit 1
    }

    Write-Host ""
    Write-Host "Install a specific version ($Branch)" -ForegroundColor White
    Write-Host "--------------------------------"
    Write-Host "  This script runs the current version's install steps. To install"
    Write-Host "  $Branch using its own installer, run:"
    Write-Host ""
    Write-Host "    `$env:DEVKIT_BOOTSTRAPPED = '1'" -ForegroundColor Green
    Write-Host "    `$env:AIDEVKIT_BRANCH = '$Branch'" -ForegroundColor Green
    Write-Host "    irm $url -OutFile install.ps1" -ForegroundColor Green
    Write-Host "    .\install.ps1" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Append any options that version supports (use --help to see them)." -ForegroundColor DarkGray
    Write-Host "  Nothing was installed." -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

# ─── Pre-install check: an OLD install that predates the aitools flow ──────────
# The current installer delegates skills to `databricks aitools`, which manages
# them in a store (.databricks\aitools\skills\.state.json) and links them into each
# tool's skills dir. Older AI Dev Kit installs instead COPIED real skill directories
# in place and/or installed the Claude Code plugin — neither is managed by aitools,
# so reinstalling over them can leave stale/duplicate skills. We detect that (for the
# scope we're installing into) and offer a full uninstall first. Skills already
# managed by aitools — a CLI upgrade OR a prior run of THIS installer — are NOT
# flagged: the aitools store is our evidence they did not come from the old flow.
function Test-PriorInstall {
    $script:PriorInstallKind = ""
    $script:PriorInstallSummary = @()
    $home_ = $env:USERPROFILE
    if ($script:Scope -eq "global") { $baseDir = $home_ } else { $baseDir = (Get-Location).Path }
    $aitoolsState = Join-Path $baseDir ".databricks\aitools\skills\.state.json"

    if ($script:Scope -eq "global") {
        $roots = @(
            (Join-Path $home_ ".claude\skills"), (Join-Path $home_ ".cursor\skills"),
            (Join-Path $home_ ".github\skills"), (Join-Path $home_ ".agents\skills"),
            (Join-Path $home_ ".gemini\skills"), (Join-Path $home_ ".gemini\antigravity\skills"),
            (Join-Path $home_ ".codeium\windsurf\skills"), (Join-Path $home_ ".config\opencode\skills"),
            (Join-Path $home_ ".kiro\skills")
        )
    } else {
        $roots = @(
            (Join-Path $baseDir ".claude\skills"), (Join-Path $baseDir ".cursor\skills"),
            (Join-Path $baseDir ".github\skills"), (Join-Path $baseDir ".agents\skills"),
            (Join-Path $baseDir ".gemini\skills"), (Join-Path $baseDir ".windsurf\skills"),
            (Join-Path $baseDir ".opencode\skills"), (Join-Path $baseDir ".kiro\skills")
        )
    }

    # Count real (non-reparse-point) skill dirs under known names. aitools links its
    # skills and always writes .state.json, so when that store exists the skills are
    # CLI-managed (upgrade path) and are NOT flagged — the "current flow" evidence.
    $legacy = 0
    if (-not (Test-Path $aitoolsState)) {
        foreach ($root in $roots) {
            if (-not (Test-Path $root)) { continue }
            foreach ($name in $script:UninstallSkillNames) {
                $p = Join-Path $root $name
                if (Test-Path $p -PathType Container) {
                    $isLink = (((Get-Item $p -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
                    if (-not $isLink) { $legacy++ }
                }
            }
        }
    }

    if ($script:Scope -eq "global") { $pluginKeys = Get-PluginKeysGlobal } else { $pluginKeys = Get-PluginKeysProject -Dir $baseDir }

    $kinds = @()
    if ($pluginKeys.Count -gt 0) {
        $kinds += "plugin"
        $script:PriorInstallSummary += "  - Claude Code plugin: $($pluginKeys -join ' ')"
    }
    if ($legacy -gt 0) {
        $kinds += "legacy-skills"
        $script:PriorInstallSummary += "  - $legacy directly-installed skill folder(s) (not managed by databricks aitools)"
    }
    $script:PriorInstallKind = ($kinds -join "+")
}

# If an old-style install is detected for the target scope, recommend a full
# uninstall and (interactively) offer to run it before installing.
function Invoke-PriorInstallCheck {
    Test-PriorInstall
    if ([string]::IsNullOrEmpty($script:PriorInstallKind)) { return }

    $scopeFlag = ""
    if ($script:Scope -eq "global") { $scopeFlag = " -Global" }

    Show-LeftoversBox -Headline "!  PREVIOUS AI DEV KIT INSTALL DETECTED ($($script:Scope) scope)" `
        -Detail "This looks like an older install (skills copied directly and/or the Claude Code plugin) that predates the current 'databricks aitools' flow. Reinstalling over it can leave stale or duplicate skills." `
        -Summary $script:PriorInstallSummary `
        -Action "Recommended: remove it first with  install.ps1 -Uninstall$scopeFlag"

    # Non-interactive / silent: never auto-remove; warn and continue.
    if ($script:Silent -or -not (Test-Interactive)) {
        Write-Warn "Skipping cleanup (non-interactive). Re-run with -Uninstall$scopeFlag to remove the old install."
        return
    }

    $ans = Read-Prompt -PromptText "Remove the previous install now (recommended) before continuing? [Y/n]" -Default "Y"
    if ($ans -match '^(n|no)$') {
        Write-Warn "Leaving the previous install in place - some skills may be stale or duplicated."
        return
    }
    # Full uninstall for THIS scope. Invoke-Uninstall RETURNS (it does not exit), so
    # the install continues afterward on a freshly cleaned slate. Force AssumeYes so
    # it doesn't ask a second time (we already confirmed), then restore it.
    $savedAssumeYes = $script:AssumeYes
    $script:AssumeYes = $true
    try { Invoke-Uninstall } catch { Write-Warn "Cleanup reported an issue - continuing with the install." }
    $script:AssumeYes = $savedAssumeYes
    Write-Ok "Previous install removed - continuing with a fresh install."
}

function Invoke-Main {
    # An explicit --branch hands off to that version's own installer
    Invoke-BranchHandoff

    # --list-skills exits early (uses the live aitools inventory when available)
    if ($script:ListSkills) { Show-SkillsList; return }

    if (-not $script:Silent) {
        Write-Host ""
        Write-Host "Databricks AI Dev Kit Installer" -ForegroundColor White
        Write-Host "--------------------------------"
    }

    # Check dependencies
    Write-Step "Checking prerequisites"
    Test-Dependencies

    # Discover the agent-skills inventory (live via `databricks aitools list`, or fallback)
    Get-AgentBInventory

    # Tool selection
    Write-Step "Selecting tools"
    Invoke-DetectTools
    Write-Ok "Selected: $(($script:Tools -split ' ') -join ', ')"

    # Profile selection
    Write-Step "Databricks profile"
    Invoke-PromptProfile
    Write-Ok "Profile: $($script:Profile_)"

    # Scope selection
    if (-not $script:ScopeExplicit) {
        Invoke-PromptScope
        Write-Ok "Scope: $($script:Scope)"
    }

    # Set state directory based on scope (for profile/manifest storage)
    if ($script:Scope -eq "global") {
        $script:StateDir = $script:InstallDir
    } else {
        $script:StateDir = Join-Path (Get-Location) ".ai-dev-kit"
    }

    # Offer to remove an older, non-aitools install for this scope before we install
    Invoke-PriorInstallCheck

    # Skill profile selection
    if ($script:InstallSkills) {
        Write-Step "Skill profiles"
        Invoke-PromptSkillsProfile
        Resolve-Skills
        Resolve-FetchRefs
        $skCount = $script:SelectedMlflowSkills.Count + $script:SelectedAgentBSkills.Count
        if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
            Write-Ok "Custom selection ($skCount skills)"
        } else {
            $profileDisplay = if ([string]::IsNullOrWhiteSpace($script:SkillsProfile)) { "all" } else { $script:SkillsProfile }
            Write-Ok "Profile: $profileDisplay ($skCount skills)"
        }
    }

    # MCP server opt-in (deprecated), then path if opted in
    Invoke-PromptMcpInstall
    if ($script:InstallMcp) {
        Invoke-PromptMcpPath
        Write-Ok "MCP path: $($script:InstallDir)"
    }

    # Confirmation summary
    if (-not $script:Silent) {
        Write-Host ""
        Write-Host "  Summary" -ForegroundColor White
        Write-Host "  ------------------------------------"
        Write-Host "  Tools:       " -NoNewline; Write-Host "$(($script:Tools -split ' ') -join ', ')" -ForegroundColor Green
        Write-Host "  Profile:     " -NoNewline; Write-Host $script:Profile_ -ForegroundColor Green
        Write-Host "  Scope:       " -NoNewline; Write-Host $script:Scope -ForegroundColor Green
        if ($script:InstallMcp) {
            Write-Host "  MCP server:  " -NoNewline; Write-Host $script:InstallDir -ForegroundColor Green
        }
        if ($script:InstallSkills) {
            $skTotal = $script:SelectedMlflowSkills.Count + $script:SelectedAgentBSkills.Count
            if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
                Write-Host "  Skills:      " -NoNewline
                Write-Host "custom selection ($skTotal skills)" -ForegroundColor Green -NoNewline
                Write-Host " (will be overwritten, backup your changes first)" -ForegroundColor Yellow
            } else {
                $profileDisplay = if ([string]::IsNullOrWhiteSpace($script:SkillsProfile)) { "all" } else { $script:SkillsProfile }
                Write-Host "  Skills:      " -NoNewline
                Write-Host "$profileDisplay ($skTotal skills)" -ForegroundColor Green -NoNewline
                Write-Host " (will be overwritten, backup your changes first)" -ForegroundColor Yellow
            }
            if ($script:SelectedAgentBSkills.Count -gt 0) {
                Write-Host "  Agent skills: " -NoNewline
                Write-Host "via databricks aitools" -ForegroundColor Green -NoNewline
                Write-Host " (requires Databricks CLI v$MinAitoolsCliVersion+)" -ForegroundColor DarkGray
            }
            if (-not $script:InstallExperimental) {
                Write-Host "  Experimental: " -NoNewline
                Write-Host "excluded" -ForegroundColor Yellow -NoNewline
                Write-Host " (--experimental false)" -ForegroundColor DarkGray
            }
        }
        if ($script:InstallMcp) {
            Write-Host "  MCP config:  " -NoNewline; Write-Host "yes" -ForegroundColor Green
        }
        Write-Host ""
    }

    # ── Dry run: report the plan and exit before any changes ──
    if ($script:DryRun) {
        Show-DryRunReport
        exit 0
    }

    if (-not $script:Silent) {
        $confirm = Read-Prompt -PromptText "Proceed with installation? (y/n)" -Default "y"
        if ($confirm -notin @("y", "Y", "yes")) {
            Write-Host ""
            Write-Msg "Installation cancelled."
            return
        }
    }

    # Version check
    Test-Version

    # Determine base directory
    if ($script:Scope -eq "global") {
        $baseDir = $env:USERPROFILE
    } else {
        $baseDir = (Get-Location).Path
    }

    # Setup MCP server (opt-in). The repo is only needed for the MCP server now.
    if ($script:InstallMcp) {
        Install-McpServer
    }

    # Install skills managed by this installer (MLflow)
    if ($script:InstallSkills) {
        Install-Skills -BaseDir $baseDir

        # Install agent skills (delegated to `databricks aitools`)
        Install-AgentBSkills -BaseDir $baseDir

        # Record resolved sources
        Write-Lockfile
    }

    # Write GEMINI.md if gemini is selected
    if ($script:Tools -match 'gemini') {
        if ($script:Scope -eq "global") {
            Write-GeminiMd (Join-Path $env:USERPROFILE "GEMINI.md")
        } else {
            Write-GeminiMd (Join-Path $baseDir "GEMINI.md")
        }
    }

    # Write MCP configs
    if ($script:InstallMcp) {
        Write-McpConfigs -BaseDir $baseDir
    }

    # Save version
    Save-Version

    # Auth prompt
    Invoke-PromptAuth

    # Summary
    Show-Summary
}

Invoke-Main
