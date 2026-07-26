#
# Databricks MCP Server - Client Registration Installer (Windows)
#
# Builds the MCP server runtime (by delegating to setup.ps1) and registers the
# `databricks` MCP server with your AI coding tools: Claude Code, Cursor,
# GitHub Copilot, OpenAI Codex, Gemini CLI, Antigravity, Windsurf, OpenCode, and Kiro.
#
# The venv build is owned by databricks-mcp-server/setup.ps1 — this script never
# duplicates that logic; it calls setup.ps1 and then writes the editor config
# files that point at the resulting venv.
#
# Usage:
#   .\databricks-mcp-server\mcp_install.ps1 [OPTIONS]
#
# Options:
#   -Profile NAME     Databricks config profile to inject (default: DEFAULT)
#   -Global           Register globally (home dir) instead of per-project
#   -Tools LIST       Comma-separated: claude,cursor,copilot,codex,gemini,antigravity,windsurf,opencode,kiro
#   -VenvDir DIR      Virtual environment location (default: <this dir>\.venv)
#   -SkipVenv         Skip the setup.ps1 venv build (assume it already exists)
#   -Silent           Silent mode (no output except errors)
#   -Uninstall        Remove only the 'databricks' MCP entry from each client config
#   -DryRun           Print the plan (install or uninstall) and exit without changes
#   -Yes              With -Uninstall: skip the confirmation prompt
#   -Help             Show this help
#
# Environment Variables (alternative to flags):
#   DEVKIT_PROFILE    Databricks config profile
#   DEVKIT_SCOPE      'project' or 'global'
#   DEVKIT_TOOLS      Comma-separated list of tools
#   DEVKIT_SILENT     Set to 'true' for silent mode
#

param(
    [string]$Profile_ = "",
    [switch]$Global,
    [string]$Tools = "",
    [string]$VenvDir = "",
    [switch]$SkipVenv,
    [switch]$Silent,
    [switch]$Uninstall,
    [switch]$DryRun,
    [switch]$Yes,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# ─── Paths (derived from this script's own location) ────────────
# The repo is already cloned when this standalone installer runs, so — unlike the
# unified installer's clone-to-~\.ai-dev-kit flow — paths derive from here, the
# same way setup.ps1 does.
$script:ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:McpEntry  = Join-Path $script:ScriptDir "run_server.py"

# ─── Defaults (env vars mirror the bash installer) ──────────────
if ($Profile_)       { $script:Profile_ = $Profile_ }
elseif ($env:DEVKIT_PROFILE) { $script:Profile_ = $env:DEVKIT_PROFILE }
else                 { $script:Profile_ = "DEFAULT" }

if ($Global)         { $script:Scope = "global"; $script:ScopeExplicit = $true }
elseif ($env:DEVKIT_SCOPE) { $script:Scope = $env:DEVKIT_SCOPE; $script:ScopeExplicit = $true }
else                 { $script:Scope = "project"; $script:ScopeExplicit = $false }

if ($Silent)         { $script:Silent = $true }
elseif ($env:DEVKIT_SILENT -in @("true", "1")) { $script:Silent = $true }
else                 { $script:Silent = $false }

if ($Tools)          { $script:UserTools = $Tools }
elseif ($env:DEVKIT_TOOLS) { $script:UserTools = $env:DEVKIT_TOOLS }
else                 { $script:UserTools = "" }
$script:Tools = ""

if ($VenvDir)        { $script:VenvDir = $VenvDir }
else                 { $script:VenvDir = Join-Path $script:ScriptDir ".venv" }

$script:SkipVenv   = [bool]$SkipVenv
$script:Uninstall  = [bool]$Uninstall
$script:DryRun     = [bool]$DryRun
$script:AssumeYes  = [bool]$Yes

$script:VenvPython = Join-Path $script:VenvDir "Scripts\python.exe"

# ─── Help ───────────────────────────────────────────────────────
if ($Help) {
    Write-Host "Databricks MCP Server - Client Registration Installer (Windows)"
    Write-Host ""
    Write-Host "Usage: .\databricks-mcp-server\mcp_install.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Profile NAME     Databricks config profile to inject (default: DEFAULT)"
    Write-Host "  -Global           Register globally (home dir) instead of per-project"
    Write-Host "  -Tools LIST       Comma-separated: claude,cursor,copilot,codex,gemini,antigravity,windsurf,opencode,kiro"
    Write-Host "  -VenvDir DIR      Virtual environment location (default: <this dir>\.venv)"
    Write-Host "  -SkipVenv         Skip the setup.ps1 venv build (assume it already exists)"
    Write-Host "  -Silent           Silent mode (no output except errors)"
    Write-Host "  -Uninstall        Remove only the 'databricks' MCP entry from each client config"
    Write-Host "  -DryRun           Print the plan (install or uninstall) and exit without changes"
    Write-Host "  -Yes              With -Uninstall: skip the confirmation prompt"
    Write-Host "  -Help             Show this help"
    Write-Host ""
    Write-Host "Environment Variables (alternative to flags):"
    Write-Host "  DEVKIT_PROFILE    Databricks config profile"
    Write-Host "  DEVKIT_SCOPE      'project' or 'global'"
    Write-Host "  DEVKIT_TOOLS      Comma-separated list of tools"
    Write-Host "  DEVKIT_SILENT     Set to 'true' for silent mode"
    Write-Host ""
    Write-Host "The venv build is delegated to databricks-mcp-server/setup.ps1."
    Write-Host ""
    exit 0
}

# ─── Output helpers ─────────────────────────────────────────────
function Write-Msg  { param([string]$Text) if (-not $script:Silent) { Write-Host "  $Text" } }
function Write-Ok   { param([string]$Text) if (-not $script:Silent) { Write-Host "  " -NoNewline; Write-Host "✓" -ForegroundColor Green -NoNewline; Write-Host " $Text" } }
function Write-Warn { param([string]$Text) if (-not $script:Silent) { Write-Host "  " -NoNewline; Write-Host "!" -ForegroundColor Yellow -NoNewline; Write-Host " $Text" } }
function Write-Die  { param([string]$Text) Write-Host "  " -NoNewline; Write-Host "✗" -ForegroundColor Red -NoNewline; Write-Host " $Text"; exit 1 }
function Write-Step { param([string]$Text) if (-not $script:Silent) { Write-Host ""; Write-Host $Text -ForegroundColor White } }

# ─── Interactive helpers ────────────────────────────────────────
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

    if (Test-Interactive) {
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
            for ($j = 0; $j -lt $count; $j++) { $states[$j] = $false }
            $nums = $input_ -split ',' | ForEach-Object { $_.Trim() }
            foreach ($n in $nums) {
                $idx = [int]$n - 1
                if ($idx -ge 0 -and $idx -lt $count) { $states[$idx] = $true }
            }
        }
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

    try { [Console]::CursorVisible = $false } catch {}

    $drawCheckbox = {
        [Console]::SetCursorPosition(0, [Math]::Max(0, [Console]::CursorTop - $totalRows))
        for ($j = 0; $j -lt $count; $j++) {
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
            $hint = $Items[$j].Hint
            $avail = [Console]::WindowWidth - [Console]::CursorLeft - 1
            if ($avail -lt 0) { $avail = 0 }
            if ($hint.Length -gt $avail) { $hint = $hint.Substring(0, $avail) }
            if ($states[$j]) {
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

    for ($j = 0; $j -lt $totalRows; $j++) { Write-Host "" }
    & $drawCheckbox

    while ($true) {
        $key = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

        switch ($key.VirtualKeyCode) {
            38 { if ($cursor -gt 0) { $cursor-- } }          # Up
            40 { if ($cursor -lt $count) { $cursor++ } }     # Down
            32 { # Space
                if ($cursor -lt $count -and -not $locked[$cursor]) {
                    $states[$cursor] = -not $states[$cursor]
                }
            }
            13 { # Enter
                if ($cursor -lt $count) {
                    if (-not $locked[$cursor]) { $states[$cursor] = -not $states[$cursor] }
                } else {
                    & $drawCheckbox
                    break
                }
            }
        }
        if ($key.VirtualKeyCode -eq 13 -and $cursor -eq $count) { break }

        & $drawCheckbox
    }

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

    Write-Host ""
    Write-Host "  Up/Down navigate, Enter confirm" -ForegroundColor DarkGray
    Write-Host ""

    $totalRows = $count + 2

    try { [Console]::CursorVisible = $false } catch {}

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

    for ($j = 0; $j -lt $totalRows; $j++) { Write-Host "" }
    & $drawRadio

    while ($true) {
        $key = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

        switch ($key.VirtualKeyCode) {
            38 { if ($cursor -gt 0) { $cursor-- } }
            40 { if ($cursor -lt $count) { $cursor++ } }
            32 { if ($cursor -lt $count) { $selected = $cursor } }
            13 {
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

# ─── Tool detection & selection ─────────────────────────────────
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
        Write-Host "  Select tools to register the databricks MCP server for:" -ForegroundColor White
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
    # If provided via -Profile flag (non-default), skip prompt
    if ($script:Profile_ -ne "DEFAULT") { return }
    if ($script:Silent) { return }
    if (-not (Test-Interactive)) { return }

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

        $items += @{ Label = "Custom profile name..."; Value = "__CUSTOM__"; Selected = $false; Hint = "Enter a custom profile name" }

        if (-not $hasDefault -and $items.Count -gt 1) {
            $items[0].Selected = $true
        }

        $selectedProfile = Select-Radio -Items $items

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

# ─── Scope selection ────────────────────────────────────────────
function Invoke-PromptScope {
    param([string]$Title = "Select registration scope")

    if ($script:Silent) { return }
    if (-not (Test-Interactive)) { return }

    Write-Host ""
    Write-Host "  $Title" -ForegroundColor White

    $items = @(
        @{ Label = "Project"; Value = "project"; Selected = $true;  Hint = "Current directory (.mcp.json, etc.)" }
        @{ Label = "Global";  Value = "global";  Selected = $false; Hint = "Home directory (~/.claude.json, etc.)" }
    )
    $script:Scope = Select-Radio -Items $items
}

# ─── MCP config writers ────────────────────────────────────────
# Write/merge an MCP server entry into a JSON config.
#   -Path     target config file
#   -RootKey  top-level key: "mcpServers" (Claude/Cursor/Gemini/Windsurf/Kiro)
#             or "servers" (Copilot)
#   -Defer    include Claude's defer_loading hint
# Merging is decoupled from whether the venv exists yet, so an existing config
# is never clobbered. The original is backed up to <file>.bak first.
function Write-McpJsonConfig {
    param([string]$Path, [string]$RootKey, [bool]$Defer)

    # No-clobber parity with the bash installer: only merge into an existing
    # config when the venv python is present. Without it the server can't run, so
    # refuse to modify a file that may hold other settings and tell the user to
    # add the entry manually. A brand-new file is always safe to write.
    if ((Test-Path $Path) -and -not (Test-Path $script:VenvPython)) {
        Write-Warn "Cannot merge MCP config into $Path without the venv python at $($script:VenvPython). Add manually."
        return
    }

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    if (Test-Path $Path) {
        Copy-Item $Path "$Path.bak" -Force
        Write-Msg "Backed up $(Split-Path $Path -Leaf) -> $(Split-Path $Path -Leaf).bak"
    }

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

# Write/merge the Codex TOML config. Unlike the historical unified installer,
# this includes the profile env block ([mcp_servers.databricks.env]) so Codex
# picks up the same DATABRICKS_CONFIG_PROFILE as every other client.
function Write-McpToml {
    param([string]$Path)

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    if (Test-Path $Path) {
        $content = Get-Content $Path -Raw
        # Anchor to the table header so a match in a comment/value can't be
        # mistaken for an existing registration (matches the removal loop's anchor).
        if ($content -match '(?m)^\[mcp_servers\.databricks') { return }
        Copy-Item $Path "$Path.bak" -Force
        Write-Msg "Backed up $(Split-Path $Path -Leaf) -> $(Split-Path $Path -Leaf).bak"
    }

    $pythonPath = $script:VenvPython -replace '\\', '/'
    $entryPath  = $script:McpEntry -replace '\\', '/'
    $tomlBlock = @"

[mcp_servers.databricks]
command = "$pythonPath"
args = ["$entryPath"]

[mcp_servers.databricks.env]
DATABRICKS_CONFIG_PROFILE = "$($script:Profile_)"
"@
    Add-Content -Path $Path -Value $tomlBlock -Encoding UTF8
}

# Write/merge the OpenCode config (root key 'mcp', type 'local', command-as-array).
function Write-OpenCodeJson {
    param([string]$Path)

    # No-clobber parity with the bash installer (see Write-McpJsonConfig).
    if ((Test-Path $Path) -and -not (Test-Path $script:VenvPython)) {
        Write-Warn "Cannot merge MCP config into $Path without the venv python at $($script:VenvPython). Add manually."
        return
    }

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    if (Test-Path $Path) {
        Copy-Item $Path "$Path.bak" -Force
        Write-Msg "Backed up $(Split-Path $Path -Leaf) -> $(Split-Path $Path -Leaf).bak"
    }

    $existing = $null
    if (Test-Path $Path) {
        try { $existing = Get-Content $Path -Raw | ConvertFrom-Json } catch { $existing = $null }
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

function Write-McpConfigs {
    param([string]$BaseDir)

    Write-Step "Registering the databricks MCP server"

    foreach ($tool in ($script:Tools -split ' ')) {
        switch ($tool) {
            "claude" {
                if ($script:Scope -eq "global") {
                    Write-McpJsonConfig (Join-Path $env:USERPROFILE ".claude.json") "mcpServers" $true
                } else {
                    Write-McpJsonConfig (Join-Path $BaseDir ".mcp.json") "mcpServers" $true
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
            default {
                Write-Warn "Unknown tool '$tool' — skipping"
            }
        }
    }
}

# ─── Uninstall (deregistration) ────────────────────────────────
# Read-only: true only if the EXACT top-level server key ($Top) contains a
# 'databricks' entry — the same thing removal targets.
function Test-McpJsonHasDatabricks {
    param([string]$Path, [string]$Top)
    if (-not (Test-Path $Path)) { return $false }
    try { $cfg = Get-Content $Path -Raw | ConvertFrom-Json } catch { return $false }
    return ($cfg.$Top -and $cfg.$Top.PSObject.Properties.Name -contains 'databricks')
}

# Remove the 'databricks' MCP server entry from a JSON config, preserving all
# other servers and settings. $Top is the top-level key ('mcpServers'/'servers'/'mcp').
function Remove-McpJsonKey {
    param([string]$Path, [string]$Top)
    if (-not (Test-Path $Path)) { return $false }
    if (-not (Select-String -Path $Path -Pattern '"databricks"' -Quiet)) { return $false }
    if ($script:DryRun) { return $true }
    try { $cfg = Get-Content $Path -Raw | ConvertFrom-Json } catch { return $false }
    if (-not ($cfg.$Top -and $cfg.$Top.PSObject.Properties.Name -contains 'databricks')) {
        return $false
    }
    Copy-Item $Path "$Path.bak" -Force
    $cfg.$Top.PSObject.Properties.Remove('databricks')
    if (-not $cfg.$Top.PSObject.Properties.Name) { $cfg.PSObject.Properties.Remove($Top) }
    $cfg | ConvertTo-Json -Depth 100 | Set-Content $Path -Encoding UTF8
    return $true
}

# Remove the [mcp_servers.databricks] block (and its dotted subtables, e.g.
# [mcp_servers.databricks.env]) from a Codex TOML config.
function Remove-McpTomlBlock {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    if (-not (Select-String -Path $Path -Pattern '^\[mcp_servers\.databricks' -Quiet)) { return $false }
    if ($script:DryRun) { return $true }
    Copy-Item $Path "$Path.bak" -Force
    $out = New-Object System.Collections.Generic.List[string]
    $skip = $false
    foreach ($line in Get-Content "$Path.bak") {
        if ($line -match '^\[mcp_servers\.databricks(\.|\])') { $skip = $true; continue }
        if ($line -match '^\[') { $skip = $false }
        if (-not $skip) { $out.Add($line) }
    }
    $out | Set-Content $Path -Encoding UTF8
    return $true
}

# Build the list of per-scope client config targets.
function Get-McpTargetsForScope {
    param([string]$BaseDir)
    if ($script:Scope -eq "global") {
        return @(
            @{ Path=(Join-Path $env:USERPROFILE ".claude.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $env:USERPROFILE ".codex\config.toml"); Kind="toml" },
            @{ Path=(Join-Path $env:USERPROFILE ".gemini\settings.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $env:USERPROFILE ".gemini\antigravity\mcp_config.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $env:USERPROFILE ".codeium\windsurf\mcp_config.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $env:USERPROFILE ".config\opencode\opencode.json"); Kind="json"; Top="mcp" },
            @{ Path=(Join-Path $env:USERPROFILE ".kiro\settings\mcp.json"); Kind="json"; Top="mcpServers" }
        )
    } else {
        return @(
            @{ Path=(Join-Path $BaseDir ".mcp.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $BaseDir ".cursor\mcp.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $BaseDir ".vscode\mcp.json"); Kind="json"; Top="servers" },
            @{ Path=(Join-Path $BaseDir ".codex\config.toml"); Kind="toml" },
            @{ Path=(Join-Path $BaseDir ".gemini\settings.json"); Kind="json"; Top="mcpServers" },
            @{ Path=(Join-Path $BaseDir "opencode.json"); Kind="json"; Top="mcp" },
            @{ Path=(Join-Path $BaseDir ".kiro\settings\mcp.json"); Kind="json"; Top="mcpServers" }
        )
    }
}

function Invoke-Uninstall {
    if (-not $script:Silent) {
        Write-Host ""
        Write-Host "Databricks MCP Server — Deregister" -ForegroundColor White
        Write-Host "--------------------------------"
    }

    # Mirror install: if scope wasn't set explicitly, ask (interactive, non -Yes).
    if (-not $script:ScopeExplicit -and -not $script:AssumeYes) {
        Invoke-PromptScope -Title "Select deregistration scope"
    }
    $baseDir = if ($script:Scope -eq "global") { $env:USERPROFILE } else { (Get-Location).Path }

    # Build the plan (only targets that actually contain our 'databricks' entry)
    $plan = @()
    foreach ($target in (Get-McpTargetsForScope $baseDir)) {
        switch ($target.Kind) {
            "json" { if (Test-McpJsonHasDatabricks $target.Path $target.Top) { $plan += $target } }
            "toml" {
                if ((Test-Path $target.Path) -and (Select-String -Path $target.Path -Pattern '^\[mcp_servers\.databricks' -Quiet)) {
                    $plan += $target
                }
            }
        }
    }

    if ($plan.Count -eq 0) {
        Write-Ok "Nothing to deregister for $($script:Scope) scope at $baseDir — no 'databricks' MCP entry found."
        if ($script:Scope -eq "project") { Write-Msg "Tip: pass -Global to remove a global registration." }
        exit 0
    }

    Write-Step "Deregister plan ($($script:Scope) scope)"
    Write-Host "  MCP config — remove 'databricks' entry ($($plan.Count)):" -ForegroundColor White
    foreach ($target in $plan) { Write-Host "    $($target.Path)" }
    Write-Host ""
    Write-Msg "Config files are backed up to <file>.bak before editing."

    if ($script:DryRun) {
        Write-Ok "Dry run — nothing was changed. Re-run without -DryRun to apply."
        exit 0
    }

    if (-not $script:AssumeYes) {
        if (Test-Interactive) {
            Write-Host "  Remove these $($plan.Count) item(s)? [y/N] " -ForegroundColor Yellow -NoNewline
            $reply = Read-Host
        } else {
            Write-Die "No terminal to confirm on. Re-run with -Yes to proceed non-interactively (or -DryRun to preview)."
        }
        if ($reply -notin @("y", "Y", "yes", "Yes", "YES")) { Write-Die "Aborted — nothing removed." }
    }

    Write-Step "Removing"
    foreach ($target in $plan) {
        switch ($target.Kind) {
            "json" { if (Remove-McpJsonKey $target.Path $target.Top) { Write-Msg "cleaned $($target.Path)" } }
            "toml" { if (Remove-McpTomlBlock $target.Path) { Write-Msg "cleaned $($target.Path)" } }
        }
    }

    Write-Host ""
    Write-Ok "databricks MCP server deregistered ($($script:Scope) scope)."
    Write-Msg "Per-editor .bak backups were left untouched."
    exit 0
}

# ─── Build the venv by delegating to setup.ps1 (single source of truth) ──
function Invoke-SetupMcp {
    Write-Step "Setting up MCP server"

    $setupScript = Join-Path $script:ScriptDir "setup.ps1"
    if (-not (Test-Path $setupScript)) { Write-Die "MCP setup script not found at $setupScript" }

    Write-Msg "Building MCP server environment (databricks-mcp-server/setup.ps1)..."
    $setupArgs = @("-VenvDir", $script:VenvDir)
    if ($script:Silent) { $setupArgs += "-Quiet" }
    & $setupScript @setupArgs
    if ($LASTEXITCODE -ne 0) { Write-Die "MCP server setup failed" }
    Write-Ok "MCP server ready"
}

# ─── Summary / post-hints ──────────────────────────────────────
function Show-Summary {
    if ($script:Silent) { return }
    Write-Host ""
    Write-Host "MCP registration complete!" -ForegroundColor Green
    Write-Host "--------------------------------"
    Write-Msg "Server:  $($script:McpEntry)"
    Write-Msg "Python:  $($script:VenvPython)"
    Write-Msg "Profile: $($script:Profile_)"
    Write-Msg "Scope:   $($script:Scope)"
    Write-Msg "Tools:   $(($script:Tools -split ' ') -join ', ')"
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
    }
    if ($script:Tools -match 'windsurf') {
        Write-Msg "$step. Restart Windsurf to pick up the databricks MCP server (Windsurf -> Settings -> Windsurf Settings -> MCP)"
        $step++
    }
    if ($script:Tools -match 'antigravity') {
        Write-Msg "$step. Open your project in Antigravity to use the databricks MCP tools"
        $step++
    }
    Write-Msg "$step. Open your project in your tool of choice and start prompting"
    Write-Host ""
}

# ─── Main ──────────────────────────────────────────────────────
function Invoke-Main {
    if ($script:Uninstall) {
        Invoke-Uninstall
    }

    if (-not $script:Silent) {
        Write-Host ""
        Write-Host "Databricks MCP Server — Client Registration" -ForegroundColor White
        Write-Host "--------------------------------"
    }

    # uv is required by setup.ps1; check early with a helpful message.
    if (-not $script:SkipVenv -and $null -eq (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Die "uv is required but not found on your PATH.
   Install it with: powershell -c ""irm https://astral.sh/uv/install.ps1 | iex""
   Then re-run this installer."
    }

    # ── Tool selection ──
    Write-Step "Selecting tools"
    Invoke-DetectTools
    Write-Ok "Selected: $(($script:Tools -split ' ') -join ', ')"

    # ── Profile selection ──
    Write-Step "Databricks profile"
    Invoke-PromptProfile
    Write-Ok "Profile: $($script:Profile_)"

    # ── Scope selection ──
    if (-not $script:ScopeExplicit) {
        Invoke-PromptScope
        Write-Ok "Scope: $($script:Scope)"
    }

    # ── Confirm ──
    if (-not $script:Silent) {
        Write-Host ""
        Write-Host "  Summary" -ForegroundColor White
        Write-Host "  ------------------------------------"
        Write-Host "  Tools:    " -NoNewline; Write-Host (($script:Tools -split ' ') -join ', ') -ForegroundColor Green
        Write-Host "  Profile:  " -NoNewline; Write-Host $script:Profile_ -ForegroundColor Green
        Write-Host "  Scope:    " -NoNewline; Write-Host $script:Scope -ForegroundColor Green
        Write-Host "  Venv:     " -NoNewline; Write-Host $script:VenvDir -ForegroundColor Green
        Write-Host ""
    }

    if ($script:DryRun) {
        Write-Ok "Dry run — nothing was changed. Re-run without -DryRun to apply."
        exit 0
    }

    if (-not $script:Silent -and (Test-Interactive)) {
        $confirm = Read-Prompt -PromptText "Proceed with MCP registration? (y/n)" -Default "y"
        if ($confirm -notin @("y", "Y", "yes", "Yes", "YES")) {
            Write-Host ""
            Write-Msg "Registration cancelled."
            exit 0
        }
    }

    # ── Build the venv (delegated to setup.ps1) ──
    if (-not $script:SkipVenv) {
        Invoke-SetupMcp
    }
    if (-not (Test-Path $script:VenvPython)) {
        Write-Warn "venv python not found at $($script:VenvPython) — configs will still be written, but build the venv with setup.ps1 before use."
    }

    # ── Write client configs ──
    $baseDir = if ($script:Scope -eq "global") { $env:USERPROFILE } else { (Get-Location).Path }
    Write-McpConfigs $baseDir

    Show-Summary
}

Invoke-Main
