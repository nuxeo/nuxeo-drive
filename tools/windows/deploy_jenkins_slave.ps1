# Usage: powershell ".\tools\windows\deploy_jenkins_slave.ps1" [ARG]
#
# Possible ARG:
#     -build: build the MSI package
#     -tests: launch the tests suite
#
# See /docs/deployment.md for more informations.
param ([switch]$build = $false, [switch]$tests = $false)

# Stop the execution on the first error
$ErrorActionPreference = "Stop"

function build_msi {
	# Build the famous MSI
	echo ">>> Building the MSI package"
	& $Env:PYTHON_DIR\python -E setup.py --freeze bdist_msi
	if ($lastExitCode -eq 0) {
		ExitWithCode $lastExitCode
	}
}

function check_import($import) {
	# Check module import to know if it must be installed
	# i.e: check_import "from PyQt4 import QtWebKit"
	#  or: check_import "import cx_Freeze"

	& $Env:PYTHON_DIR\python -E -c "$import"
	if ($lastExitCode -eq 0) {
		return 1
	}
	return 0
}

function check_vars {
	# Check required variables
	if (-Not ($Env:PYTHON_DRIVE_VERSION)) {
		echo "PYTHON_DRIVE_VERSION not defined. Aborting."
		exit 1
	#} elseif (-Not ($Env:PYQT_VERSION)) {
	#	echo "PYQT_VERSION not defined. Aborting."
	#	exit 1
	} elseif (-Not ($Env:WORKSPACE)) {
		echo "WORKSPACE not defined. Aborting."
		exit 1
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
	if (-Not ($Env:CXFREEZE_VERSION)) {
		$Env:CXFREEZE_VERSION = "4.3.3"
	}

	# For now, we cannot use other PyQt version than this one
	# Later we will need to add a check on this envar like for WORKSPACE and PYTHON_DRIVE_VERSION
	$Env:PYQT_VERSION = "4.11.4"
	$Env:STORAGE_DIR = (New-Item -ItemType Directory -Force -Path "$($Env:WORKSPACE)\deploy-dir").FullName
	$Env:PYTHON_DIR = "$Env:STORAGE_DIR\drive-$Env:PYTHON_DRIVE_VERSION-python"

	echo "    PYTHON_DRIVE_VERSION = $Env:PYTHON_DRIVE_VERSION"
	echo "    PYQT_VERSION         = $Env:PYQT_VERSION"
	echo "    WORKSPACE            = $Env:WORKSPACE"
	echo "    WORKSPACE_DRIVE      = $Env:WORKSPACE_DRIVE"
	echo "    STORAGE_DIR          = $Env:STORAGE_DIR"
	echo "    PYTHON_DIR           = $Env:PYTHON_DIR"

	Set-Location "$Env:WORKSPACE_DRIVE"

	if (-Not ($Env:SPECIFIC_TEST) -Or ($Env:SPECIFIC_TEST -eq "") -Or ($Env:SPECIFIC_TEST -eq "nuxeo-drive-client\tests")) {
		$Env:SPECIFIC_TEST = "nuxeo-drive-client\tests"
	} else {
		echo "    SPECIFIC_TEST        = $Env:SPECIFIC_TEST"
		$Env:SPECIFIC_TEST = "nuxeo-drive-client\tests\$Env:SPECIFIC_TEST"
	}
}

function download($url, $output) {
	# Download one file and save its content to a given file name
	echo ">>> Downloading $url"
	echo "             to $output"
	if (-Not (Test-Path $output)) {
		$curl = New-Object System.Net.WebClient
		$curl.DownloadFile($url, $output)
	}
}

function ExitWithCode($retCode) {
	$host.SetShouldExit($retCode)
	exit
}

function install_cxfreeze {
	# Install cx_Freeze manually as pip does not work for this package
	$output = "$Env:STORAGE_DIR\cx_Freeze-$Env:CXFREEZE_VERSION.win32-py2.7.msi"
	$url = "https://s3-eu-west-1.amazonaws.com/nuxeo-jenkins-resources/drive/cx_Freeze-$Env:CXFREEZE_VERSION.win32-py2.7.msi"

	if (check_import "import cx_Freeze") {
		return
	}

	download $url $output
	echo ">>> Installing cx_Freeze"
	Start-Process msiexec -ArgumentList "/a `"$output`" /passive TARGETDIR=`"$Env:PYTHON_DIR`"" -wait
}

function install_deps {
	echo ">>> Installing requirements"
	& $Env:PYTHON_DIR\python -E -m pip install -q -t "$Env:PYTHON_DIR" -r requirements.txt
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
	& $Env:PYTHON_DIR\python -E -m pip install -q -t "$Env:PYTHON_DIR" -r requirements-windows.txt
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function install_pip {
	$output = "$Env:STORAGE_DIR\get-pip.py"
	$url = "https://bootstrap.pypa.io/get-pip.py"

	if (check_import "import pip") {
		return
	}

	echo ">>> Installing pip"
	download $url $output
	& $Env:PYTHON_DIR\python -E "$output" -q -t "$Env:PYTHON_DIR"
	$ret = $lastExitCode

	# Cleanup
	Remove-Item -Force "$output"

	if ($ret -ne 0) {
		ExitWithCode $ret
	}
}

function install_pyqt {
	$output = "$Env:STORAGE_DIR\PyQt4-$Env:PYQT_VERSION-gpl-Py2.7-Qt4.8.7-x32.exe"
	$url = "https://s3-eu-west-1.amazonaws.com/nuxeo-jenkins-resources/drive/PyQt4-$Env:PYQT_VERSION-gpl-Py2.7-Qt4.8.7-x32.exe"
	$packages = "$Env:PYTHON_DIR\Lib\site-packages"
	$packages_pyqt = "$packages\PyQt4"
	$source = "Lib\site-packages"
	$source_pyqt = "Lib\site-packages\PyQt4"

	if (check_import "import PyQt4.QtWebKit") {
		return
	}

	download $url $output
	Set-Location "$Env:STORAGE_DIR"

	echo ">>> Installing PyQt $Env:PYQT_VERSION"
	& 7z x "$output" "Lib" "`$_OUTDIR" -xr"!doc" -xr"!examples" -xr"!mkspecs" -xr"!sip" -y
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
	Copy-Item -Force "$source\sip.pyd" -Destination "$packages"
	Copy-Item -Recurse -Force "$source_pyqt\imports" -Destination "$packages_pyqt"
	Copy-Item -Recurse -Force "$source_pyqt\plugins" -Destination "$packages_pyqt"
	Copy-Item -Force "$source_pyqt\__init__.py" -Destination "$packages_pyqt"
	Copy-Item -Force "$source_pyqt\*.dll" -Destination "$packages_pyqt"
	Copy-Item -Force "`$_OUTDIR\*.pyd" -Destination "$packages_pyqt"

	# Delete useless modules
	Remove-Item -Recurse -Force "$packages_pyqt\plugins\designer"
	Remove-Item -Recurse -Force "$packages_pyqt\plugins\phonon_backend"
	Remove-Item -Force "$packages_pyqt\phonon*"
	Remove-Item -Force "$packages_pyqt\Qsci*"
	Remove-Item -Force "$packages_pyqt\QtDeclarative*"
	Remove-Item -Force "$packages_pyqt\QtDesigner*"
	Remove-Item -Force "$packages_pyqt\QtHelp*"
	Remove-Item -Force "$packages_pyqt\QtOpenGL*"
	Remove-Item -Force "$packages_pyqt\QtTest*"

	# Cleanup
	Remove-Item -Recurse -Force "Lib"
	Remove-Item -Recurse -Force "`$_OUTDIR"

	Set-Location "$Env:WORKSPACE_DRIVE"
}

function install_python {
	$output = "$Env:STORAGE_DIR\python-$Env:PYTHON_DRIVE_VERSION.msi"
	$url = "https://www.python.org/ftp/python/$Env:PYTHON_DRIVE_VERSION/python-$Env:PYTHON_DRIVE_VERSION.msi"

	if (Test-Path "$Env:PYTHON_DIR\python.exe") {
		return
	}

	download $url $output
	echo ">>> Installing Python"
	Start-Process msiexec -ArgumentList "/a `"$output`" /passive TARGETDIR=`"$Env:PYTHON_DIR`"" -wait
}

function launch_tests {
	# Launch the tests suite
	& $Env:PYTHON_DIR\python -E -m pip install -q -t "$Env:PYTHON_DIR" -r requirements-tests.txt
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
	& $Env:PYTHON_DIR\python -E -m pytest --showlocals --exitfirst --strict --failed-first -r Efx --full-trace --capture=sys --no-cov-on-fail --cov-append --cov-report term-missing:skip-covered --cov-report html:..\coverage --cov=nuxeo-drive-client\nxdrive "$Env:SPECIFIC_TEST"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function sign_msi {
	# Sign the MSI
	$dest = "dist"
	$certificate = "$Env:USERPROFILE\certificates\nuxeo.com.pfx"
	$password = ""
	$msi = "Nuxeo Drive"
	$timestamp_url =  "http://timestamp.verisign.com/scripts/timstamp.dll"

	echo ">>> Signing the MSI"
	& signtool sign /v /f "$certificate" /p "$password" /d "$msi" /t "$timstamp"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	echo ">>> Verifying the signature"
	& signtool verify /v /pa "$dest/*.msi"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function main {
	# Launch operations
	check_vars
	install_python
	install_pip
	install_deps
	install_pyqt
	install_cxfreeze
	if ((check_import "import PyQt4.QtWebKit") -ne 1) {
		echo ">>> Installation failed."
		ExitWithCode 1
	}

	if ($build) {
		build_msi
		# sign_msi
	} elseif ($tests) {
		launch_tests
	}
}

main
