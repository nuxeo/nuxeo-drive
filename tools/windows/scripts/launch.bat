@echo off
rem Start the application from sources.

call envvars.bat

powershell -ExecutionPolicy Bypass .\tools\windows\deploy_jenkins_slave.ps1 -start
