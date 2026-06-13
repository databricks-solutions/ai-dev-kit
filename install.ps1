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
# Include experimental agent skills in profile/"all" selections (default: true).
# Pass --experimental false (or DEVKIT_EXPERIMENTAL=false) for stable only.
# Explicit --skills requests are always honored as named.
$script:InstallExperimental = ($env:DEVKIT_EXPERIMENTAL -notin @("false", "0"))

# -McpPath / DEVKIT_MCP_PATH implies opting into the MCP server
if ($script:UserMcpPath) { $script:InstallMcp = $true }

# Raw-fetch ref overrides (see Resolve-Ref). SKILLS_CHANNEL=dev flips unset
# refs to `main` for living-at-head testing.
$script:SkillsChannel = if ($env:SKILLS_CHANNEL) { $env:SKILLS_CHANNEL } else { "stable" }
$script:ApxRef = if ($env:APX_REF) { $env:APX_REF } elseif ($script:SkillsChannel -eq "dev") { "main" } else { "latest" }
$script:MlflowRef = if ($env:MLFLOW_REF) { $env:MLFLOW_REF } else { "main" }  # mlflow/skills is tagless -- main is intentional
$script:IncludePrereleases = ($env:INCLUDE_PRERELEASES -in @("true", "1"))

# Databricks skills bundled in this repo (everything else moved to databricks/databricks-agent-skills)
$script:LocalSkills = @("databricks-genie")

# MLflow skills (fetched from mlflow/skills repo; MLFLOW_REF defaults to main -- the repo is tagless)
$script:MlflowSkills = @(
    "agent-evaluation", "analyze-mlflow-chat-session", "analyze-mlflow-trace",
    "instrumenting-with-mlflow-tracing", "mlflow-onboarding", "querying-mlflow-metrics",
    "retrieving-mlflow-traces", "searching-mlflow-docs"
)
$MlflowBaseUrl = "https://raw.githubusercontent.com/mlflow/skills"

# APX skills (fetched from databricks-solutions/apx repo @ latest stable tag, see Resolve-Ref / APX_REF)
$script:ApxSkills = @("databricks-app-apx")
$ApxBaseUrl = "https://raw.githubusercontent.com/databricks-solutions/apx"

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
    "databricks-execution-compute", "databricks-iceberg", "databricks-lakeflow-connect",
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
    "databricks-apps", "databricks-apps-python", "databricks-app-apx", "databricks-lakebase",
    "databricks-model-serving", "databricks-dbsql", "databricks-jobs", "databricks-dabs"
)

# Selected skills (populated during profile selection)
$script:SelectedLocalSkills = @()
$script:SelectedMlflowSkills = @()
$script:SelectedApxSkills = @()
$script:SelectedAgentBSkills = @()

# Resolved raw-fetch refs (populated by Resolve-FetchRefs)
$script:MlflowResolvedRef = ""
$script:ApxResolvedRef = ""

# aitools agent mapping (populated by Resolve-AitoolsAgents)
$script:AitoolsAgents = ""

# ─── --list-skills handler ────────────────────────────────────
# (function -- needs Get-AgentBInventory; invoked from Invoke-Main)

# Number of skills the "all" profile installs (excluded agent skills omitted)
function Get-AllSkillsCount {
    $n = $script:LocalSkills.Count + $script:MlflowSkills.Count + $script:ApxSkills.Count +
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
    Write-Host "Bundled Skills (from this repo)" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:LocalSkills) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "MLflow Skills (from mlflow/skills repo @ $($script:MlflowRef))" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:MlflowSkills) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "APX Skills (from databricks-solutions/apx repo @ $($script:ApxRef))" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:ApxSkills) { Write-Host "    $s" }
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

# ─── Parse arguments ─────────────────────────────────────────
$i = 0
while ($i -lt $args.Count) {
    switch ($args[$i]) {
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
        { $_ -in "-h", "--help", "-Help" } {
            Write-Host "Databricks AI Dev Kit Installer (Windows)"
            Write-Host ""
            Write-Host "Usage: irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 -OutFile install.ps1"
            Write-Host "       .\install.ps1 [OPTIONS]"
            Write-Host ""
            Write-Host "Options:"
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
            Write-Host "  -h, --help            Show this help"
            Write-Host ""
            Write-Host "Environment Variables:"
            Write-Host "  AIDEVKIT_BRANCH       Branch or tag to install (alias: DEVKIT_BRANCH; default: latest release)"
            Write-Host "  AIDEVKIT_HOME         Installation directory (default: ~/.ai-dev-kit)"
            Write-Host "  DEVKIT_INSTALL_MCP    Set to 'true' to install the deprecated MCP server (default: false)"
            Write-Host "  DEVKIT_PROFILE/SCOPE/TOOLS/SKILLS/SKILLS_PROFILE/MCP_PATH/FORCE/SILENT  (mirror the bash installer)"
            Write-Host "  DEVKIT_EXPERIMENTAL   'true' (default) or 'false' to skip experimental agent skills"
            Write-Host "  APX_REF               Ref for APX skill fetch: 'latest' (default), a tag/SHA, or 'main'"
            Write-Host "  MLFLOW_REF            Ref for MLflow skills fetch (default: main)"
            Write-Host "  SKILLS_CHANNEL        'stable' (default) or 'dev' (unset raw-fetch refs follow main)"
            Write-Host "  INCLUDE_PRERELEASES   Set to '1' to allow -rc/-beta tags when resolving 'latest'"
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
        [array]$Items  # Each: @{ Label; Value; State; Hint }
    )

    $count  = $Items.Count
    $cursor = 0
    $states = @()
    foreach ($item in $Items) {
        $states += $item.State
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
                if ($cursor -lt $count) {
                    $states[$cursor] = -not $states[$cursor]
                }
            }
            13 { # Enter
                if ($cursor -lt $count) {
                    $states[$cursor] = -not $states[$cursor]
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

# Bucket one skill name into its source (returns "local"/"mlflow"/"apx"/"agentb", or "" for unknown)
function Get-SkillBucket {
    param([string]$Name)
    if ($script:LocalSkills -contains $Name) { return "local" }
    if ($script:MlflowSkills -contains $Name) { return "mlflow" }
    if ($script:ApxSkills -contains $Name) { return "apx" }
    if (($script:AgentBStable -contains $Name) -or ($script:AgentBExperimental -contains $Name)) { return "agentb" }
    return ""
}

# Resolve selected skills from profile names or explicit skill list,
# bucketing each name into its source (local repo / mlflow / apx / agent-skills).
function Resolve-Skills {
    Get-AgentBInventory

    $localSkills = @()
    $mlflowSkills = @()
    $apxSkills = @()
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
                "local"  { $localSkills += $skill }
                "mlflow" { $mlflowSkills += $skill }
                "apx"    { $apxSkills += $skill }
                "agentb" { $agentBSkills += $skill }
                default  { Write-Err "Unknown skill: '$skill' (run with --list-skills to see available skills)" }
            }
        }
        $script:SelectedLocalSkills  = @($localSkills  | Select-Object -Unique)
        $script:SelectedMlflowSkills = @($mlflowSkills | Select-Object -Unique)
        $script:SelectedApxSkills    = @($apxSkills    | Select-Object -Unique)
        $script:SelectedAgentBSkills = @($agentBSkills | Select-Object -Unique)
        return
    }

    # Priority 2: --skills-profile flag or interactive selection
    if ([string]::IsNullOrWhiteSpace($script:SkillsProfile) -or $script:SkillsProfile -eq "all" -or ($script:SkillsProfile -split ',' | ForEach-Object { $_.Trim() }) -contains "all") {
        $script:SelectedLocalSkills  = @($script:LocalSkills)
        $script:SelectedMlflowSkills = @($script:MlflowSkills)
        $script:SelectedApxSkills    = @($script:ApxSkills)
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
            "local"  { $localSkills += $skill }
            "mlflow" { $mlflowSkills += $skill }
            "apx"    { $apxSkills += $skill }
            "agentb" { $agentBSkills += $skill }
            default  { Write-Warn "Skill '$skill' not found in any source (skipped)" }
        }
    }

    $script:SelectedLocalSkills  = @($localSkills  | Select-Object -Unique)
    $script:SelectedMlflowSkills = @($mlflowSkills | Select-Object -Unique)
    $script:SelectedApxSkills    = @($apxSkills    | Select-Object -Unique)
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

    if ([string]::IsNullOrWhiteSpace($selected)) {
        $script:SkillsProfile = "all"
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
        "databricks-app-apx"                    = @("App APX", "FastAPI + React")
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
    # automatically. Order: agent skills (stable, then experimental), then
    # bundled, MLflow, and APX skills.
    $items = @()
    $seen = @()
    foreach ($skill in ($script:AgentBStable + $script:AgentBExperimental + $script:LocalSkills + $script:MlflowSkills + $script:ApxSkills)) {
        if ($seen -contains $skill) { continue }
        $seen += $skill
        $label = if ($meta.ContainsKey($skill)) { $meta[$skill][0] } else { $skill }
        $hint  = if ($meta.ContainsKey($skill)) { $meta[$skill][1] } else { "" }
        $items += @{ Label = $label; Value = $skill; State = ($preselected -contains $skill); Hint = $hint }
    }

    $selected = Select-Checkbox -Items $items
    $script:UserSkills = ($selected -split ' ') -join ','
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
    $skillsCsv = $script:SelectedAgentBSkills -join ','
    $needsExperimental = Test-AgentBNeedsExperimental
    $count = $script:SelectedAgentBSkills.Count

    if ($script:AitoolsAgents) {
        Write-Msg "Delegating $count agent skills to databricks aitools (agents: $($script:AitoolsAgents))"
        $aitoolsArgs = @("aitools", "install", "--scope", $script:Scope, "--agents", $script:AitoolsAgents, "--skills", $skillsCsv)
        if ($needsExperimental) { $aitoolsArgs += "--experimental" }
        $aitoolsArgs += @("-p", $script:Profile_)
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        if ($script:Silent) {
            & databricks @aitoolsArgs 2>&1 | Out-Null
        } else {
            # Drop aitools' "Skipped <agent>: does not support project-scoped
            # skills" notices -- we deliver to those tools ourselves.
            & databricks @aitoolsArgs 2>&1 |
                Where-Object { "$_" -notmatch 'does not support project-scoped skills' } |
                ForEach-Object { Write-Host "$_" }
        }
        $installOk = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prevEAP
        if (-not $installOk) {
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
        $stageArgs = @("aitools", "install", "--scope", "project", "--agents", "claude-code", "--skills", $SkillsCsv)
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

# ─── Raw-fetch ref resolution (apx, mlflow) ───────────────────

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
    if ($script:SelectedApxSkills.Count -gt 0) {
        $script:ApxResolvedRef = Resolve-Ref -Repo "databricks-solutions/apx" -Requested $script:ApxRef
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
    if ($script:SelectedApxSkills.Count -gt 0) {
        $kind = if ($script:ApxResolvedRef -in @("main", "master")) { "branch" } else { "release_tag" }
        $sha = Get-GitHubSha -Repo "databricks-solutions/apx" -Ref $script:ApxResolvedRef
        $sources["databricks-solutions/apx"] = [ordered]@{
            requested_ref = $script:ApxRef
            resolved_kind = $kind
            resolved_ref  = $script:ApxResolvedRef
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
    $localList  = if ($script:SelectedLocalSkills.Count -gt 0)  { $script:SelectedLocalSkills -join ' ' }  else { "<none>" }
    $mlflowList = if ($script:SelectedMlflowSkills.Count -gt 0) { $script:SelectedMlflowSkills -join ' ' } else { "<none>" }
    $apxList    = if ($script:SelectedApxSkills.Count -gt 0)    { $script:SelectedApxSkills -join ' ' }    else { "<none>" }
    $mlflowRefDisplay = if ($script:MlflowResolvedRef) { $script:MlflowResolvedRef } else { "n/a" }
    $apxRefDisplay    = if ($script:ApxResolvedRef)    { $script:ApxResolvedRef }    else { "n/a" }
    Write-Msg "Bundled skills (this repo):  $localList"
    Write-Msg "MLflow skills @ ${mlflowRefDisplay}: $mlflowList"
    Write-Msg "APX skills @ ${apxRefDisplay}: $apxList"
    if ($script:SelectedAgentBSkills.Count -gt 0) {
        $skillsCsv = $script:SelectedAgentBSkills -join ','
        $expFlag = if (Test-AgentBNeedsExperimental) { " --experimental" } else { "" }
        $releaseSuffix = if ($script:AgentBRelease) { " @ $($script:AgentBRelease)" } else { "" }
        Write-Msg "Agent skills (databricks-agent-skills$releaseSuffix): $($script:SelectedAgentBSkills -join ' ')"
        if ($script:AitoolsAgents) {
            Write-Msg "Would run: databricks aitools install --scope $($script:Scope) --agents $($script:AitoolsAgents) --skills $skillsCsv$expFlag -p $($script:Profile_)"
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
            "cursor" {
                if ($script:Tools -notmatch 'claude') {
                    $dirs += Join-Path $BaseDir ".cursor\skills"
                }
            }
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
    $localCount = $script:SelectedLocalSkills.Count
    $mlflowCount = $script:SelectedMlflowSkills.Count
    $apxCount = $script:SelectedApxSkills.Count
    $totalCount = $localCount + $mlflowCount + $apxCount
    Write-Msg "Installing $totalCount skills (agent skills are installed separately via databricks aitools)"

    # Skills this installer manages directly. Agent skills are deliberately NOT
    # in this set: any same-named entry from an older install is a stale real
    # copy that must be removed -- `databricks aitools` will not overwrite an
    # existing real directory, so leaving it would shadow the new install.
    # (Symlinks for tools aitools can't target are re-created each run.)
    $allNewSkills = @()
    $allNewSkills += $script:SelectedLocalSkills
    $allNewSkills += $script:SelectedMlflowSkills
    $allNewSkills += $script:SelectedApxSkills

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

    # Raw-fetch URLs pinned to the resolved refs
    $mlflowRef = if ($script:MlflowResolvedRef) { $script:MlflowResolvedRef } else { "main" }
    $apxRef = if ($script:ApxResolvedRef) { $script:ApxResolvedRef } else { "main" }
    $mlflowRawUrl = "$MlflowBaseUrl/$mlflowRef"
    $apxRawUrl = "$ApxBaseUrl/$apxRef/skills/apx"

    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        # Install bundled Databricks skills from this repo
        foreach ($skill in $script:SelectedLocalSkills) {
            $src = Join-Path $script:RepoDir "databricks-skills\$skill"
            if (-not (Test-Path $src)) { continue }
            $dest = Join-Path $dir $skill
            if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
            Copy-Item -Recurse $src $dest
            $manifestEntries += "$dir|$skill"
        }
        $shortDir = $dir -replace [regex]::Escape($env:USERPROFILE), '~'
        Write-Ok "Databricks skills ($localCount) -> $shortDir"

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

        # Install APX skills from databricks-solutions/apx repo
        if ($script:SelectedApxSkills.Count -gt 0) {
            $prevEAP2 = $ErrorActionPreference; $ErrorActionPreference = "Continue"
            foreach ($skill in $script:SelectedApxSkills) {
                $destDir = Join-Path $dir $skill
                if (-not (Test-Path $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                $url = "$apxRawUrl/SKILL.md"
                try {
                    Invoke-WebRequest -Uri $url -OutFile (Join-Path $destDir "SKILL.md") -UseBasicParsing -ErrorAction Stop
                    foreach ($ref in @("backend-patterns.md", "frontend-patterns.md")) {
                        try {
                            Invoke-WebRequest -Uri "$apxRawUrl/$ref" -OutFile (Join-Path $destDir $ref) -UseBasicParsing -ErrorAction Stop
                        } catch {}
                    }
                    $manifestEntries += "$dir|$skill"
                } catch {
                    Remove-Item $destDir -ErrorAction SilentlyContinue
                    Write-Warning "Could not install APX skill '$skill' - consider removing $destDir if it is no longer needed"
                }
            }
            $ErrorActionPreference = $prevEAP2
            Write-Ok "APX skills ($apxCount, @ $apxRef) -> $shortDir"
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
- Databricks Apps (Python and APX)
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
    if ($script:Tools -match 'cursor') {
        Write-Msg "$step. Enable MCP in Cursor: Cursor -> Settings -> Cursor Settings -> Tools & MCP -> Toggle 'databricks'"
        $step++
    }
    if ($script:Tools -match 'copilot') {
        Write-Msg "$step. In Copilot Chat, click 'Configure Tools' (tool icon, bottom-right) and enable 'databricks'"
        $step++
        Write-Msg "$step. Use Copilot in Agent mode to access Databricks skills and MCP tools"
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
    if ($script:Tools -match 'windsurf') {
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
    Write-Msg "$step. Try: `"List my SQL warehouses`""
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
function Invoke-Main {
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

    # Skill profile selection
    if ($script:InstallSkills) {
        Write-Step "Skill profiles"
        Invoke-PromptSkillsProfile
        Resolve-Skills
        Resolve-FetchRefs
        $skCount = $script:SelectedLocalSkills.Count + $script:SelectedMlflowSkills.Count + $script:SelectedApxSkills.Count + $script:SelectedAgentBSkills.Count
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
            $skTotal = $script:SelectedLocalSkills.Count + $script:SelectedMlflowSkills.Count + $script:SelectedApxSkills.Count + $script:SelectedAgentBSkills.Count
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
            if ($script:SelectedApxSkills.Count -gt 0 -and $script:ApxResolvedRef) {
                Write-Host "  APX ref:     " -NoNewline; Write-Host $script:ApxResolvedRef -ForegroundColor Green
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

    # Setup MCP server (opt-in). Otherwise clone sources only if needed for bundled skills.
    if ($script:InstallMcp) {
        Install-McpServer
    } elseif ((-not (Test-Path $script:RepoDir)) -and ($script:SelectedLocalSkills.Count -gt 0)) {
        Write-Step "Downloading sources"
        Get-RepoSources
    }

    # Install skills managed by this installer (bundled + mlflow + apx)
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
