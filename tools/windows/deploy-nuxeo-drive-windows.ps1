# Usage: powershell ".\deploy-nuxeo-drive-windows.ps1" VERSION
#
# Deploy script for Nuxeo Drive releases (not alpha, not beta, just official releases).
#
# Workflow:
#   - kill eventual running process
#   - uninstall any versions
#   - download the given version
#   - install the given version
#   - add a custom local config file
#
# Contributors:
#   - Mickaël Schoentgen <mschoentgen@nuxeo.com>
#
# History:
#
#   1.0.0 [2020-02-13]
#       - Initial version.
#
param([string]$version)

# Stop the execution on the first error
$ErrorActionPreference = "Stop"

# Global variables
$global:VERSION = "1.0.0"
$global:APP = "Nuxeo Drive"
$global:URL = "https://community.nuxeo.com/static/drive-updates/release/nuxeo-drive"
$global:TMPDIR = New-TemporaryFile | %{ mkdir $_-d }
$global:INSTALLER = "$global:TMPDIR\installer.exe"

# Import required for downloads
Import-Module BitsTransfer

function add_local_config($version) {
	# Add a custom config file (a backup is done)
	$conf = "$Env:UserProfile\.nuxeo-drive\config.ini"
	$data = "[DEFAULT]
env = managed

[managed]
channel = centralized
"

	if ($version -eq "4.4.0") {
		# On 4.4.0 we need to enforce client_version locally.
		# See https://jira.nuxeo.com/browse/NXDRIVE-2047 for details.
		$data = "${data}client_version = $version"
	}

	Write-Output ">>> Setting the centralized channel in the config file"

	if (Test-Path "$conf") {
		# Backup the current file, the user will have to merge old and new files manually
		Write-Output ">>> Backing up current $conf file, manual merge will be needed"
		Rename-Item -Path "$conf" -NewName "config.$(Get-Date -Format yyyy_MM_dd-HH_mm_ss).ini"
	}

	# Create the conf file
	[IO.File]::WriteAllLines($conf, $data)
}

function download($version) {
	# Download the installer.

	$url = "$global:URL-$version.exe"
	$try = 1

	while ($try -lt 6) {
		Write-Output ">>> [$try/5] Downloading $url"
		Write-Output "                   to $global:INSTALLER"
		Try {
			Start-BitsTransfer -Source $url -Destination $global:INSTALLER

			# Remove the confirmation due to "This came from another computer and migh
			# be blocked to help protect this computer"
			Unblock-File "$global:INSTALLER"
			return
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

function force_kill() {
	# Kill any running process.

	Write-Output ">>> Killing eventual processes"

	# Nuxeo Drive 3
	Get-Process -Name "ndrivew" -ErrorAction SilentlyContinue | Stop-Process -Force

	# Nuxeo Drive >= 4
	Get-Process -Name "ndrive" -ErrorAction SilentlyContinue | Stop-Process -Force
}

function install() {
	# Install the given version.
	Write-Output ">>> Installing $global:APP"

	#  "| Out-Null" is a trick to wait for the command to finish
	& "$global:INSTALLER" /verysilent | Out-Null
}

function uninstall() {
	# Remove installed version.

	$uninstallers = @(
		# Nuxeo Drive 3.1.0 and 3.1.1
		"$Env:UserProfile\AppData\Roaming\$global:APP\unins000.exe",
		# Nuxeo Drive 3.1.2 and newer
		"$Env:UserProfile\AppData\Local\$global:APP\unins000.exe"
	)
	foreach ($uninstaller in $uninstallers) {
		if (Test-Path "$uninstaller") {
			Write-Output ">>> Uninstaller found: $uninstaller"
			#  "| Out-Null" is a trick to wait for the command to finish
			& "$uninstaller" /verysilent | Out-Null
			Write-Output ">>> Uninstalled $app"
		}
	}
}

function main {
	# Entry point
	Write-Output "$global:APP deploy script, version $global:VERSION."
	Write-Output ""

	if (-Not "$version") {
		Write-Output 'Usage: powershell ".\deploy-nuxeo-drive-windows.ps1" VERSION (must be >= 4.4.0)'
		Write-Output 'Ex:    powershell ".\deploy-nuxeo-drive-windows.ps1" 4.4.0'
		ExitWithCode 1
	}

	Write-Output ">>> Deploying $global:APP $version ... "

	force_kill
	uninstall
	download "$version"
	install
	add_local_config "$version"

	# Clean-up
	Remove-Item -Path "$global:TMPDIR" -Force -Recurse

	Write-Output ">>> $global:APP $version successfully deployed!"
}

main
