#
# Databricks AI Dev Kit - Unified Installer (Windows)
#
# Installs skills, MCP server, and configuration for Claude Code, Cursor, OpenAI Codex, GitHub Copilot, Gemini CLI, and Antigravity.
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

# Determine branch/tag to use
if ($env:AIDEVKIT_BRANCH) {
    $Branch = $env:AIDEVKIT_BRANCH
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
$MinSdkVersion = "0.85.0"

# ─── Defaults ─────────────────────────────────────────────────
$script:Profile_     = "DEFAULT"
$script:Scope        = "project"
$script:ScopeExplicit = $false  # Track if --global was explicitly passed
$script:InstallMcp   = $true
$script:InstallSkills = $true
$script:Force        = $false
$script:Silent       = $false
$script:UserTools    = ""
$script:Tools        = ""
$script:UserMcpPath  = ""
$script:Pkg          = ""
$script:ProfileProvided = $false
$script:SkillsProfile = ""
$script:UserSkills   = ""
$script:ListSkills   = $false

# Databricks skills (bundled in repo)
$script:Skills = @(
    "databricks-agent-bricks", "databricks-aibi-dashboards", "databricks-app-python",
    "databricks-bundles", "databricks-config", "databricks-dbsql", "databricks-docs", "databricks-genie",
    "databricks-iceberg", "databricks-jobs", "databricks-lakebase-autoscale", "databricks-lakebase-provisioned",
    "databricks-metric-views", "databricks-mlflow-evaluation", "databricks-model-serving", "databricks-ai-functions",
    "databricks-python-sdk", "databricks-spark-declarative-pipelines", "databricks-spark-structured-streaming",
    "databricks-synthetic-data-gen", "databricks-unity-catalog", "databricks-unstructured-pdf-generation",
    "databricks-vector-search", "databricks-zerobus-ingest", "spark-python-data-source"
)

# MLflow skills (fetched from mlflow/skills repo)
$script:MlflowSkills = @(
    "agent-evaluation", "analyze-mlflow-chat-session", "analyze-mlflow-trace",
    "instrumenting-with-mlflow-tracing", "mlflow-onboarding", "querying-mlflow-metrics",
    "retrieving-mlflow-traces", "searching-mlflow-docs"
)
$MlflowRawUrl = "https://raw.githubusercontent.com/mlflow/skills/main"

# APX skills (fetched from databricks-solutions/apx repo)
$script:ApxSkills = @("databricks-app-apx")
$ApxRawUrl = "https://raw.githubusercontent.com/databricks-solutions/apx/main/skills/apx"

# ─── Skill profiles ──────────────────────────────────────────
$script:CoreSkills = @("databricks-config", "databricks-docs", "databricks-python-sdk", "databricks-unity-catalog")

$script:ProfileDataEngineer = @(
    "databricks-spark-declarative-pipelines", "databricks-spark-structured-streaming",
    "databricks-jobs", "databricks-bundles", "databricks-dbsql", "databricks-iceberg",
    "databricks-zerobus-ingest", "spark-python-data-source", "databricks-metric-views",
    "databricks-synthetic-data-gen"
)
$script:ProfileAnalyst = @(
    "databricks-aibi-dashboards", "databricks-dbsql", "databricks-genie", "databricks-metric-views"
)
$script:ProfileAiMlEngineer = @(
    "databricks-agent-bricks", "databricks-vector-search", "databricks-model-serving",
    "databricks-genie", "databricks-ai-functions", "databricks-unstructured-pdf-generation",
    "databricks-mlflow-evaluation", "databricks-synthetic-data-gen", "databricks-jobs"
)
$script:ProfileAiMlMlflow = @(
    "agent-evaluation", "analyze-mlflow-chat-session", "analyze-mlflow-trace",
    "instrumenting-with-mlflow-tracing", "mlflow-onboarding", "querying-mlflow-metrics",
    "retrieving-mlflow-traces", "searching-mlflow-docs"
)
$script:ProfileAppDeveloper = @(
    "databricks-app-python", "databricks-app-apx", "databricks-lakebase-autoscale",
    "databricks-lakebase-provisioned", "databricks-model-serving", "databricks-dbsql",
    "databricks-jobs", "databricks-bundles"
)

# Selected skills (populated during profile selection)
$script:SelectedSkills = @()
$script:SelectedMlflowSkills = @()
$script:SelectedApxSkills = @()

# ─── --list-skills handler ────────────────────────────────────
if ($script:ListSkills) {
    Write-Host ""
    Write-Host "Available Skill Profiles" -ForegroundColor White
    Write-Host "--------------------------------"
    Write-Host ""
    Write-Host "  all              " -ForegroundColor White -NoNewline; Write-Host "All 34 skills (default)"
    Write-Host "  data-engineer    " -ForegroundColor White -NoNewline; Write-Host "Pipelines, Spark, Jobs, Streaming (14 skills)"
    Write-Host "  analyst          " -ForegroundColor White -NoNewline; Write-Host "Dashboards, SQL, Genie, Metrics (8 skills)"
    Write-Host "  ai-ml-engineer   " -ForegroundColor White -NoNewline; Write-Host "Agents, RAG, Vector Search, MLflow (17 skills)"
    Write-Host "  app-developer    " -ForegroundColor White -NoNewline; Write-Host "Apps, Lakebase, Deployment (10 skills)"
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
    Write-Host "MLflow Skills (from mlflow/skills repo)" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:MlflowSkills) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "APX Skills (from databricks-solutions/apx repo)" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:ApxSkills) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "Usage: .\install.ps1 --skills-profile data-engineer,ai-ml-engineer" -ForegroundColor DarkGray
    Write-Host "       .\install.ps1 --skills databricks-jobs,databricks-dbsql" -ForegroundColor DarkGray
    Write-Host ""
    return
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
        { $_ -in "--mcp-only", "-McpOnly" }    { $script:InstallSkills = $false; $i++ }
        { $_ -in "--mcp-path", "-McpPath" }    { $script:UserMcpPath = $args[$i + 1]; $i += 2 }
        { $_ -in "--silent", "-Silent" }       { $script:Silent = $true; $i++ }
        { $_ -in "--tools", "-Tools" }         { $script:UserTools = $args[$i + 1]; $i += 2 }
        { $_ -in "--skills-profile", "-SkillsProfile" } { $script:SkillsProfile = $args[$i + 1]; $i += 2 }
        { $_ -in "--skills", "-Skills" }       { $script:UserSkills = $args[$i + 1]; $i += 2 }
        { $_ -in "--list-skills", "-ListSkills" } { $script:ListSkills = $true; $i++ }
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
            Write-Host "  --skills-only         Skip MCP server setup"
            Write-Host "  --mcp-only            Skip skills installation"
            Write-Host "  --mcp-path PATH       Path to MCP server installation"
            Write-Host "  --silent              Silent mode (no output except errors)"
            Write-Host "  --tools LIST          Comma-separated: claude,cursor,copilot,codex,gemini,antigravity"
            Write-Host "  --skills-profile LIST Comma-separated profiles: all,data-engineer,analyst,ai-ml-engineer,app-developer"
            Write-Host "  --skills LIST         Comma-separated skill names to install (overrides profile)"
            Write-Host "  --list-skills         List available skills and profiles, then exit"
            Write-Host "  -f, --force           Force reinstall"
            Write-Host "  -h, --help            Show this help"
            Write-Host ""
            Write-Host "Environment Variables:"
            Write-Host "  AIDEVKIT_BRANCH       Branch or tag to install (default: latest release)"
            Write-Host "  AIDEVKIT_HOME         Installation directory (default: ~/.ai-dev-kit)"
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
            if ($states[$j]) {
                Write-Host $Items[$j].Hint -ForegroundColor Green -NoNewline
            } else {
                Write-Host $Items[$j].Hint -ForegroundColor DarkGray -NoNewline
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
            if ($j -eq $selected) {
                Write-Host $Items[$j].Hint -ForegroundColor Green -NoNewline
            } else {
                Write-Host $Items[$j].Hint -ForegroundColor DarkGray -NoNewline
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

    $claudeState  = $hasClaude;  $claudeHint  = if ($hasClaude)  { "detected" } else { "not found" }
    $cursorState  = $hasCursor;  $cursorHint  = if ($hasCursor)  { "detected" } else { "not found" }
    $codexState   = $hasCodex;   $codexHint   = if ($hasCodex)   { "detected" } else { "not found" }
    $copilotState = $hasCopilot; $copilotHint = if ($hasCopilot) { "detected" } else { "not found" }
    $geminiState  = $hasGemini;  $geminiHint  = if ($hasGemini)  { "detected" } else { "not found" }
    $antigravityState = $hasAntigravity; $antigravityHint = if ($hasAntigravity) { "detected" } else { "not found" }

    # If nothing detected, default to claude
    if (-not $hasClaude -and -not $hasCursor -and -not $hasCodex -and -not $hasCopilot -and -not $hasGemini -and -not $hasAntigravity) {
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

    # Python package manager
    if ($script:InstallMcp) {
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            $script:Pkg = "uv"
        } elseif (Get-Command pip3 -ErrorAction SilentlyContinue) {
            $script:Pkg = "pip3"
        } elseif (Get-Command pip -ErrorAction SilentlyContinue) {
            $script:Pkg = "pip"
        } else {
            Write-Err "Python package manager required. Install Python: choco install python -y"
        }
        Write-Ok $script:Pkg
    }
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

# ─── Setup MCP server ────────────────────────────────────────
function Install-McpServer {
    Write-Step "Setting up MCP server"

    # Native commands (git, pip) write informational messages to stderr.
    # Temporarily relax error handling so these don't terminate the script.
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    # Clone or update repo
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
    Write-Ok "Repository cloned ($Branch)"

    # Create venv and install
    Write-Msg "Installing Python dependencies..."
    if ($script:Pkg -eq "uv") {
        & uv venv --python 3.11 --allow-existing $script:VenvDir -q 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            & uv venv --allow-existing $script:VenvDir -q 2>&1 | Out-Null
        }
        & uv pip install --python $script:VenvPython -e "$($script:RepoDir)\databricks-tools-core" -e "$($script:RepoDir)\databricks-mcp-server" -q 2>&1 | Out-Null
    } else {
        if (-not (Test-Path $script:VenvDir)) {
            & python -m venv $script:VenvDir 2>&1 | Out-Null
        }
        & $script:VenvPython -m pip install -q -e "$($script:RepoDir)\databricks-tools-core" -e "$($script:RepoDir)\databricks-mcp-server" 2>&1 | Out-Null
    }

    # Verify
    & $script:VenvPython -c "import databricks_mcp_server" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $ErrorActionPreference = $prevEAP
        Write-Err "MCP server install failed"
    }

    $ErrorActionPreference = $prevEAP
    Write-Ok "MCP server ready"

    # Check Databricks SDK version
    try {
        $sdkOutput = & $script:VenvPython -c "from databricks.sdk.version import __version__; print(__version__)" 2>&1
        if ($sdkOutput -match '(\d+\.\d+\.\d+)') {
            $sdkVersion = $Matches[1]
            if ([version]$sdkVersion -ge [version]$MinSdkVersion) {
                Write-Ok "Databricks SDK v$sdkVersion"
            } else {
                Write-Warn "Databricks SDK v$sdkVersion is outdated (minimum: v$MinSdkVersion)"
                Write-Msg "  Upgrade: $($script:VenvPython) -m pip install --upgrade databricks-sdk"
            }
        } else {
            Write-Warn "Could not determine Databricks SDK version"
        }
    } catch {
        Write-Warn "Could not determine Databricks SDK version"
    }
}

# ─── Skill profile selection ──────────────────────────────────
function Resolve-Skills {
    # Priority 1: Explicit --skills flag
    if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
        $userList = $script:UserSkills -split ','
        $dbSkills = @() + $script:CoreSkills
        $mlflowSkills = @()
        $apxSkills = @()
        foreach ($skill in $userList) {
            $skill = $skill.Trim()
            if ($script:MlflowSkills -contains $skill) {
                $mlflowSkills += $skill
            } elseif ($script:ApxSkills -contains $skill) {
                $apxSkills += $skill
            } else {
                $dbSkills += $skill
            }
        }
        $script:SelectedSkills = $dbSkills | Select-Object -Unique
        $script:SelectedMlflowSkills = $mlflowSkills | Select-Object -Unique
        $script:SelectedApxSkills = $apxSkills | Select-Object -Unique
        return
    }

    # Priority 2: --skills-profile flag or interactive selection
    if ([string]::IsNullOrWhiteSpace($script:SkillsProfile) -or $script:SkillsProfile -eq "all") {
        $script:SelectedSkills = $script:Skills
        $script:SelectedMlflowSkills = $script:MlflowSkills
        $script:SelectedApxSkills = $script:ApxSkills
        return
    }

    # Build union of selected profiles
    $dbSkills = @() + $script:CoreSkills
    $mlflowSkills = @()
    $apxSkills = @()

    foreach ($profile in ($script:SkillsProfile -split ',')) {
        $profile = $profile.Trim()
        switch ($profile) {
            "all" {
                $script:SelectedSkills = $script:Skills
                $script:SelectedMlflowSkills = $script:MlflowSkills
                $script:SelectedApxSkills = $script:ApxSkills
                return
            }
            "data-engineer"  { $dbSkills += $script:ProfileDataEngineer }
            "analyst"        { $dbSkills += $script:ProfileAnalyst }
            "ai-ml-engineer" {
                $dbSkills += $script:ProfileAiMlEngineer
                $mlflowSkills += $script:ProfileAiMlMlflow
            }
            "app-developer" {
                $dbSkills += $script:ProfileAppDeveloper
                $apxSkills += $script:ApxSkills
            }
            default { Write-Warn "Unknown skill profile: $profile (ignored)" }
        }
    }

    $script:SelectedSkills = $dbSkills | Select-Object -Unique
    $script:SelectedMlflowSkills = $mlflowSkills | Select-Object -Unique
    $script:SelectedApxSkills = $apxSkills | Select-Object -Unique
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
    $pLabels = @("All Skills", "Data Engineer", "Business Analyst", "AI/ML Engineer", "App Developer", "Custom")
    $pValues = @("all", "data-engineer", "analyst", "ai-ml-engineer", "app-developer", "custom")
    $pHints  = @("Install everything (34 skills)", "Pipelines, Spark, Jobs, Streaming (14 skills)", "Dashboards, SQL, Genie, Metrics (8 skills)", "Agents, RAG, Vector Search, MLflow (17 skills)", "Apps, Lakebase, Deployment (10 skills)", "Pick individual skills")
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
                if ($pStates[$j]) {
                    Write-Host $pHints[$j] -ForegroundColor Green -NoNewline
                } else {
                    Write-Host $pHints[$j] -ForegroundColor DarkGray -NoNewline
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
    $preselected = @()
    foreach ($profile in ($PreselectedProfiles -split ' ')) {
        switch ($profile) {
            "data-engineer"  { $preselected += $script:ProfileDataEngineer }
            "analyst"        { $preselected += $script:ProfileAnalyst }
            "ai-ml-engineer" { $preselected += $script:ProfileAiMlEngineer + $script:ProfileAiMlMlflow }
            "app-developer"  { $preselected += $script:ProfileAppDeveloper + $script:ApxSkills }
        }
    }

    Write-Host ""
    Write-Host "  Select individual skills" -ForegroundColor White
    Write-Host "  Core skills (config, docs, python-sdk, unity-catalog) are always installed" -ForegroundColor DarkGray

    $items = @(
        @{ Label = "Spark Pipelines";      Value = "databricks-spark-declarative-pipelines"; State = ($preselected -contains "databricks-spark-declarative-pipelines"); Hint = "SDP/LDP, CDC, SCD Type 2" }
        @{ Label = "Streaming";            Value = "databricks-spark-structured-streaming";  State = ($preselected -contains "databricks-spark-structured-streaming");  Hint = "Real-time streaming" }
        @{ Label = "Jobs & Workflows";     Value = "databricks-jobs";                        State = ($preselected -contains "databricks-jobs");                        Hint = "Multi-task orchestration" }
        @{ Label = "Asset Bundles";        Value = "databricks-bundles";               State = ($preselected -contains "databricks-bundles");               Hint = "DABs deployment" }
        @{ Label = "Databricks SQL";       Value = "databricks-dbsql";                       State = ($preselected -contains "databricks-dbsql");                       Hint = "SQL warehouse queries" }
        @{ Label = "Iceberg";              Value = "databricks-iceberg";                     State = ($preselected -contains "databricks-iceberg");                     Hint = "Apache Iceberg tables" }
        @{ Label = "Zerobus Ingest";       Value = "databricks-zerobus-ingest";              State = ($preselected -contains "databricks-zerobus-ingest");              Hint = "Streaming ingestion" }
        @{ Label = "Python Data Src";      Value = "spark-python-data-source";               State = ($preselected -contains "spark-python-data-source");               Hint = "Custom Spark data sources" }
        @{ Label = "Metric Views";         Value = "databricks-metric-views";                State = ($preselected -contains "databricks-metric-views");                Hint = "Metric definitions" }
        @{ Label = "AI/BI Dashboards";     Value = "databricks-aibi-dashboards";             State = ($preselected -contains "databricks-aibi-dashboards");             Hint = "Dashboard creation" }
        @{ Label = "Genie";                Value = "databricks-genie";                       State = ($preselected -contains "databricks-genie");                       Hint = "Natural language SQL" }
        @{ Label = "Agent Bricks";         Value = "databricks-agent-bricks";                State = ($preselected -contains "databricks-agent-bricks");                Hint = "Build AI agents" }
        @{ Label = "Vector Search";        Value = "databricks-vector-search";               State = ($preselected -contains "databricks-vector-search");               Hint = "Similarity search" }
        @{ Label = "Model Serving";        Value = "databricks-model-serving";               State = ($preselected -contains "databricks-model-serving");               Hint = "Deploy models/agents" }
        @{ Label = "MLflow Evaluation";    Value = "databricks-mlflow-evaluation";           State = ($preselected -contains "databricks-mlflow-evaluation");           Hint = "Model evaluation" }
        @{ Label = "AI Functions";          Value = "databricks-ai-functions";                State = ($preselected -contains "databricks-ai-functions");                Hint = "AI Functions, document parsing & RAG" }
        @{ Label = "Unstructured PDF";     Value = "databricks-unstructured-pdf-generation"; State = ($preselected -contains "databricks-unstructured-pdf-generation"); Hint = "Synthetic PDFs for RAG" }
        @{ Label = "Synthetic Data";       Value = "databricks-synthetic-data-gen";          State = ($preselected -contains "databricks-synthetic-data-gen");          Hint = "Generate test data" }
        @{ Label = "Lakebase Autoscale";   Value = "databricks-lakebase-autoscale";          State = ($preselected -contains "databricks-lakebase-autoscale");          Hint = "Managed PostgreSQL" }
        @{ Label = "Lakebase Provisioned"; Value = "databricks-lakebase-provisioned";        State = ($preselected -contains "databricks-lakebase-provisioned");        Hint = "Provisioned PostgreSQL" }
        @{ Label = "App Python";           Value = "databricks-app-python";                  State = ($preselected -contains "databricks-app-python");                  Hint = "Dash, Streamlit, Flask" }
        @{ Label = "App APX";              Value = "databricks-app-apx";                     State = ($preselected -contains "databricks-app-apx");                     Hint = "FastAPI + React" }
        @{ Label = "MLflow Onboarding";    Value = "mlflow-onboarding";                      State = ($preselected -contains "mlflow-onboarding");                      Hint = "Getting started" }
        @{ Label = "Agent Evaluation";     Value = "agent-evaluation";                       State = ($preselected -contains "agent-evaluation");                       Hint = "Evaluate AI agents" }
        @{ Label = "MLflow Tracing";       Value = "instrumenting-with-mlflow-tracing";      State = ($preselected -contains "instrumenting-with-mlflow-tracing");      Hint = "Instrument with tracing" }
        @{ Label = "Analyze Traces";       Value = "analyze-mlflow-trace";                   State = ($preselected -contains "analyze-mlflow-trace");                   Hint = "Analyze trace data" }
        @{ Label = "Retrieve Traces";      Value = "retrieving-mlflow-traces";               State = ($preselected -contains "retrieving-mlflow-traces");               Hint = "Search & retrieve traces" }
        @{ Label = "Analyze Chat";         Value = "analyze-mlflow-chat-session";            State = ($preselected -contains "analyze-mlflow-chat-session");            Hint = "Chat session analysis" }
        @{ Label = "Query Metrics";        Value = "querying-mlflow-metrics";                State = ($preselected -contains "querying-mlflow-metrics");                Hint = "MLflow metrics queries" }
        @{ Label = "Search MLflow Docs";   Value = "searching-mlflow-docs";                  State = ($preselected -contains "searching-mlflow-docs");                  Hint = "MLflow documentation" }
    )

    $selected = Select-Checkbox -Items $items
    $script:UserSkills = ($selected -split ' ') -join ','
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
        }
    }
    $dirs = $dirs | Select-Object -Unique

    # Count selected skills for display
    $dbCount = $script:SelectedSkills.Count
    $mlflowCount = $script:SelectedMlflowSkills.Count
    $apxCount = $script:SelectedApxSkills.Count
    $totalCount = $dbCount + $mlflowCount + $apxCount
    Write-Msg "Installing $totalCount skills"

    # Build set of all skills being installed now
    $allNewSkills = @()
    $allNewSkills += $script:SelectedSkills
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
            # Only remove if the directory exists
            $prevPath = Join-Path $prevDir $prevSkill
            if (Test-Path $prevPath) {
                Remove-Item -Recurse -Force $prevPath
                Write-Msg "Removed deselected skill: $prevSkill"
            }
        }
    }

    # Start fresh manifest
    $manifestEntries = @()

    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        # Install Databricks skills from repo
        foreach ($skill in $script:SelectedSkills) {
            $src = Join-Path $script:RepoDir "databricks-skills\$skill"
            if (-not (Test-Path $src)) { continue }
            $dest = Join-Path $dir $skill
            if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
            Copy-Item -Recurse $src $dest
            $manifestEntries += "$dir|$skill"
        }
        $shortDir = $dir -replace [regex]::Escape($env:USERPROFILE), '~'
        Write-Ok "Databricks skills ($dbCount) -> $shortDir"

        # Install MLflow skills from mlflow/skills repo
        if ($script:SelectedMlflowSkills.Count -gt 0) {
            $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
            foreach ($skill in $script:SelectedMlflowSkills) {
                $destDir = Join-Path $dir $skill
                if (-not (Test-Path $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                $url = "$MlflowRawUrl/$skill/SKILL.md"
                try {
                    Invoke-WebRequest -Uri $url -OutFile (Join-Path $destDir "SKILL.md") -UseBasicParsing -ErrorAction Stop
                    foreach ($ref in @("reference.md", "examples.md", "api.md")) {
                        try {
                            Invoke-WebRequest -Uri "$MlflowRawUrl/$skill/$ref" -OutFile (Join-Path $destDir $ref) -UseBasicParsing -ErrorAction Stop
                        } catch {}
                    }
                    $manifestEntries += "$dir|$skill"
                } catch {
                    Remove-Item -Recurse -Force $destDir -ErrorAction SilentlyContinue
                }
            }
            $ErrorActionPreference = $prevEAP
            Write-Ok "MLflow skills ($mlflowCount) -> $shortDir"
        }

        # Install APX skills from databricks-solutions/apx repo
        if ($script:SelectedApxSkills.Count -gt 0) {
            $prevEAP2 = $ErrorActionPreference; $ErrorActionPreference = "Continue"
            foreach ($skill in $script:SelectedApxSkills) {
                $destDir = Join-Path $dir $skill
                if (-not (Test-Path $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                $url = "$ApxRawUrl/SKILL.md"
                try {
                    Invoke-WebRequest -Uri $url -OutFile (Join-Path $destDir "SKILL.md") -UseBasicParsing -ErrorAction Stop
                    foreach ($ref in @("backend-patterns.md", "frontend-patterns.md")) {
                        try {
                            Invoke-WebRequest -Uri "$ApxRawUrl/$ref" -OutFile (Join-Path $destDir $ref) -UseBasicParsing -ErrorAction Stop
                        } catch {}
                    }
                    $manifestEntries += "$dir|$skill"
                } catch {
                    Remove-Item $destDir -ErrorAction SilentlyContinue
                    Write-Warning "Could not install APX skill '$skill' - consider removing $destDir if it is no longer needed"
                }
            }
            $ErrorActionPreference = $prevEAP2
            Write-Ok "APX skills ($apxCount) -> $shortDir"
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
function Write-McpJson {
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
    if ((Test-Path $Path) -and (Test-Path $script:VenvPython)) {
        try {
            $existing = Get-Content $Path -Raw | ConvertFrom-Json
        } catch {
            $existing = $null
        }
    }

    if ($existing) {
        # Merge into existing config — use forward slashes for JSON compatibility
        if (-not $existing.mcpServers) {
            $existing | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{}) -Force
        }
        $dbEntry = [PSCustomObject]@{
            command = $script:VenvPython -replace '\\', '/'
            args    = @($script:McpEntry -replace '\\', '/')
            env     = [PSCustomObject]@{ DATABRICKS_CONFIG_PROFILE = $script:Profile_ }
        }
        $existing.mcpServers | Add-Member -NotePropertyName "databricks" -NotePropertyValue $dbEntry -Force
        $existing | ConvertTo-Json -Depth 10 | Set-Content $Path -Encoding UTF8
    } else {
        # Write fresh config — use forward slashes for cross-platform JSON compatibility
        $pythonPath = $script:VenvPython -replace '\\', '/'
        $entryPath  = $script:McpEntry -replace '\\', '/'
        $json = @"
{
  "mcpServers": {
    "databricks": {
      "command": "$pythonPath",
      "args": ["$entryPath"],
      "env": {"DATABRICKS_CONFIG_PROFILE": "$($script:Profile_)"}
    }
  }
}
"@
        Set-Content -Path $Path -Value $json -Encoding UTF8
    }
}

function Write-CopilotMcpJson {
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
    if ((Test-Path $Path) -and (Test-Path $script:VenvPython)) {
        try {
            $existing = Get-Content $Path -Raw | ConvertFrom-Json
        } catch {
            $existing = $null
        }
    }

    if ($existing) {
        if (-not $existing.servers) {
            $existing | Add-Member -NotePropertyName "servers" -NotePropertyValue ([PSCustomObject]@{}) -Force
        }
        $dbEntry = [PSCustomObject]@{
            command = $script:VenvPython -replace '\\', '/'
            args    = @($script:McpEntry -replace '\\', '/')
            env     = [PSCustomObject]@{ DATABRICKS_CONFIG_PROFILE = $script:Profile_ }
        }
        $existing.servers | Add-Member -NotePropertyName "databricks" -NotePropertyValue $dbEntry -Force
        $existing | ConvertTo-Json -Depth 10 | Set-Content $Path -Encoding UTF8
    } else {
        $pythonPath = $script:VenvPython -replace '\\', '/'
        $entryPath  = $script:McpEntry -replace '\\', '/'
        $json = @"
{
  "servers": {
    "databricks": {
      "command": "$pythonPath",
      "args": ["$entryPath"],
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

function Write-GeminiMcpJson {
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
    if ((Test-Path $Path) -and (Test-Path $script:VenvPython)) {
        try {
            $existing = Get-Content $Path -Raw | ConvertFrom-Json
        } catch {
            $existing = $null
        }
    }

    if ($existing) {
        if (-not $existing.mcpServers) {
            $existing | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{}) -Force
        }
        $dbEntry = [PSCustomObject]@{
            command = $script:VenvPython -replace '\\', '/'
            args    = @($script:McpEntry -replace '\\', '/')
            env     = [PSCustomObject]@{ DATABRICKS_CONFIG_PROFILE = $script:Profile_ }
        }
        $existing.mcpServers | Add-Member -NotePropertyName "databricks" -NotePropertyValue $dbEntry -Force
        $existing | ConvertTo-Json -Depth 10 | Set-Content $Path -Encoding UTF8
    } else {
        $pythonPath = $script:VenvPython -replace '\\', '/'
        $entryPath  = $script:McpEntry -replace '\\', '/'
        $json = @"
{
  "mcpServers": {
    "databricks": {
      "command": "$pythonPath",
      "args": ["$entryPath"],
      "env": {"DATABRICKS_CONFIG_PROFILE": "$($script:Profile_)"}
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

function Write-McpConfigs {
    param([string]$BaseDir)

    Write-Step "Configuring MCP"

    foreach ($tool in ($script:Tools -split ' ')) {
        switch ($tool) {
            "claude" {
                if ($script:Scope -eq "global") {
                    Write-McpJson (Join-Path $env:USERPROFILE ".claude\mcp.json")
                } else {
                    Write-McpJson (Join-Path $BaseDir ".mcp.json")
                }
                Write-Ok "Claude MCP config"
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
                    Write-Msg "           `"env`": {`"DATABRICKS_CONFIG_PROFILE`": `"$($script:Profile)`"}"
                    Write-Msg "         }"
                    Write-Msg "       }"
                    Write-Msg "     }"
                } else {
                    Write-McpJson (Join-Path $BaseDir ".cursor\mcp.json")
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
                    Write-CopilotMcpJson (Join-Path $BaseDir ".vscode\mcp.json")
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
                    Write-GeminiMcpJson (Join-Path $env:USERPROFILE ".gemini\settings.json")
                } else {
                    Write-GeminiMcpJson (Join-Path $BaseDir ".gemini\settings.json")
                }
                Write-Ok "Gemini CLI MCP config"
            }
            "antigravity" {
                if ($script:Scope -eq "project") {
                    Write-Warn "Antigravity only supports global MCP configuration."
                    Write-Msg "  Config written to ~/.gemini/antigravity/mcp_config.json"
                }
                Write-GeminiMcpJson (Join-Path $env:USERPROFILE ".gemini\antigravity\mcp_config.json")
                Write-Ok "Antigravity MCP config"
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
    
    $labels = @("Project", "Global")
    $values = @("project", "global")
    $hints = @("Install in current directory (.cursor/, .claude/, .gemini/)", "Install in home directory (~/.cursor/, ~/.claude/, ~/.gemini/)")
    $count = 2
    $selected = 0
    $cursor = 0
    
    $isInteractive = Test-Interactive
    
    if (-not $isInteractive) {
        # Fallback: numbered list
        Write-Host ""
        Write-Host "  1. (*) Project  Install in current directory (.cursor/, .claude/, .gemini/)"
        Write-Host "  2. ( ) Global   Install in home directory (~/.cursor/, ~/.claude/, ~/.gemini/)"
        Write-Host ""
        Write-Host "  Enter number to select (or press Enter for default): " -NoNewline
        $input_ = Read-Host
        if (-not [string]::IsNullOrWhiteSpace($input_) -and $input_ -eq "2") {
            $selected = 1
        }
        $script:Scope = $values[$selected]
        return
    }
    
    # Interactive mode
    Write-Host ""
    Write-Host "  Up/Down navigate, Enter select" -ForegroundColor DarkGray
    Write-Host ""
    
    $totalRows = $count
    
    try { [Console]::CursorVisible = $false } catch {}
    
    $drawScope = {
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
            $padLabel = $labels[$j].PadRight(20)
            Write-Host " $padLabel " -NoNewline
            if ($j -eq $selected) {
                Write-Host $hints[$j] -ForegroundColor Green -NoNewline
            } else {
                Write-Host $hints[$j] -ForegroundColor DarkGray -NoNewline
            }
            $pos = [Console]::CursorLeft
            $remaining = [Console]::WindowWidth - $pos - 1
            if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
            Write-Host ""
        }
    }
    
    # Reserve lines
    for ($j = 0; $j -lt $totalRows; $j++) { Write-Host "" }
    & $drawScope
    
    while ($true) {
        $key = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        
        switch ($key.VirtualKeyCode) {
            38 { if ($cursor -gt 0) { $cursor-- } }
            40 { if ($cursor -lt 1) { $cursor++ } }
            32 { $selected = $cursor }
            13 {
                $selected = $cursor
                & $drawScope
                break
            }
        }
        if ($key.VirtualKeyCode -eq 13) { break }
        
        & $drawScope
    }
    
    try { [Console]::CursorVisible = $true } catch {}
    
    $script:Scope = $values[$selected]
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
    if (-not $script:Silent) {
        Write-Host ""
        Write-Host "Databricks AI Dev Kit Installer" -ForegroundColor White
        Write-Host "--------------------------------"
    }

    # Check dependencies
    Write-Step "Checking prerequisites"
    Test-Dependencies

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
        $skCount = $script:SelectedSkills.Count + $script:SelectedMlflowSkills.Count + $script:SelectedApxSkills.Count
        if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
            Write-Ok "Custom selection ($skCount skills)"
        } else {
            $profileDisplay = if ([string]::IsNullOrWhiteSpace($script:SkillsProfile)) { "all" } else { $script:SkillsProfile }
            Write-Ok "Profile: $profileDisplay ($skCount skills)"
        }
    }

    # MCP path
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
            $skTotal = $script:SelectedSkills.Count + $script:SelectedMlflowSkills.Count + $script:SelectedApxSkills.Count
            if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
                Write-Host "  Skills:      " -NoNewline; Write-Host "custom selection ($skTotal skills)" -ForegroundColor Green
            } else {
                $profileDisplay = if ([string]::IsNullOrWhiteSpace($script:SkillsProfile)) { "all" } else { $script:SkillsProfile }
                Write-Host "  Skills:      " -NoNewline; Write-Host "$profileDisplay ($skTotal skills)" -ForegroundColor Green
            }
        }
        if ($script:InstallMcp) {
            Write-Host "  MCP config:  " -NoNewline; Write-Host "yes" -ForegroundColor Green
        }
        Write-Host ""
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

    # Setup MCP server
    if ($script:InstallMcp) {
        Install-McpServer
    } elseif (-not (Test-Path $script:RepoDir)) {
        Write-Step "Downloading sources"
        if (-not (Test-Path $script:InstallDir)) {
            New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null
        }
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & git -c advice.detachedHead=false clone -q --depth 1 --branch $Branch $RepoUrl $script:RepoDir 2>&1 | Out-Null
        $ErrorActionPreference = $prevEAP
        Write-Ok "Repository cloned ($Branch)"
    }

    # Install skills
    if ($script:InstallSkills) {
        Install-Skills -BaseDir $baseDir
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
