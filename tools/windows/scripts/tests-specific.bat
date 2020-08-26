@echo off
rem Launch the tests suite on a specific test file/class/function.
rem See https://github.com/nuxeo/nuxeo-drive/blob/master/docs/deployment.md#optional-envars

call envvars.bat

set SKIP=rerun
set SPECIFIC_TEST=old_functional/test_context_menu.py
powershell -ExecutionPolicy Bypass .\tools\windows\deploy_ci_agent.ps1 -tests > %WORKSPACE%\tests-spec.log
