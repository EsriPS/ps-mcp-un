@echo off
rem Start the PS-MCP server using a local env file.
rem
rem Usage:
rem   start-ps-mcp-un.bat                       uses .env next to this script
rem   start-ps-mcp-un.bat path\to\other.env     uses the given env file
rem
rem Requires the project virtual environment (.venv). Create it with: uv sync --all-packages

setlocal
cd /d "%~dp0"

set "ENV_FILE=%~1"
if "%ENV_FILE%"=="" set "ENV_FILE=%~dp0.env"

set "PSMCP_EXE=%~dp0.venv\Scripts\psmcp.exe"

if not exist "%PSMCP_EXE%" (
    echo [ERROR] %PSMCP_EXE% not found.
    echo Create the virtual environment first: uv sync --all-packages
    exit /b 1
)

if not exist "%ENV_FILE%" (
    echo [ERROR] Env file not found: %ENV_FILE%
    echo Copy .env.sample to .env and fill in your values.
    exit /b 1
)

echo Starting PS-MCP server with env file: %ENV_FILE%
"%PSMCP_EXE%" --env-file "%ENV_FILE%" serve
set "EXIT_CODE=%ERRORLEVEL%"

endlocal & exit /b %EXIT_CODE%
