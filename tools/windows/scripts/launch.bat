@echo off
rem Start the application from sources.

call envvars.bat

powershell -ExecutionPolicy Bypass .\tools\windows\deploy_ci_agent.ps1 -start
