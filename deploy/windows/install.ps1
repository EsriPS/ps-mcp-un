# PS-MCP Deployment Installer (Windows)
param([string]$InstallDir = (Get-Location))
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Installing PS-MCP to: $InstallDir"
if (-not (Test-Path "$InstallDir\.venv")) {
    Write-Host "Creating virtual environment..."
    try { uv venv --python 3.13 --seed "$InstallDir\.venv" }
    catch { py -3.13 -m venv "$InstallDir\.venv" }
}
Write-Host "Installing wheels..."
$Wheels = (Get-ChildItem "$ScriptDir\wheels\*.whl" | ForEach-Object { $_.FullName })
$Pip = "$InstallDir\.venv\Scripts\pip.exe"
# Prefer a fully offline install (works when the package was built with
# --include-deps so all third-party dependencies are bundled). If that fails -
# typically because transitive deps like 'requests' are missing from wheels\ -
# fall back to resolving the remainder from PyPI.
& $Pip install --no-index --find-links "$ScriptDir\wheels" $Wheels
if ($LASTEXITCODE -ne 0) {
    Write-Host "Offline install incomplete; retrying with PyPI for missing dependencies..."
    & $Pip install --find-links "$ScriptDir\wheels" $Wheels
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}
if ((Test-Path "$ScriptDir\config") -and -not (Test-Path "$InstallDir\.psmcp")) {
    New-Item -ItemType Directory -Force -Path "$InstallDir\.psmcp" | Out-Null
    Copy-Item "$ScriptDir\config\*" "$InstallDir\.psmcp\"
    Write-Host "Copied router config to $InstallDir\.psmcp\"
}
if (-not (Test-Path "$InstallDir\.env") -and (Test-Path "$ScriptDir\.env.sample")) {
    Copy-Item "$ScriptDir\.env.sample" "$InstallDir\.env"
    Write-Host "Created .env from sample - edit it with your settings"
}
Write-Host ""
Write-Host "Installation complete!"
Write-Host "Start the server:"
Write-Host "  $InstallDir\.venv\Scripts\psmcp.exe --env-file $InstallDir\.env serve"
