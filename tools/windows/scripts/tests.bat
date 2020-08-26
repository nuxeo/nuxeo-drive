@echo off
rem Launch the complete tests suite.

call envvars.bat

rem You can skip some parts
rem See https://github.com/nuxeo/nuxeo-drive/blob/master/docs/deployment.md#optional-envars
set SKIP=integration

powershell -ExecutionPolicy Bypass .\tools\windows\deploy_ci_agent.ps1 -tests > %WORKSPACE%\tests.log
