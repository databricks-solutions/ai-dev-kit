#
# Databricks AI Dev Kit - Unified Installer (Windows)
#
# Installs skills, MCP server, and configuration for Claude Code, Cursor, OpenAI Codex, and GitHub Copilot.
#
# Usage:
#   irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 | iex
#   .\install.ps1 -Global
#   .\install.ps1 -SkillsOnly
#   .\install.ps1 -McpOnly
#   .\install.ps1 -Tools cursor,codex,copilot
#   .\install.ps1 -Force
#

$ErrorActionPreference = "Stop"

# ─── Configuration ────────────────────────────────────────────
$RepoUrl   = "https://github.com/databricks-solutions/ai-dev-kit.git"
$RawUrl    = "https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main"
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
$script:InstallMcp   = $true
$script:InstallSkills = $true
$script:Force        = $false
$script:Silent       = $false
$script:UserTools    = ""
$script:Tools        = ""
$script:UserMcpPath  = ""
$script:Pkg          = ""
$script:ProfileProvided = $false

# Databricks skills (bundled in repo)
$script:Skills = @(
    "agent-bricks", "aibi-dashboards", "asset-bundles", "databricks-app-apx",
    "databricks-app-python", "databricks-config", "databricks-dbsql", "databricks-docs", "databricks-genie",
    "databricks-jobs", "databricks-python-sdk", "databricks-unity-catalog",
    "lakebase-provisioned", "model-serving", "spark-declarative-pipelines",
    "synthetic-data-generation", "unstructured-pdf-generation"
)

# MLflow skills (fetched from mlflow/skills repo)
$script:MlflowSkills = @(
    "agent-evaluation", "analyze-mlflow-chat-session", "analyze-mlflow-trace",
    "instrumenting-with-mlflow-tracing", "mlflow-onboarding", "querying-mlflow-metrics",
    "retrieving-mlflow-traces", "searching-mlflow-docs"
)
$MlflowRawUrl = "https://raw.githubusercontent.com/mlflow/skills/main"

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
        { $_ -in "-g", "--global", "-Global" }  { $script:Scope = "global"; $i++ }
        { $_ -in "--skills-only", "-SkillsOnly" } { $script:InstallMcp = $false; $i++ }
        { $_ -in "--mcp-only", "-McpOnly" }    { $script:InstallSkills = $false; $i++ }
        { $_ -in "--mcp-path", "-McpPath" }    { $script:UserMcpPath = $args[$i + 1]; $i += 2 }
        { $_ -in "--silent", "-Silent" }       { $script:Silent = $true; $i++ }
        { $_ -in "--tools", "-Tools" }         { $script:UserTools = $args[$i + 1]; $i += 2 }
        { $_ -in "-f", "--force", "-Force" }   { $script:Force = $true; $i++ }
        { $_ -in "-h", "--help", "-Help" } {
            Write-Host "Databricks AI Dev Kit Installer (Windows)"
            Write-Host ""
            Write-Host "Usage: irm .../install.ps1 | iex"
            Write-Host "       .\install.ps1 [OPTIONS]"
            Write-Host ""
            Write-Host "Options:"
            Write-Host "  -p, --profile NAME    Databricks profile (default: DEFAULT)"
            Write-Host "  -g, --global          Install globally for all projects"
            Write-Host "  --skills-only         Skip MCP server setup"
            Write-Host "  --mcp-only            Skip skills installation"
            Write-Host "  --mcp-path PATH       Path to MCP server installation"
            Write-Host "  --silent              Silent mode (no output except errors)"
            Write-Host "  --tools LIST          Comma-separated: claude,cursor,copilot,codex"
            Write-Host "  -f, --force           Force reinstall"
            Write-Host "  -h, --help            Show this help"
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

    $claudeState  = $hasClaude;  $claudeHint  = if ($hasClaude)  { "detected" } else { "not found" }
    $cursorState  = $hasCursor;  $cursorHint  = if ($hasCursor)  { "detected" } else { "not found" }
    $codexState   = $hasCodex;   $codexHint   = if ($hasCodex)   { "detected" } else { "not found" }
    $copilotState = $hasCopilot; $copilotHint = if ($hasCopilot) { "detected" } else { "not found" }

    # If nothing detected, default to claude
    if (-not $hasClaude -and -not $hasCursor -and -not $hasCodex -and -not $hasCopilot) {
        $claudeState = $true
        $claudeHint  = "default"
    }

    if (-not $script:Silent) {
        Write-Host ""
        Write-Host "  Select tools to install for:" -ForegroundColor White
    }

    $items = @(
        @{ Label = "Claude Code";    Value = "claude";  State = $claudeState;  Hint = $claudeHint }
        @{ Label = "Cursor";         Value = "cursor";  State = $cursorState;  Hint = $cursorHint }
        @{ Label = "GitHub Copilot"; Value = "copilot"; State = $copilotState; Hint = $copilotHint }
        @{ Label = "OpenAI Codex";   Value = "codex";   State = $codexState;   Hint = $codexHint }
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
        if (-not $hasDefault -and $items.Count -gt 0) {
            $items[0].Selected = $true
        }

        $script:Profile_ = Select-Radio -Items $items
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

    $localVer = (Get-Content $verFile -Raw).Trim()

    try {
        $remoteVer = (Invoke-WebRequest -Uri "$RawUrl/VERSION" -UseBasicParsing -ErrorAction Stop).Content.Trim()
    } catch {
        return
    }

    if ($remoteVer -and $remoteVer -notmatch '(404|Not Found|error)') {
        if ($localVer -eq $remoteVer) {
            Write-Ok "Already up to date (v$localVer)"
            Write-Msg "Use --force to reinstall"
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
        & git -C $script:RepoDir pull -q 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Remove-Item -Recurse -Force $script:RepoDir -ErrorAction SilentlyContinue
            & git clone -q --depth 1 $RepoUrl $script:RepoDir 2>&1 | Out-Null
        }
    } else {
        if (-not (Test-Path $script:InstallDir)) {
            New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null
        }
        & git clone -q --depth 1 $RepoUrl $script:RepoDir 2>&1 | Out-Null
    }
    if ($LASTEXITCODE -ne 0) {
        $ErrorActionPreference = $prevEAP
        Write-Err "Failed to clone repository"
    }
    Write-Ok "Repository cloned"

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
        }
    }
    $dirs = $dirs | Select-Object -Unique

    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        # Install Databricks skills from repo
        foreach ($skill in $script:Skills) {
            $src = Join-Path $script:RepoDir "databricks-skills\$skill"
            if (-not (Test-Path $src)) { continue }
            $dest = Join-Path $dir $skill
            if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
            Copy-Item -Recurse $src $dest
        }
        $shortDir = $dir -replace [regex]::Escape($env:USERPROFILE), '~'
        Write-Ok "Databricks skills -> $shortDir"

        # Install MLflow skills from mlflow/skills repo
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        foreach ($skill in $script:MlflowSkills) {
            $destDir = Join-Path $dir $skill
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            $url = "$MlflowRawUrl/$skill/SKILL.md"
            try {
                Invoke-WebRequest -Uri $url -OutFile (Join-Path $destDir "SKILL.md") -UseBasicParsing -ErrorAction Stop
                # Try optional reference files
                foreach ($ref in @("reference.md", "examples.md", "api.md")) {
                    try {
                        Invoke-WebRequest -Uri "$MlflowRawUrl/$skill/$ref" -OutFile (Join-Path $destDir $ref) -UseBasicParsing -ErrorAction Stop
                    } catch {}
                }
            } catch {
                Remove-Item -Recurse -Force $destDir -ErrorAction SilentlyContinue
            }
        }
        $ErrorActionPreference = $prevEAP
        Write-Ok "MLflow skills -> $shortDir"
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
                    Write-Warn "Cursor global: configure in Settings > MCP"
                    Write-Msg "  Command: $($script:VenvPython) | Args: $($script:McpEntry)"
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
    Write-Msg "$step. Configure profile $($script:Profile_) or set environment variables DATABRICKS_HOST and DATABRICKS_TOKEN."
    Write-Msg "   Authenticate: databricks auth login --profile $($script:Profile_)"
    $step++
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
    Write-Msg "$step. Open your project in your tool of choice"
    $step++
    Write-Msg "$step. Try: `"List my SQL warehouses`""
    Write-Host ""
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
            Write-Host "  Skills:      " -NoNewline; Write-Host "yes" -ForegroundColor Green
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
        & git clone -q --depth 1 $RepoUrl $script:RepoDir 2>&1 | Out-Null
        $ErrorActionPreference = $prevEAP
        Write-Ok "Repository cloned"
    }

    # Install skills
    if ($script:InstallSkills) {
        Install-Skills -BaseDir $baseDir
    }

    # Write MCP configs
    if ($script:InstallMcp) {
        Write-McpConfigs -BaseDir $baseDir
    }

    # Save version
    Save-Version

    # Summary
    Show-Summary

    # Auth prompt
    Invoke-PromptAuth
}

Invoke-Main
