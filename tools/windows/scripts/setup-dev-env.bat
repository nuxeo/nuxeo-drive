@echo off
rem Install dev environment and requirements.

call envvars.bat

%PYTHON% -m venv venv
venv\Scripts\python.exe -m pip install -r tools\deps\requirements-dev.txt -r tools\deps\requirements-pip.txt -r tools\deps\requirements-tests.txt -r tools\deps\requirements-tox.txt --upgrade-strategy=only-if-needed
