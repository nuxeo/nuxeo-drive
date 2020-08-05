@echo off
rem Primary environment variables to control all other scripts.
rem https://github.com/nuxeo/nuxeo-drive/blob/master/docs/deployment.md

rem The absolute path to the WORKSPACE, here on the current user desktop
set WORKSPACE=%USERPROFILE%\Desktop

rem The absolute path to the application sources.
rem If not defined, it will be set to $WORKSPACE\sources or $WORKSPACE\nuxeo-drive.
rem If no folder exists, it will be set to $WORKSPACE.
set WORKSPACE_DRIVE=z:

rem The Nuxeo URL, if different from "http://localhost:8080/nuxeo"
rem set NXDRIVE_TEST_NUXEO_URL=http://192.168.0.25:8080/nuxeo

rem Convenient variable for later use
set PYTHON=%WORKSPACE%\deploy-dir\%PYTHON_DRIVE_VERSION%\Scripts\python.exe

rem Keep it up-to-date with the current git branch!
rem set SENTRY_ENV=NXDRIVE-xxx

cd /D %WORKSPACE_DRIVE%
