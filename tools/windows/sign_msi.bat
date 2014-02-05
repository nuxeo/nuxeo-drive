@echo off

set DIST_DIR=dist
set CERTIFICATE_PATH="%USERPROFILE%\certificates\nuxeo.com.pfx"
set PFX_PASSWORD=""
set MSI_PROGRAM_NAME="Nuxeo Drive"
set TIMESTAMP_URL=http://timestamp.verisign.com/scripts/timstamp.dll

set SIGN_CMD=signtool sign /v /f %CERTIFICATE_PATH% /p %PFX_PASSWORD% /d %MSI_PROGRAM_NAME% /t %TIMESTAMP_URL%
set VERIFY_CMD=signtool verify /v /pa

FOR %%F IN (%DIST_DIR%\*.msi) DO (
	echo ---------------------------------------------
	echo Signing %%F
    echo ---------------------------------------------
	echo %SIGN_CMD% %%F
	%SIGN_CMD% %%F
	echo ---------------------------------------------
    echo Verifying %%F
	echo ---------------------------------------------
    echo %VERIFY_CMD% %%F
	%VERIFY_CMD% %%F
)
