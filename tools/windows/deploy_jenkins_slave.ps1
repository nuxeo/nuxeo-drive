# Usage: powershell ".\tools\windows\deploy_jenkins_slave.ps1" [ARG]
#
# Possible ARG:
#     -build: build the MSI package
#     -tests: launch the tests suite
param ([switch]$build = $false, [switch]$tests = $false)

# Stop the execution on the first error
$ErrorActionPreference = "Stop"

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

# For now, we cannot use other PyQt version than this one
# Later we will need to add a check on this envar like for WORKSPACE and PYTHON_DRIVE_VERSION
$Env:PYQT_VERSION = "4.11.4"
$PYTHON_DRIVE_VERSION = $Env:PYTHON_DRIVE_VERSION
$STORAGE_DIR = (New-Item -ItemType Directory -Force -Path "$($Env:WORKSPACE)\deploy-dir").FullName
$PYTHON_DIR = "$STORAGE_DIR\drive-$PYTHON_DRIVE_VERSION-python"

function ExitWithCode($retCode) {
	$host.SetShouldExit($retCode)
	exit
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

function install_python {
	$output = "$STORAGE_DIR\python-$PYTHON_DRIVE_VERSION.msi"
	$url = "https://www.python.org/ftp/python/$PYTHON_DRIVE_VERSION/python-$PYTHON_DRIVE_VERSION.msi"

	if (-Not (Test-Path $PYTHON_DIR)) {
		download $url $output
		echo ">>> Installing Python"
		# As the installation write some keys into regedit, we need to uninstlall Python before installing a new one.
		# If we do not do that, the next installation will be incomplete.
		# This issue will be resolved when using Python 3.
		#Start-Process msiexec -ArgumentList "/x `"$output`" /passive" -wait
		Start-Process msiexec -ArgumentList "/i `"$output`" /passive ALLUSERS=`"0`" ADDLOCAL=`"pip_feature`" REMOVE=`"Extensions`" TARGETDIR=`"$PYTHON_DIR`"" -wait
	}
}

function install_pyqt {
	$pyqt_version = "$Env:PYQT_VERSION"
	$output = "$STORAGE_DIR\PyQt4-$pyqt_version-gpl-Py2.7-Qt4.8.7-x32.exe"
	$url = "https://sourceforge.net/projects/pyqt/files/PyQt4/PyQt-$pyqt_version/PyQt4-$pyqt_version-gpl-Py2.7-Qt4.8.7-x32.exe"
	$packages = "$PYTHON_DIR\Lib\site-packages"
	$packages_pyqt = "$($packages)\PyQt4"
	$source = "$STORAGE_DIR\Lib\site-packages"
	$source_pyqt = "$STORAGE_DIR\Lib\site-packages\PyQt4"

	if (-Not (Test-Path $packages_pyqt)) {
		download $url $output

		Set-Location "$STORAGE_DIR"

		echo ">>> Installing PyQt $pyqt_version"
		& 7z x "$output" "Lib" -xr"!doc" -xr"!examples" -xr"!mkspecs" -xr"!sip" -y
		Copy-Item -Force "$source\sip.pyd" -Destination "$packages"
		Copy-Item -Recurse -Force "$source_pyqt\imports" -Destination "$packages_pyqt"
		Copy-Item -Recurse -Force "$source_pyqt\plugins" -Destination "$packages_pyqt"
		Copy-Item -Recurse -Force "$source_pyqt\uic" -Destination "$packages_pyqt"
		Copy-Item -Force "$source_pyqt\__init__.py" -Destination "$packages_pyqt"
		Copy-Item -Force "$source_pyqt\*.dll" -Destination "$packages_pyqt"
		Copy-Item -Force "$source_pyqt\*.pyd" -Destination "$packages_pyqt"

		# Remove useless modules
		Remove-Item -Recurse -Force "$packages_pyqt\plugins\designer"
		Remove-Item -Recurse -Force "$packages_pyqt\plugins\phonon_backend"
		Remove-Item -Force "$packages_pyqt\phonon*"
		Remove-Item -Force "$packages_pyqt\Qsci*"
		Remove-Item -Force "$packages_pyqt\QtDeclarative*"
		Remove-Item -Force "$packages_pyqt\QtDesigner*"
		Remove-Item -Force "$packages_pyqt\QtHelp*"
		Remove-Item -Force "$packages_pyqt\QtOpenGL*"
		Remove-Item -Force "$packages_pyqt\QtTest*"

		Set-Location "$Env:WORKSPACE_DRIVE"
	}
}

function install_cxfreeze {
	# Install cx_Freeze manually as pip does not work for this package
	$output = "$STORAGE_DIR\cx_Freeze-4.3.3.win32-py2.7.msi"
	$url = "https://sourceforge.net/projects/cx-freeze/files/4.3.3/cx_Freeze-4.3.3.win32-py2.7.msi"
	$packages_cxfreeze = "$PYTHON_DIR\Lib\site-packages\cx_Freeze"

	if (-Not (Test-Path $packages_cxfreeze)) {
		download $url $output
		echo ">>> Installing cx_Freeze"
		# Here we use the "/a" argument to prevent cx_Freeze to be listed in installed softwares
		Start-Process msiexec -ArgumentList "/a `"$output`" /passive TARGETDIR=`"$PYTHON_DIR`"" -wait
	}
}

function install_deps {
	echo ">>> Installing requirements"
	& $PYTHON_DIR\Scripts\pip install -q -t "$PYTHON_DIR" -r requirements.txt
	& $PYTHON_DIR\Scripts\pip install -q -t "$PYTHON_DIR" -r requirements-windows.txt
}

function check_qtwebkit {
	# Test if PyQt is installed and works
	& $PYTHON_DIR\python -c 'from PyQt4 import QtWebKit'
	if ($lastExitCode -ne 0) {
		echo ">>> Installation failed."
		ExitWithCode $lastExitCode
	}
}

function build_msi {
	# Build the famous MSI
	echo ">>> Building the MSI package"
	& $PYTHON_DIR\python setup.py --freeze bdist_msi

	# To implement with the new certificat
	# sign_msi
}

function launch_tests {
	# Launch the tests suite
	& $PYTHON_DIR\Scripts\pip install -q -t "$PYTHON_DIR" -r requirements-tests.txt
	& $PYTHON_DIR\python $PYTHON_DIR\pytest.py --showlocals --exitfirst --strict --failed-first -r Efx --full-trace --cache-clear --capture=sys --no-cov-on-fail --cov-report html:..\coverage --cov=nuxeo-drive-client\nxdrive nuxeo-drive-client\nxdrive
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function main {
	echo "    PYTHON_DRIVE_VERSION = $PYTHON_DRIVE_VERSION"
	echo "    PYQT_VERSION         = $Env:PYQT_VERSION"
	echo "    WORKSPACE            = $Env:WORKSPACE"
	echo "    WORKSPACE_DRIVE      = $Env:WORKSPACE_DRIVE"
	echo "    STORAGE_DIR          = $STORAGE_DIR"
	echo "    PYTHON_DIR           = $PYTHON_DIR"

	Set-Location "$Env:WORKSPACE_DRIVE"

	install_python
	install_pyqt
	install_cxfreeze
	install_deps
	check_qtwebkit

	if ($build) {
		build_msi
	} elseif ($tests) {
		launch_tests
	}
}

main
