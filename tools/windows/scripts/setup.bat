@echo off
rem Install/Update requirements.

call envvars.bat

powershell -ExecutionPolicy Bypass .\tools\windows\deploy_jenkins_slave.ps1 -install
