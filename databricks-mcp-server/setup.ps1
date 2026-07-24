#
# Setup script for databricks-mcp-server (Windows).
#
# Creates the Python virtual environment and installs the MCP server (plus its
# databricks-tools-core dependency) in editable mode, then verifies the install.
#
# This is the single source of truth for building the MCP server runtime on
# Windows. The unified installers only write the editor config files that point
# at the venv — when the user opts into the (deprecated) MCP server, they
# delegate the actual environment build here.
#
# Usage:
#   .\databricks-mcp-server\setup.ps1 [OPTIONS]
#
# Options:
#   -VenvDir DIR   Location for the virtual environment (default: <this dir>\.venv)
#   -Python VER    Python version to request from uv (default: 3.11)
#   -Quiet         Suppress progress output (errors still print)
#   -Help          Show this help
#

$ErrorActionPreference = "Stop"

# ─── Parse arguments (accept both -Style and --style for parity with bash) ───
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ParentDir = Split-Path -Parent $ScriptDir
$ToolsCoreDir = Join-Path $ParentDir "databricks-tools-core"

$VenvDir = Join-Path $ScriptDir ".venv"
$PythonVersion = "3.11"
$Quiet = $false

$i = 0
while ($i -lt $args.Count) {
    switch ($args[$i]) {
        { $_ -in "--venv-dir", "-VenvDir" } { $VenvDir = $args[$i + 1]; $i += 2 }
        { $_ -in "--python", "-Python" }    { $PythonVersion = $args[$i + 1]; $i += 2 }
        { $_ -in "--quiet", "-Quiet" }      { $Quiet = $true; $i++ }
        { $_ -in "-h", "--help", "-Help" } {
            Write-Host "Setup the Databricks MCP server runtime (Windows)"
            Write-Host ""
            Write-Host "Usage: .\databricks-mcp-server\setup.ps1 [OPTIONS]"
            Write-Host ""
            Write-Host "  -VenvDir DIR   Virtual environment location (default: <script dir>\.venv)"
            Write-Host "  -Python VER    Python version for uv (default: 3.11)"
            Write-Host "  -Quiet         Suppress progress output"
            Write-Host "  -Help          Show this help"
            return
        }
        default { Write-Host "Unknown option: $($args[$i])" -ForegroundColor Red; exit 1 }
    }
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$MinSdkVersion = "0.85.0"

# Output helpers (respect -Quiet; errors always print)
function Say { param([string]$Text) if (-not $Quiet) { Write-Host $Text } }
function Die { param([string]$Text) Write-Host "Error: $Text" -ForegroundColor Red; exit 1 }

Say "======================================"
Say "Setting up Databricks MCP Server"
Say "======================================"
Say ""
Say "MCP Server directory: $ScriptDir"
Say "Tools Core directory: $ToolsCoreDir"
Say "Virtual environment:  $VenvDir"
Say ""

# Pick a package manager: prefer uv, fall back to pip via the venv
$pkg = ""
if (Get-Command uv -ErrorAction SilentlyContinue) {
    $pkg = "uv"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pkg = "pip"
} else {
    Die "Neither 'uv' nor 'python' found on PATH. Install Python (choco install python -y) or uv, then re-run."
}
Say "✓ package manager: $pkg"

if (-not (Test-Path $ToolsCoreDir)) {
    Die "databricks-tools-core not found at $ToolsCoreDir"
}
Say "✓ databricks-tools-core found"

# Native commands (uv, pip) write informational messages to stderr; relax error
# handling so those don't terminate the script.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"

Say ""
Say "Creating virtual environment..."
if ($pkg -eq "uv") {
    & uv venv --python $PythonVersion --allow-existing $VenvDir -q 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { & uv venv --allow-existing $VenvDir -q 2>&1 | Out-Null }
} else {
    if (-not (Test-Path $VenvDir)) { & python -m venv $VenvDir 2>&1 | Out-Null }
}
Say "✓ Virtual environment ready"

Say ""
Say "Installing databricks-tools-core and databricks-mcp-server (editable)..."
if ($pkg -eq "uv") {
    & uv pip install --python $VenvPython -e $ToolsCoreDir -e $ScriptDir -q 2>&1 | Out-Null
} else {
    & $VenvPython -m pip install -q -e $ToolsCoreDir -e $ScriptDir 2>&1 | Out-Null
}
Say "✓ Packages installed"

# Verify
Say ""
Say "Verifying installation..."
& $VenvPython -c "import databricks_mcp_server" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    $ErrorActionPreference = $prevEAP
    Die "Failed to import databricks_mcp_server"
}
Say "✓ MCP server can be imported"

# Check Databricks SDK version
try {
    $sdkOutput = & $VenvPython -c "from databricks.sdk.version import __version__; print(__version__)" 2>&1
    if ($sdkOutput -match '(\d+\.\d+\.\d+)') {
        $sdkVersion = $Matches[1]
        if ([version]$sdkVersion -ge [version]$MinSdkVersion) {
            Say "✓ Databricks SDK v$sdkVersion"
        } else {
            Say "! Databricks SDK v$sdkVersion is outdated (minimum: v$MinSdkVersion)"
            Say "  Upgrade: $VenvPython -m pip install --upgrade databricks-sdk"
        }
    } else {
        Say "! Could not determine Databricks SDK version"
    }
} catch {
    Say "! Could not determine Databricks SDK version"
}

$ErrorActionPreference = $prevEAP

if (-not $Quiet) {
    $pyForJson = $VenvPython -replace '\\', '/'
    $entryForJson = (Join-Path $ScriptDir "run_server.py") -replace '\\', '/'
    Write-Host ""
    Write-Host "======================================"
    Write-Host "Setup complete!"
    Write-Host "======================================"
    Write-Host ""
    Write-Host "To run the MCP server:"
    Write-Host "  $VenvPython $(Join-Path $ScriptDir 'run_server.py')"
    Write-Host ""
    Write-Host "MCP config snippet (.mcp.json for Claude, .cursor/mcp.json for Cursor):"
    Write-Host @"
    {
      "mcpServers": {
        "databricks": {
          "command": "$pyForJson",
          "args": ["$entryForJson"],
          "defer_loading": true
        }
      }
    }
"@
    Write-Host ""
}
