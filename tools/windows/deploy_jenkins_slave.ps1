# Usage: powershell ".\tools\windows\deploy_jenkins_slave.ps1" [ARGS]
#
# Handle CLI arguments
#     -build: build the MSI package
param ([switch]$build = $false)

# Stop the execution on the fisrt error
$ErrorActionPreference = "Stop"

# Properties defined outside this script
$AppProps = convertfrom-stringdata(get-content tools\python_version)
$PYTHON_DRIVE_VERSION = $AppProps."PYTHON_DRIVE_VERSION"

# Global variables
if (-Not ($Env:WORKSPACE)) {
    $Env:WORKSPACE = $pwd
}
$STORAGE_DIR = (New-Item -ItemType Directory -Force -Path "$($Env:WORKSPACE)\deploy-dir").FullName
$PYTHON_DIR = "$STORAGE_DIR\drive-$PYTHON_DRIVE_VERSION-python"
$VENV = "$STORAGE_DIR\drive-$PYTHON_DRIVE_VERSION-venv"

function download($url, $output) {
	# Download one file and save its content to a given file name
	echo ">>> Downloading $url"
	echo "             to $output"
	$curl = New-Object System.Net.WebClient
	$curl.DownloadFile($url, $output)
}

function install_python {
	# Install Python
	$output = "$STORAGE_DIR\python-$PYTHON_DRIVE_VERSION.msi"
	$url = "https://www.python.org/ftp/python/$PYTHON_DRIVE_VERSION/python-$PYTHON_DRIVE_VERSION.msi"

	download $url $output
	echo ">>> Installing Python"
	# As the installation write some keys into regedit, we need to uninstlall Python before installing a new one.
	# If we do not do that, the next installation will be incomplete.
	# This issue will be resolved when using Python 3.
	Start-Process msiexec -ArgumentList "/x `"$output`" /passive" -wait
	Start-Process msiexec -ArgumentList "/i `"$output`" /passive ADDLOCAL=`"pip_feature`" TARGETDIR=`"$PYTHON_DIR`"" -wait
}

function install_pyqt4 {
	# Install PyQt4 + QtWebKit
	$output = "$STORAGE_DIR\PyQt4-4.11.4-gpl-Py2.7-Qt4.8.7-x32.exe"
	$url = "https://sourceforge.net/projects/pyqt/files/PyQt4/PyQt-4.11.4/PyQt4-4.11.4-gpl-Py2.7-Qt4.8.7-x32.exe/download"
	$packages = "$PYTHON_DIR\Lib\site-packages"
	$packages_pyqt = "$($packages)\PyQt4"

	download $url $output
	echo ">>> Installing PyQt4"
	& 7z x "$output" "Lib" "`$_OUTDIR" -xr"!doc" -xr"!examples" -xr"!mkspecs" -xr"!sip" -o"$STORAGE_DIR" -y
	Copy-Item "$STORAGE_DIR\Lib\site-packages\sip.pyd" "$packages" -Force
	Copy-Item "$STORAGE_DIR\Lib\site-packages\PyQt4\imports" "$packages_pyqt" -Recurse -Force
	Copy-Item "$STORAGE_DIR\Lib\site-packages\PyQt4\plugins" "$packages_pyqt" -Recurse -Force
	Copy-Item "$STORAGE_DIR\Lib\site-packages\PyQt4\__init__.py" "$packages_pyqt" -Force
	Copy-Item "$STORAGE_DIR\Lib\site-packages\PyQt4\*.dll" "$packages_pyqt" -Force
	Copy-Item "$STORAGE_DIR\`$_OUTDIR\uic" "$packages_pyqt" -Recurse -Force
	Copy-Item "$STORAGE_DIR\`$_OUTDIR\*.pyd" "$packages_pyqt" -Force
}

function install_cxfreeze {
	# Install cx_Freeze manually as pip does not work for this package
	$output = "$STORAGE_DIR\cx_Freeze-4.3.3.win32-py2.7.msi"
	$url = "https://sourceforge.net/projects/cx-freeze/files/4.3.3/cx_Freeze-4.3.3.win32-py2.7.msi/download"
	$packages_cxfreeze = "$PYTHON_DIR\Lib\site-packages\cx_Freeze"

	download $url $output
	echo ">>> Installing cx_Freeze"
	# Here we use the "/a" argument to prevent cx_Freeze to be listed in installed softwares
	Start-Process msiexec -ArgumentList "/a `"$output`" /passive TARGETDIR=`"$PYTHON_DIR`"" -wait
}

function activate_venv {
	echo ">>> Activating the virtualenv"
	& $VENV\Scripts\activate.ps1
}

function setup_venv {
	# Setup virtualenv
	echo ">>> Installing the virtualenv"
	& $PYTHON_DIR\Scripts\pip install virtualenv
	& $PYTHON_DIR\Scripts\virtualenv -p "$PYTHON_DIR\python.exe" --system-site-packages --always-copy $VENV
	activate_venv
	pip install -r requirements.txt
	pip install -r windows-requirements.txt
}

function check_qtwebkit {
	# Test if PyQt4.QtWebKit is installed and works
	python -c 'from PyQt4 import QtWebKit'
	if ($lastExitCode -eq 0) {
		echo ">>> Installation success!"
	} else {
		echo ">>> Installation failed."
		exit
	}
}

function build_msi {
    # Build the famous MSI
    echo ">>> Building the MSI package"
    python setup.py --freeze bdist_msi
}

function main {
	echo "    STORAGE_DIR = $STORAGE_DIR"
	echo "    PYTHON_DIR  = $PYTHON_DIR"
	echo "    VENV        = $VENV"

	install_python
	install_pyqt4
	install_cxfreeze
	setup_venv
	check_qtwebkit
	if ($build) {
		build_msi
		# To implement with the new certificat
		# sign_msi
	}
}

main
