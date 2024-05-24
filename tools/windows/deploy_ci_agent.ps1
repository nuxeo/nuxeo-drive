# Usage: powershell ".\tools\windows\deploy_ci_agent.ps1" [ARG]
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
$global:PIP_OPT = "-m", "pip", "install", "--no-cache-dir", "--upgrade", "--upgrade-strategy=only-if-needed", "--progress-bar=off"

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
		$filename = "innosetup-$Env:INNO_SETUP_VERSION.exe"
		$output = "$Env:WORKSPACE\$filename"
		$url = "https://mlaan2.home.xs4all.nl/ispack/$filename"
		download $url $output

		Write-Output ">>> Installing Inno Setup $Env:INNO_SETUP_VERSION"
		# https://jrsoftware.org/ishelp/index.php?topic=setupcmdline
		Start-Process $output -argumentlist "`
			/SP- `
			/VERYSILENT `
			/SUPPRESSMSGBOXES
			/TYPE=compact `
			" `
			-wait
	}

	& $Env:ISCC_PATH\iscc /DMyAppVersion="$app_version" "$script"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function build_dll($msbuild_exe, $project, $platform) {
	$folder = "$Env:WORKSPACE_DRIVE\tools\windows\NuxeoDriveShellExtensions"
	& $msbuild_exe $folder\NuxeoDriveShellExtensions.sln /t:$project /p:Configuration=Release /p:Platform=$platform
}

function build_installer {
	# Build the installer
	$app_version = (Get-Content nxdrive/__init__.py) -match "__version__" -replace '"', "" -replace "__version__ = ", ""

	# Build DDLs only on GitHub-CI, no need to loose time on the local dev machine
	if ($Env:GITHUB_WORKSPACE) {
		build_overlays
	}

	sign_dlls

	Write-Output ">>> [$app_version] Freezing the application"
	freeze_pyinstaller

	# Do some clean-up
	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT tools\cleanup_application_tree.py "dist\ndrive"

	# Remove compiled QML files
	Get-ChildItem -Path "dist\ndrive" -Recurse -File -Include *.qmlc | Foreach ($_) {Remove-Item -Verbose $_.Fullname}

	add_missing_ddls
	sign "dist\ndrive\ndrive.exe"

	# Stop now if we only want the application to be frozen (for integration tests)
	if ($Env:FREEZE_ONLY) {
		return 0
	}

	if ($Env:ZIP_NEEDED) {
		zip_files "dist\nuxeo-drive-windows-$app_version.zip" "dist\ndrive"
	}

	if (-Not ($Env:SKIP_ADDONS)) {
		build "$app_version" "tools\windows\setup-addons.iss"
		sign "dist\nuxeo-drive-addons.exe"
	}

	build "$app_version" "tools\windows\setup.iss"
	sign "dist\nuxeo-drive-$app_version.exe"

	build "$app_version" "tools\windows\setup-admin.iss"
	sign "dist\nuxeo-drive-$app_version-admin.exe"
}

function build_overlays {
	$folder = "$Env:WORKSPACE_DRIVE\tools\windows\NuxeoDriveShellExtensions"
	$util_dll = "NuxeoDriveUtil"
	$overlay_dll = "NuxeoDriveOverlays"

	# Remove old DLLs on GitHub-CI to prevent such errors:
	#	Rename-Item : Cannot create a file when that file already exists.
	if ($Env:GITHUB_WORKSPACE) {
		Get-ChildItem -Path $folder -Recurse -File -Include *.dll | Foreach ($_) {Remove-Item $_.Fullname}
	}

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

	# Find MSBuild.exe (https://github.com/Microsoft/vswhere/wiki/Find-MSBuild)
	$msbuild_exe = vswhere -latest -requires Microsoft.Component.MSBuild -find MSBuild\**\Bin\MSBuild.exe | select-object -first 1
	if (-Not ($msbuild_exe)) {
		Write-Output ">>> No MSBuild.exe accessible"
		ExitWithCode $lastExitCode
	}

	$OverlayConstants = "$folder\$overlay_dll\OverlayConstants.h"
	$OverlayConstantsOriginal = "$OverlayConstants.original"
	$Resources = "$folder\$overlay_dll\DriveOverlay.rc"
	$ResourcesOriginal = "$Resources.original"

	# Start build chain
	Write-Output ">>> Building $util_dll DLL"
	build_dll $msbuild_exe $util_dll "x64"
	build_dll $msbuild_exe $util_dll "Win32"

	foreach ($overlay in $overlays) {
		$id = $overlay["Id"]
		$name = $overlay["Name"]
		$icon = $overlay["Icon"]

		Write-Output ">>> Building $name DLL"
		# Fill templates with the right data
		(Get-Content $OverlayConstantsOriginal).replace('[$overlay.id$]', $id).replace('[$overlay.name$]', $name) | Set-Content $OverlayConstants
		(Get-Content $ResourcesOriginal).replace('[$overlay.icon$]', $icon) | Set-Content $Resources

		# Compile for x64 and Win32 and rename to the right status
		build_dll $msbuild_exe $overlay_dll "x64"
		build_dll $msbuild_exe $overlay_dll "Win32"

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
		$Env:PYTHON_DRIVE_VERSION = '3.9.5'  # XXX_PYTHON
	}
	if (-Not ($Env:WORKSPACE)) {
		if ($Env:GITHUB_WORKSPACE) {
			# Running from GitHub Actions
			$Env:WORKSPACE = (Get-Item $Env:GITHUB_WORKSPACE).parent.FullName
		} else {
			Write-Output ">>> WORKSPACE not defined. Aborting."
			ExitWithCode 1
		}
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
	if (-Not ($Env:INNO_SETUP_VERSION)) {
		$Env:INNO_SETUP_VERSION = "6.1.2"  # XXX_INNO_SETUP
	}
	if (-Not ($Env:PYTHON_DIR)) {
		$version = $Env:PYTHON_DRIVE_VERSION -replace '\.', ""
		$Env:PYTHON_DIR = "C:\Python$version-32"
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
			# Remove the confirmation due to "This came from another computer and might
			# be blocked to help protect this computer"
			Unblock-File "$output"
			return
		}
		Write-Output ">>> [$try/5] Downloading $url"
		Write-Output "                   to $output"
		Try {
			if ($Env:GITHUB_WORKSPACE) {
				$client = New-Object System.Net.WebClient
				$client.DownloadFile($url, $output)
			} else {
				Start-BitsTransfer -Source $url -Destination $output
			}
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

	# See NXDRIVE-1554 for details
	$bluetooth_pyd = "$Env:STORAGE_DIR\Lib\site-packages\PyQt5\QtBluetooth.pyd"
	$bluetooth_dll = "$Env:STORAGE_DIR\Lib\site-packages\PyQt5\Qt\bin\Qt5Bluetooth.dll"
	if (Test-Path $bluetooth_pyd) {
		Remove-Item -Path $bluetooth_pyd -Verbose
	}
	if (Test-Path $bluetooth_dll) {
		Remove-Item -Path $bluetooth_dll -Verbose
	}
}

function install_python {
	if (Test-Path "$Env:STORAGE_DIR\Scripts\activate.bat") {
		& $Env:STORAGE_DIR\Scripts\activate.bat
		if ($lastExitCode -ne 0) {
			ExitWithCode $lastExitCode
		}
		return
	}

	# Python needs to be downloaded and installed on GitHub-CI
	$filename = "python-$Env:PYTHON_DRIVE_VERSION.exe"
	$url = "https://www.python.org/ftp/python/$Env:PYTHON_DRIVE_VERSION/$filename"
	$output = "$Env:WORKSPACE\$filename"
	download $url $output

	Write-Output ">>> Installing Python $Env:PYTHON_DRIVE_VERSION into $Env:PYTHON_DIR"
	# https://docs.python.org/3.7/using/windows.html#installing-without-ui
	Start-Process $output -argumentlist "`
		/quiet `
		TargetDir=$Env:PYTHON_DIR `
		AssociateFiles=0 `
		CompileAll=1 `
		Shortcuts=0 `
		Include_doc=0 `
		Include_launcher=0 `
		InstallLauncherAllUsers=0 `
		Include_tcltk=0 `
		Include_test=0 `
		Include_tools=0 `
		" `
		-wait

	# Fix a bloody issue ... !
	New-Item -Path $Env:STORAGE_DIR -Name Scripts -ItemType directory -Verbose
	Copy-Item $Env:PYTHON_DIR\vcruntime140.dll $Env:STORAGE_DIR\Scripts -Verbose

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
			-n0 --last-failed --last-failed-no-failures none $junitxml
	}
}

function launch_tests {
	$junit_folder = "tools\jenkins\junit\xml"

	if (Test-Path ".pytest_cache") {
		# We can't use any PowerShell/batch command to delete recursively the folder in a reliable way.
		# See https://serverfault.com/q/199921/530506 for details and NXDRIVE-2212 for the error.
		& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -c "import shutil; shutil.rmtree('.pytest_cache')"
	}

	# If a specific test is asked, just run it and bypass all over checks
	if ($Env:SPECIFIC_TEST -ne "tests") {
		Write-Output ">>> Launching the tests suite"
		launch_test "$Env:SPECIFIC_TEST"
		return
	}

	if (-not ($Env:SKIP -match 'tests')) {
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
			if ($lastExitCode -eq 0) {
				$junitxml = junit_arg "final"
				& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -bb -Wall -m pytest `
					-n0 --last-failed --last-failed-no-failures none $junitxml
				# The above command will exit with error code 5 if there is no failure to rerun
				$ret = $lastExitCode
			}
		}

		$Env:TEST_SUITE = "Drive"
		& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT `
			tools\jenkins\junit\merge.py `
			tools\jenkins\junit\xml

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
		Write-Output ">>> SIGNING_ID is not set, using '$Env:SIGNING_ID'"
	}
	if (-Not ($Env:APP_NAME)) {
		$Env:APP_NAME = "Nuxeo Drive"
		Write-Output ">>> APP_NAME is not set, using '$Env:APP_NAME'"
	}

	if ($Env:GITHUB_WORKSPACE) {
		$cert = "certificate.pfx"
		if (Test-Path $cert) {
			Write-Output ">>> Importing the code signing certificate"
			$password = ConvertTo-SecureString -String $Env:KEYCHAIN_PASSWORD -AsPlainText -Force
			Import-PfxCertificate -FilePath $cert -CertStoreLocation "Cert:\LocalMachine\My" -Password $password

			# Remove the file to not import it again the next run
			Remove-Item -Path $cert -Verbose
		}
	}

	Write-Output ">>> Signing $file"
	& $Env:SIGNTOOL_PATH\signtool.exe sign `
		/a `
		/sm `
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
