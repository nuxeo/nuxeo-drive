@echo off
rem Launch integration tests.
rem Assume there is a folder "ndrive" on the desktop of the current user.
rem That folder is the result of build.bat when FREEZE_ONLY=1 is set.
rem The "ndrive" is then inside the "dist" folder of the $WORKSPACE_DRIVE.

call envvars.bat

set SPECIFIC_TEST=tests/integration/windows
%PYTHON% -m pytest -n0 --executable="%USERPROFILE%\Desktop\ndrive\ndrive.exe" %SPECIFIC_TEST% > %WORKSPACE%\tests-int.log
