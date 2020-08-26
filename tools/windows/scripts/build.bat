@echo off
rem Build the application and its installer.

call envvars.bat

rem Uncomment to only build the application, bypassing ZIP creation and installer generation.
rem This is useful when testing integration where you need only the app exe.
rem set FREEZE_ONLY=1

powershell -ExecutionPolicy Bypass .\tools\windows\deploy_ci_agent.ps1 -build
