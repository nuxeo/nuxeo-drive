@echo off
rem Test the auto-upgrade process.

call envvars.bat

%python% tools\scripts\check_update_process.py

echo.
pause
