# Usage: powershell ".\tools\windows\deploy_jenkins_slave.ps1" [ARG]
#
# Possible ARG:
#     -build: build the installer
#     -check_upgrade: check the auto-update works
#     -install: install all dependencies
#     -install_release: install all but test dependencies
#     -start: start Nuxeo Drive
#     -tests: launch the tests suite
#
# See /docs/deployment.md for more information.
#
# ---
#
# You can tweak tests checks by setting the SKIP envar:
#    - SKIP=rerun to not rerun failed test(s)
#
# There is no strict syntax about multiple skips (coma, coma + space, no separator, ... ).
#
param (
	[switch]$build = $false,
	[switch]$build_dlls = $false,
	[switch]$check_upgrade = $false,
	[switch]$install = $false,
	[switch]$install_release = $false,
	[switch]$start = $false,
	[switch]$tests = $false
)

# Stop the execution on the first error
$ErrorActionPreference = "Stop"

# Global variables
$global:PYTHON_OPT = "-Xutf8", "-E", "-s"
$global:PIP_OPT = "-m", "pip", "install", "--upgrade", "--upgrade-strategy=only-if-needed"

# Imports
Import-Module BitsTransfer

function add_missing_ddls {
	# Missing DLLS for Windows 7
	$folder = "C:\Program Files (x86)\Windows Kits\10\Redist\ucrt\DLLs\x86\"
	if (Test-Path $folder) {
		Get-ChildItem $folder | Copy -Verbose -Force -Destination "dist\ndrive"
	}
}

function build($app_version, $script) {
	# Build an executable
	Write-Output ">>> [$app_version] Building $script"
	if (-Not (Test-Path "$Env:ISCC_PATH")) {
		Write-Output ">>> ISCC does not exist: $Env:ISCC_PATH. Aborting."
		ExitWithCode 1
	}
	& $Env:ISCC_PATH\iscc /DMyAppVersion="$app_version" "$script"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function build_dll($project, $platform) {
	$folder = "$Env:WORKSPACE_DRIVE\tools\windows\NuxeoDriveShellExtensions"
	& $Env:MSBUILD_PATH\MSBuild.exe $folder\NuxeoDriveShellExtensions.sln /t:$project /p:Configuration=Release /p:Platform=$platform
}

function build_installer {
	# Build the installer
	$app_version = (Get-Content nxdrive/__init__.py) -match "__version__" -replace '"', "" -replace "__version__ = ", ""

	sign_dlls

	Write-Output ">>> [$app_version] Freezing the application"
	# freeze_nuitka
	freeze_pyinstaller

	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT tools\cleanup_application_tree.py "dist\ndrive"
	add_missing_ddls
	sign "dist\ndrive\ndrive.exe"

	# Stop now if we only want the application to be frozen (for integration tests)
	if ($Env:FREEZE_ONLY) {
		return 0
	}

	zip_files "dist\nuxeo-drive-windows-$app_version.zip" "dist\ndrive"

	build "$app_version" "tools\windows\setup-addons.iss"
	sign "dist\nuxeo-drive-addons.exe"

	build "$app_version" "tools\windows\setup.iss"
	sign "dist\nuxeo-drive-$app_version.exe"

	build "$app_version" "tools\windows\setup-admin.iss"
	sign "dist\nuxeo-drive-$app_version-admin.exe"
}

function build_overlays {
	$folder = "$Env:WORKSPACE_DRIVE\tools\windows\NuxeoDriveShellExtensions"
	$util_dll = "NuxeoDriveUtil"
	$overlay_dll = "NuxeoDriveOverlays"

	# List of DLLs to build
	$overlays = @(
		@{Name='NuxeoDriveSynced'; Id='1'; Icon='badge_synced'},
		@{Name='NuxeoDriveSyncing'; Id='2'; Icon='badge_syncing'},
		@{Name='NuxeoDriveConflicted'; Id='3'; Icon='badge_conflicted'},
		@{Name='NuxeoDriveError'; Id='4'; Icon='badge_error'},
		@{Name='NuxeoDriveLocked'; Id='5'; Icon='badge_locked'},
		@{Name='NuxeoDriveUnsynced'; Id='6'; Icon='badge_unsynced'}
	)

	$x64Path = "%name%_x64.dll"
	$Win32Path = "%name%_x86.dll"

	if (-Not ($Env:MSBUILD_PATH)) {
		$Env:MSBUILD_PATH = "C:\Program Files (x86)\Microsoft Visual Studio\2017\Community\MSBuild\15.0\Bin"
	}
	if (-Not (Test-Path -Path $Env:MSBUILD_PATH)) {
		Write-Output ">>> No MSBuild.exe accessible"
		ExitWithCode $lastExitCode
	}

	$OverlayConstants = "$folder\$overlay_dll\OverlayConstants.h"
	$OverlayConstantsOriginal = "$OverlayConstants.original"
	$Resources = "$folder\$overlay_dll\DriveOverlay.rc"
	$ResourcesOriginal = "$Resources.original"

	# Start build chain
	">>> Building $util_dll DLL"
	build_dll $util_dll "x64"
	build_dll $util_dll "Win32"

	foreach ($overlay in $overlays) {
		$id = $overlay["Id"]
		$name = $overlay["Name"]
		$icon = $overlay["Icon"]

		Write-Output ">>> Building $name DLL"
		# Fill templates with the right data
		(Get-Content $OverlayConstantsOriginal).replace('[$overlay.id$]', $id).replace('[$overlay.name$]', $name) | Set-Content $OverlayConstants
		(Get-Content $ResourcesOriginal).replace('[$overlay.icon$]', $icon) | Set-Content $Resources

		# Compile for x64 and Win32 and rename to the right status
		build_dll $overlay_dll "x64"
		build_dll $overlay_dll "Win32"

		$Oldx64Name = $x64Path.replace('%name%', $overlay_dll)
		$Newx64Name = $x64Path.replace('%name%', $name)
		$OldWin32Name = $Win32Path.replace('%name%', $overlay_dll)
		$NewWin32Name = $Win32Path.replace('%name%', $name)

		Rename-Item -Path $folder\Release\x64\$Oldx64Name -NewName $Newx64Name
		Rename-Item -Path $folder\Release\Win32\$OldWin32Name -NewName $NewWin32Name
	}

	# Delete everything that is not a DLL
	Get-ChildItem -Path $folder\Release -Recurse -File -Exclude *.dll | Foreach ($_) {Remove-Item $_.Fullname}
}

function check_import($import) {
	# Check module import to know if it must be installed
	# i.e: check_import "from PyQt4 import QtWebKit"
	#  or: check_import "import cx_Freeze"
	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -c $import
	if ($lastExitCode -eq 0) {
		return 1
	}
	return 0
}

function check_upgrade {
	# Ensure a new version can be released by checking the auto-update process.
    & $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT tools\scripts\check_update_process.py
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}


function check_vars {
	# Check required variables
	if (-Not ($Env:PYTHON_DRIVE_VERSION)) {
		$Env:PYTHON_DRIVE_VERSION = '3.7.4'  # XXX_PYTHON
	} elseif (-Not ($Env:WORKSPACE)) {
		Write-Output ">>> WORKSPACE not defined. Aborting."
		ExitWithCode 1
	}
	if (-Not ($Env:WORKSPACE_DRIVE)) {
		if (Test-Path "$($Env:WORKSPACE)\sources") {
			$Env:WORKSPACE_DRIVE = "$($Env:WORKSPACE)\sources"
		} elseif (Test-Path "$($Env:WORKSPACE)\nuxeo-drive") {
			$Env:WORKSPACE_DRIVE = "$($Env:WORKSPACE)\nuxeo-drive"
		} else {
			$Env:WORKSPACE_DRIVE = $Env:WORKSPACE
		}
	}
	if (-Not ($Env:ISCC_PATH)) {
		$Env:ISCC_PATH = "C:\Program Files (x86)\Inno Setup 6"  # XXX_INNO_SETUP
	}
	if (-Not ($Env:PYTHON_DIR)) {
		$ver_major, $ver_minor = $Env:PYTHON_DRIVE_VERSION.split('.')[0,1]
		$Env:PYTHON_DIR = "C:\Python$ver_major$ver_minor-32"
	}

	$Env:STORAGE_DIR = (New-Item -ItemType Directory -Force -Path "$($Env:WORKSPACE)\deploy-dir\$Env:PYTHON_DRIVE_VERSION").FullName

	Write-Output "    PYTHON_DRIVE_VERSION = $Env:PYTHON_DRIVE_VERSION"
	Write-Output "    WORKSPACE            = $Env:WORKSPACE"
	Write-Output "    WORKSPACE_DRIVE      = $Env:WORKSPACE_DRIVE"
	Write-Output "    STORAGE_DIR          = $Env:STORAGE_DIR"
	Write-Output "    PYTHON_DIR           = $Env:PYTHON_DIR"
	Write-Output "    ISCC_PATH            = $Env:ISCC_PATH"

	Set-Location "$Env:WORKSPACE_DRIVE"

	if (-Not ($Env:SPECIFIC_TEST) -Or ($Env:SPECIFIC_TEST -eq "")) {
		$Env:SPECIFIC_TEST = "tests"
	} else {
		Write-Output "    SPECIFIC_TEST        = $Env:SPECIFIC_TEST"
		$Env:SPECIFIC_TEST = "tests\$Env:SPECIFIC_TEST"
	}

	if (-Not ($Env:SKIP)) {
		$Env:SKIP = ""
	} else {
		Write-Output "    SKIP                 = $Env:SKIP"
	}
}

function download($url, $output) {
	# Download one file and save its content to a given file name
	# $output must be an absolute path.
	$try = 1
	while ($try -lt 6) {
		if (Test-Path "$output") {
			# Remove the confirmation due to "This came from another computer and migh
			# be blocked to help protect this computer"
			Unblock-File "$output"
			return
		}
		Write-Output ">>> [$try/5] Downloading $url"
		Write-Output "                   to $output"
		Try {
			Start-BitsTransfer -Source $url -Destination $output
		} Catch {}
		$try += 1
		Start-Sleep -s 5
	}

	Write-Output ">>> Impossible to download $url"
	ExitWithCode 1
}

function ExitWithCode($retCode) {
	$host.SetShouldExit($retCode)
	exit
}

function freeze_nuitka() {
	$env:PATH = "C:\mingw64\mingw32\bin;$env:PATH"

	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -OO -m nuitka `
		--standalone `
		--follow-imports `
		--python-flag=nosite,noasserts `
		--mingw64 `
		--plugin-enable=qt-plugins=iconengines,imageformats,platforms,platformthemes,qml,styles `
		--windows-icon=tools\windows\app_icon.ico `
		--windows-disable-console `
		--assume-yes-for-downloads `
		nxdrive

	# TODO: VersionInfo for the final executable
	# TODO: UPX

	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function freeze_pyinstaller() {
	# Note: -OO option cannot be set with PyInstaller
	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -m PyInstaller ndrive.spec --noconfirm

	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function install_deps {
	if (-Not (check_import "import pip")) {
		Write-Output ">>> Installing pip"
		# https://github.com/python/cpython/blob/master/Tools/msi/pip/pip.wxs#L28
		& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -OO -m ensurepip -U --default-pip
		if ($lastExitCode -ne 0) {
			ExitWithCode $lastExitCode
		}
	}

	Write-Output ">>> Installing requirements"
	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -OO $global:PIP_OPT -r tools\deps\requirements-pip.txt
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -OO $global:PIP_OPT -r tools\deps\requirements.txt
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -OO $global:PIP_OPT -r tools\deps\requirements-dev.txt
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
	if (-Not ($install_release)) {
		& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -OO $global:PIP_OPT -r tools\deps\requirements-tests.txt
		if ($lastExitCode -ne 0) {
			ExitWithCode $lastExitCode
		}
		# & $Env:STORAGE_DIR\Scripts\pre-commit.exe install
	}
	Remove-Item -Path "$Env:STORAGE_DIR\Lib\site-packages\PyQt5\QtBluetooth.pyd" -Verbose
	Remove-Item -Path "$Env:STORAGE_DIR\Lib\site-packages\PyQt5\Qt\bin\Qt5Bluetooth.dll" -Verbose
}

function install_python {
	if (Test-Path "$Env:STORAGE_DIR\Scripts\activate.bat") {
		& $Env:STORAGE_DIR\Scripts\activate.bat
		if ($lastExitCode -ne 0) {
			ExitWithCode $lastExitCode
		}
		return
	}

	# Fix a bloody issue with our slaves ... !
	New-Item -Path $Env:STORAGE_DIR -Name Scripts -ItemType directory
	Copy-Item $Env:PYTHON_DIR\vcruntime140.dll $Env:STORAGE_DIR\Scripts

	Write-Output ">>> Setting-up the Python virtual environment"

	& $Env:PYTHON_DIR\python.exe $global:PYTHON_OPT -OO -m venv --copies "$Env:STORAGE_DIR"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	& $Env:STORAGE_DIR\Scripts\activate.bat
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function junit_arg($path, $run) {
	$junit = "tools\jenkins\junit\xml"

	if ($run) {
		$run = ".$run"
	}
    return "--junitxml=$junit\$path$run.xml"
}

function launch_test($path, $pytest_args) {
	# Launch tests on a specific path. On failure, retry failed tests.
	$junitxml = junit_arg $path 1
	if ($Env:SPECIFIC_TEST -ne "tests") {
		# Skip JUnit report when running a specific test as it will fail because
		# of the "::" that may contain the report filename, see NXDRIVE-1994.
		$junitxml = ""
	}

	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -bb -Wall -m pytest $pytest_args $junitxml "$path"
	if ($lastExitCode -eq 0) {
		return
	}

	if (-not ($Env:SKIP -match 'rerun' -or $Env:SKIP -match 'all')) {
		# Will return 0 if rerun is needed else 1
		& $Env:STORAGE_DIR\Scripts\python.exe tools\check_pytest_lastfailed.py
		if ($lastExitCode -eq 1) {
			return
		}

		# Do not fail on error as all failures will be re-run another time at the end
		$junitxml = junit_arg $path 2
		& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -bb -Wall -m pytest `
			--last-failed --last-failed-no-failures none $junitxml
	}
}

function launch_tests {
	$junit_folder = "tools\jenkins\junit\xml"

	if (Test-Path ".pytest_cache") {
		Remove-Item -Path ".pytest_cache" -Verbose
	}

	# If a specific test is asked, just run it and bypass all over checks
	if ($Env:SPECIFIC_TEST -ne "tests") {
		Write-Output ">>> Launching the tests suite"
		launch_test "$Env:SPECIFIC_TEST"
		return
	}

	if (-not ($Env:SKIP -match 'tests')) {
		Write-Output ">>> Launching functional tests"
		launch_test "tests\functional"

		Write-Output ">>> Launching synchronization functional tests, file by file"
		Write-Output "    (first, run for each test file, failures are ignored to have"
		Write-Output "     a whole picture of errors)"
		$files = Get-ChildItem "tests\old_functional" -Filter test_*.py
		$total = $files.count
		$number = 1
		$files |  Foreach-Object {
			$test_file = "tests\old_functional\$_"
			Write-Output ""
			Write-Output ">>> [$number/$total] Testing $test_file ..."
			launch_test "$test_file" "-q" "--durations=3"
			$number = $number + 1
		}

		if (-not ($Env:SKIP -match 'rerun' -or $Env:SKIP -match 'all')) {
			Write-Output ">>> Re-rerun failed tests"

			& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -m pytest --cache-show
			# Will return 0 if rerun is needed else 1
			& $Env:STORAGE_DIR\Scripts\python.exe tools\check_pytest_lastfailed.py
			if ($lastExitCode -eq 1) {
				return
			}

			$junitxml = junit_arg "final"
			& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -bb -Wall -m pytest `
				--last-failed --last-failed-no-failures none $junitxml
			# The above command will exit with error code 5 if there is no failure to rerun
			$ret = $lastExitCode
		}

		& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT tools\jenkins\junit\merge.py

		if ($ret -ne 0 -and $ret -ne 5) {
			ExitWithCode $ret
		}
	}
}

function sign($file) {
	# Code sign a file
	if (-Not ($Env:SIGNTOOL_PATH)) {
		Write-Output ">>> SIGNTOOL_PATH not set, skipping code signature"
		return
	}
	if (-Not ($Env:SIGNING_ID)) {
		$Env:SIGNING_ID = "Nuxeo"
		Write-Output ">>> SIGNING_ID is not set, using 'Nuxeo'"
	}
	if (-Not ($Env:APP_NAME)) {
		$Env:APP_NAME = "Nuxeo Drive"
	}

	Write-Output ">>> Signing $file"
	& $Env:SIGNTOOL_PATH\signtool.exe sign `
		/a `
		/s MY `
		/n "$Env:SIGNING_ID" `
		/d "$Env:APP_NAME" `
		/fd sha256 `
		/tr http://timestamp.digicert.com/sha256/timestamp `
		/v `
		"$file"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	Write-Output ">>> Verifying $file"
	& $Env:SIGNTOOL_PATH\signtool.exe verify /pa /v "$file"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function sign_dlls {
	$folder = "$Env:WORKSPACE_DRIVE\tools\windows\dll"
	Get-ChildItem $folder -Recurse -Include *.dll | Foreach-Object {
		sign $_.FullName
	}
}

function start_nxdrive {
	# Start Nuxeo Drive
	$Env:PYTHONPATH = "$Env:WORKSPACE_DRIVE"
	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -OO -m nxdrive
}

function zip_files($filename, $src) {
	# Create a ZIP archive
	if (Test-Path $filename) {
		Remove-Item -Path $filename -Verbose
	}

	Add-Type -Assembly System.IO.Compression.FileSystem
	$compression_level = [System.IO.Compression.CompressionLevel]::Optimal
	[System.IO.Compression.ZipFile]::CreateFromDirectory(
		$src, $filename, $compression_level, $false)
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function main {
	# Launch operations
	check_vars
	install_python

	if ($build) {
		build_installer
	} elseif ($build_dlls) {
		build_overlays
	} elseif ($check_upgrade) {
		check_upgrade
	} elseif ($install -or $install_release) {
		install_deps
		if ((check_import "import PyQt5") -ne 1) {
			Write-Output ">>> No PyQt5. Installation failed."
			ExitWithCode 1
		}
	} elseif ($start) {
		start_nxdrive
	} elseif ($tests) {
		launch_tests
	}
}

main
