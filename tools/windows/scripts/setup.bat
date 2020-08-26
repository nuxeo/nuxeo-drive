@echo off
rem Install/Update requirements.

call envvars.bat

powershell -ExecutionPolicy Bypass .\tools\windows\deploy_ci_agent.ps1 -install
