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
& "$InstallDir\.venv\Scripts\pip.exe" install --find-links "$ScriptDir\wheels" `
    (Get-ChildItem "$ScriptDir\wheels\*.whl" | ForEach-Object { $_.FullName })
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
