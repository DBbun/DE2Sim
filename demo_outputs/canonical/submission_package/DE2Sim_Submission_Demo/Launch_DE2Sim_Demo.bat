@echo off
set "DEMO_DIR=%~dp0"
set "DASHBOARD=%DEMO_DIR%demo_dashboard.html"
if not exist "%DASHBOARD%" (
  echo DE2Sim demo dashboard is missing: "%DASHBOARD%"
  pause
  exit /b 1
)
start "" "%DASHBOARD%"
