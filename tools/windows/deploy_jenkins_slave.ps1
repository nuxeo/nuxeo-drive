# Usage: powershell ".\tools\windows\deploy_jenkins_slave.ps1" [ARG]
#
# Possible ARG:
#     -build: build the installer
#     -direct: no downloads, just run the tests suite
#     -start: start Nuxeo Drive
#     -tests: launch the tests suite
#
# See /docs/deployment.md for more informations.
param (
	[switch]$build = $false,
	[switch]$direct = $false,
	[switch]$start = $false,
	[switch]$tests = $false
)

# Stop the execution on the first error
$ErrorActionPreference = "Stop"

# Global variables
$global:PYTHON_OPT = "-E", "-s"
$global:PIP_OPT = "-m", "pip", "install", "--upgrade", "--upgrade-strategy=only-if-needed"
$global:SERVER = "https://nuxeo-jenkins-public-resources.s3.eu-west-3.amazonaws.com/drive"

function build_installer {
	# Build the installer
	$app_version = (Get-Content nuxeo-drive-client/nxdrive/__init__.py) -match "__version__" -replace "'", "" -replace "__version__ = ", ""

	Write-Output ">>> [$app_version] Freezing the application"
	& $Env:PYTHON_DIR\Scripts\pyinstaller ndrive.spec --noconfirm
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	Write-Output ">>> [$app_version] Building the installer"
	& $Env:ISCC_PATH\iscc /DMyAppVersion="$app_version" "tools\windows\setup.iss"
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function check_import($import) {
	# Check module import to know if it must be installed
	# i.e: check_import "from PyQt4 import QtWebKit"
	#  or: check_import "import cx_Freeze"
	& $Env:PYTHON_DIR\python $global:PYTHON_OPT -c $import
	if ($lastExitCode -eq 0) {
		return 1
	}
	return 0
}

function check_sum($file) {
	# Calculate the MD5 sum of the file to check its integrity
	$filename = (Get-Item $file).Name
	$checksums = "$Env:WORKSPACE_DRIVE\tools\checksums.txt"
	$md5 = (Get-FileHash "$file" -Algorithm MD5).Hash.ToLower()

	if ((Select-String "$md5  $filename" $checksums -ca).count -eq 1) {
		return 1
	}
	return 0
}

function check_vars {
	# Check required variables
	if (-Not ($Env:PYTHON_DRIVE_VERSION)) {
		Write-Output ">>> PYTHON_DRIVE_VERSION not defined. Aborting."
		ExitWithCode 1
	} elseif (-Not ($Env:PYQT_VERSION)) {
		Write-Output ">>> PYQT_VERSION not defined. Aborting."
		ExitWithCode 1
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
	if (-Not ($Env:SIP_VERSION)) {
		$Env:SIP_VERSION = "4.19.7"  # XXX: SIP_VERSION
	}
	if (-Not ($Env:QT_PATH)) {
		$Env:QT_PATH = "C:\Qt\4.8.7"
	}
	if (-Not (Test-Path "$Env:QT_PATH")) {
		Write-Output ">>> QT_PATH does not exist: $Env:QT_PATH. Aborting."
		ExitWithCode 1
	}
	if (-Not ($Env:MINGW_PATH)) {
		$Env:MINGW_PATH = "C:\mingw32"
	}
	if (-Not (Test-Path "$Env:MINGW_PATH")) {
		Write-Output ">>> MINGW_PATH does not exist: $Env:MINGW_PATH. Aborting."
		ExitWithCode 1
	}
	if (-Not ($Env:ISCC_PATH)) {
		$Env:ISCC_PATH = "C:\Program Files (x86)\Inno Setup 5"
	}
	if (-Not (Test-Path "$Env:ISCC_PATH")) {
		Write-Output ">>> ISCC does not exist: $Env:ISCC_PATH. Aborting."
		ExitWithCode 1
	}

	$Env:STORAGE_DIR = (New-Item -ItemType Directory -Force -Path "$($Env:WORKSPACE)\deploy-dir").FullName
	$Env:PYTHON_DIR = "$Env:STORAGE_DIR\drive-$Env:PYTHON_DRIVE_VERSION-python"

	Write-Output "    PYTHON_DRIVE_VERSION = $Env:PYTHON_DRIVE_VERSION"
	Write-Output "    PYQT_VERSION         = $Env:PYQT_VERSION"
	Write-Output "    SIP_VERSION          = $Env:SIP_VERSION"
	Write-Output "    WORKSPACE            = $Env:WORKSPACE"
	Write-Output "    WORKSPACE_DRIVE      = $Env:WORKSPACE_DRIVE"
	Write-Output "    STORAGE_DIR          = $Env:STORAGE_DIR"
	Write-Output "    PYTHON_DIR           = $Env:PYTHON_DIR"
	Write-Output "    QT_PATH              = $Env:QT_PATH"
	Write-Output "    MINGW_PATH           = $Env:MINGW_PATH"
	Write-Output "    ISCC_PATH            = $Env:ISCC_PATH"

	# Adjust the PATH for compilation tools
	$Env:Path = "$Env:QT_PATH\bin;$Env:MINGW_PATH\bin"

	Set-Location "$Env:WORKSPACE_DRIVE"

	if (-Not ($Env:SPECIFIC_TEST) -Or ($Env:SPECIFIC_TEST -eq "") -Or ($Env:SPECIFIC_TEST -eq "nuxeo-drive-client\tests")) {
		$Env:SPECIFIC_TEST = "nuxeo-drive-client\tests"
	} else {
		Write-Output "    SPECIFIC_TEST        = $Env:SPECIFIC_TEST"
		$Env:SPECIFIC_TEST = "nuxeo-drive-client\tests\$Env:SPECIFIC_TEST"
	}
}

function download($url, $output, [bool]$check=$true) {
	# Download one file and save its content to a given file name
	# $output must be an absolute path.
	$try = 1
	while ($try -lt 6) {
		if (Test-Path "$output") {
			if ($check -eq $false) {
				return
			} elseif (check_sum "$output") {
				return
			}
			Remove-Item -Force "$output"
		}
		Write-Output ">>> [$try/5] Downloading $url"
		Write-Output "                   to $output"
		Try {
			$curl = New-Object System.Net.WebClient
			$curl.DownloadFile($url, $output)
		} Catch {}
		$try += 1
		Start-Sleep -s 5
	}

	Write-Output ">>> Impossible to download $url (MD5 verification set to $check)"
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
		& $Env:PYTHON_DIR\python $global:PYTHON_OPT -m ensurepip -U --default-pip
		if ($lastExitCode -ne 0) {
			ExitWithCode $lastExitCode
		}
	}

	Write-Output ">>> Installing requirements"
	& $Env:PYTHON_DIR\python $global:PYTHON_OPT $global:PIP_OPT -r requirements.txt
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
	& $Env:PYTHON_DIR\python $global:PYTHON_OPT $global:PIP_OPT -r requirements-dev.txt
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function install_openssl {
	$src = "$Env:MINGW_PATH\opt\bin"

	if (-Not (Test-Path "$Env:WORKSPACE_DRIVE\tools\windows\libeay32.dll")) {
		echo ">>> Retrieving OpenSSL DLL: libeay32.dll"
		Copy-Item "$src\libeay32.dll" "$Env:WORKSPACE_DRIVE\tools\windows"
	}

	if (-Not (Test-Path "$Env:WORKSPACE_DRIVE\tools\windows\ssleay32.dll")) {
		echo ">>> Retrieving OpenSSL DLL: ssleay32.dll"
		Copy-Item "$src\ssleay32.dll" "$Env:WORKSPACE_DRIVE\tools\windows"
	}
}

function install_pyqt {
	$fname = "PyQt4_gpl_win-$Env:PYQT_VERSION"
	$url = "$global:SERVER/$fname.zip"
	$output = "$Env:STORAGE_DIR\$fname.zip"

	if (check_import "import PyQt4.QtWebKit") {
		return
	}

	Write-Output ">>> Installing PyQt $Env:PYQT_VERSION"

	download $url $output
	unzip "$fname.zip" $Env:STORAGE_DIR
	Set-Location "$Env:STORAGE_DIR\$fname"

	Write-Output ">>> [PyQt $Env:PYQT_VERSION] Configuring"
	& $Env:PYTHON_DIR\python $global:PYTHON_OPT configure-ng.py `
		--confirm-license `
		--no-designer-plugin `
		--no-docstrings `
		--no-python-dbus `
		--no-qsci-api `
		--no-tools `
		--sip="$Env:PYTHON_DIR\sip.exe" `
		--spec="win32-g++"

	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	Write-Output ">>> [PyQt $Env:PYQT_VERSION] Compiling"
	& mingw32-make -j 2
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	Write-Output ">>> [PyQt $Env:PYQT_VERSION] Installing"
	& mingw32-make install
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	Set-Location $Env:WORKSPACE_DRIVE
}

function install_python {
	$output = "$Env:STORAGE_DIR\python-$Env:PYTHON_DRIVE_VERSION.msi"
	$url = "https://www.python.org/ftp/python/$Env:PYTHON_DRIVE_VERSION/python-$Env:PYTHON_DRIVE_VERSION.msi"

	if (Test-Path "$Env:PYTHON_DIR\python.exe") {
		return
	}

	Write-Output ">>> Installing Python"
	download $url $output
	Start-Process msiexec -ArgumentList "/a `"$output`" /passive TARGETDIR=`"$Env:PYTHON_DIR`"" -wait
}

function install_sip {
	$fname = "sip-$Env:SIP_VERSION"
	$url = "$global:SERVER/$fname.zip"
	$output = "$Env:STORAGE_DIR\$fname.zip"

	if (check_import "import os, sip; os._exit(not sip.SIP_VERSION_STR == '$Env:SIP_VERSION')") {
		return
	}

	Write-Output ">>> Installing SIP $Env:SIP_VERSION"

	download $url $output
	unzip "$fname.zip" $Env:STORAGE_DIR
	Set-Location "$Env:STORAGE_DIR\$fname"

	Write-Output ">>> [SIP $Env:SIP_VERSION] Configuring"
	& $Env:PYTHON_DIR\python $global:PYTHON_OPT configure.py `
		--no-stubs `
		--platform="win32-g++"

	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	Write-Output ">>> [SIP $Env:SIP_VERSION] Compiling"
	& mingw32-make -j 2
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	Write-Output ">>> [SIP $Env:SIP_VERSION] Installing"
	& mingw32-make install
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}

	Set-Location $Env:WORKSPACE_DRIVE
}

function launch_tests {
	# Launch the tests suite
	if (!$direct) {
		& $Env:PYTHON_DIR\python $global:PYTHON_OPT $global:PIP_OPT -r requirements-tests.txt
		if ($lastExitCode -ne 0) {
			ExitWithCode $lastExitCode
		}
	}
	& $Env:PYTHON_DIR\python $global:PYTHON_OPT -m pytest $Env:SPECIFIC_TEST `
		--cov-report= `
		--cov=nuxeo-drive-client/nxdrive `
		--showlocals `
		--strict `
		--failed-first `
		--no-print-logs `
		--log-level=CRITICAL `
		-r fE `
		-W error `
		-v
	if ($lastExitCode -ne 0) {
		ExitWithCode $lastExitCode
	}
}

function start_nxdrive {
	# Start Nuxeo Drive
	$Env:PYTHONPATH = "$Env:WORKSPACE_DRIVE\nuxeo-drive-client"
	& $Env:PYTHON_DIR\python nuxeo-drive-client/nxdrive/commandline.py
}

function unzip($filename, $dest_dir) {
	# Uncompress a Zip file into a given directory.
	Write-Output ">>> Uncompressing $filename into $dest_dir"
	$options = 0x14  # overwrite and hide the dialog
	$shell = New-Object -com shell.application
	$src = $shell.NameSpace((Join-Path $dest_dir $filename))
	$dst = $shell.NameSpace((Join-Path $dest_dir ""))
	$dst.CopyHere($src.items(), $options)
}

function main {
	# Launch operations
	check_vars
	if (!$direct) {
		install_python
		install_deps
		install_sip
		install_pyqt
		install_openssl
	}

	if ((check_import "import PyQt4.QtWebKit") -ne 1) {
		Write-Output ">>> No WebKit. Installation failed."
		ExitWithCode 1
	}

	if ($build) {
		build_installer
	} elseif ($start) {
		start_nxdrive
	} elseif ($tests) {
		launch_tests
	}
}

main
