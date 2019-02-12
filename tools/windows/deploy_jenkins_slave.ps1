# Usage: powershell ".\tools\windows\deploy_jenkins_slave.ps1" [ARG]
#
# Possible ARG:
#     -build: build the installer
#     -install: install all dependencies
#     -start: start Nuxeo Drive
#     -tests: launch the tests suite
#
# See /docs/deployment.md for more informations.
param (
	[switch]$build = $false,
	[switch]$install = $false,
	[switch]$install_release = $false,
	[switch]$start = $false,
	[switch]$tests = $false
)

# Stop the execution on the first error
$ErrorActionPreference = "Stop"

# Global variables
$global:PYTHON_OPT = "-E", "-s"
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

function build_installer {
	# Build the installer
	$app_version = (Get-Content nxdrive/__init__.py) -match "__version__" -replace '"', "" -replace "__version__ = ", ""

	Write-Output ">>> [$app_version] Freezing the application"
	& $Env:STORAGE_DIR\Scripts\pyinstaller ndrive.spec --noconfirm
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT tools\cleanup_application_tree.py "dist\ndrive"
	add_missing_ddls
	sign "dist\ndrive\ndrive.exe"
	zip_files "dist\nuxeo-drive-windows.zip" "dist\ndrive"

	build "$app_version" "tools\windows\setup-addons.iss"
	sign "dist\nuxeo-drive-addons.exe"

	build "$app_version" "tools\windows\setup.iss"
	sign "dist\nuxeo-drive-$app_version.exe"

	build "$app_version" "tools\windows\setup-admin.iss"
	sign "dist\nuxeo-drive-$app_version-admin.exe"
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

function check_vars {
	# Check required variables
	if (-Not ($Env:PYTHON_DRIVE_VERSION)) {
		$Env:PYTHON_DRIVE_VERSION = '3.6.7'  # XXX_PYTHON
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
		$Env:ISCC_PATH = "C:\Program Files (x86)\Inno Setup 5"
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

function install_deps {
	if (-Not (check_import "import pip")) {
		Write-Output ">>> Installing pip"
		# https://github.com/python/cpython/blob/master/Tools/msi/pip/pip.wxs#L28
		& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -m ensurepip -U --default-pip
		if ($lastExitCode -ne 0) {
			ExitWithCode $lastExitCode
		}
	}

	Write-Output ">>> Installing requirements"
	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT $global:PIP_OPT -r requirements.txt
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
	if (-Not ($install_release)) {
		& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT $global:PIP_OPT -r requirements-dev.txt
		if ($lastExitCode -ne 0) {
			ExitWithCode $lastExitCode
		}
		& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT $global:PIP_OPT -r requirements-tests.txt
		if ($lastExitCode -ne 0) {
			ExitWithCode $lastExitCode
		}
		# & $Env:STORAGE_DIR\Scripts\pre-commit.exe install
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

	# Fix a bloody issue with our slaves ... !
	New-Item -Path $Env:STORAGE_DIR -Name Scripts -ItemType directory
	Copy-Item $Env:PYTHON_DIR\vcruntime140.dll $Env:STORAGE_DIR\Scripts

	Write-Output ">>> Setting-up the Python virtual environment"

	& $Env:PYTHON_DIR\python.exe -m venv --copies "$Env:STORAGE_DIR"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	& $Env:STORAGE_DIR\Scripts\activate.bat
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function launch_tests {
	# Launch the tests suite
	$Env:MYPYPATH = "$Env:WORKSPACE_DRIVE\tools\stubs"

	if ($Env:SPECIFIC_TEST -eq "tests") {
		Write-Output ">>> Checking the style"
		& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -m flake8 .
		if ($lastExitCode -ne 0) {
			ExitWithCode $lastExitCode
		}

		Write-Output ">>> Checking type annotations"
		& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -m mypy --ignore-missing-imports nxdrive
		if ($lastExitCode -ne 0) {
			ExitWithCode $lastExitCode
		}
	}

	# Write-Output ">>> Launching the tests suite"
	# & $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -b -Wall -m pytest $Env:SPECIFIC_TEST
	# if ($lastExitCode -ne 0) {
	# 	ExitWithCode $lastExitCode
	# }

	Write-Output ">>> Launching unit tests"
	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -b -Wall -m pytest -n 4 "tests\\unit"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	Write-Output ">>> Launching functional tests"
	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -b -Wall -m pytest -n 4 "tests\\functional"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	Write-Output ">>> Launching old functional tests"
	& $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -b -Wall -m pytest -v "tests\\old_functional"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	# Write-Output ">>> Launching integration tests"
	# & $Env:STORAGE_DIR\Scripts\python.exe $global:PYTHON_OPT -b -Wall -m pytest "tests\\integration"
	# if ($lastExitCode -ne 0) {
	# 	ExitWithCode $lastExitCode
	# }
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
		/a  `
		/s MY `
		/n "$Env:SIGNING_ID" `
		/d "$Env:APP_NAME" `
		/fd sha256 `
		/tr http://sha256timestamp.ws.symantec.com/sha256/timestamp `
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

function start_nxdrive {
	# Start Nuxeo Drive
	$Env:PYTHONPATH = "$Env:WORKSPACE_DRIVE"
	& $Env:STORAGE_DIR\Scripts\python.exe -m nxdrive
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
