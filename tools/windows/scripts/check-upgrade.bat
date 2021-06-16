@echo off
rem Test the auto-upgrade process.

call envvars.bat

powershell -ExecutionPolicy Bypass .\tools\windows\deploy_ci_agent.ps1 -check_upgrade

echo.
pause
