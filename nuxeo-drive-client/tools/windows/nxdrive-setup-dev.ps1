# Powershell script: save on Desktop and Right Click "Run with PowerShell"

# Get ready to download and install dev tools from the web
$storagedir = "$pwd\nxdrive-tools"
mkdir $storagedir -ErrorAction SilentlyContinue
$webclient = New-Object System.Net.WebClient

# Download Git
#$url =
"https://github.com/downloads/msysgit/git/Git-1.7.11-preview20120620.exe"
#$git_installer = "$storagedir\Git-1.7.11-preview20120620.exe"
#echo "Downloading Git from $url"
#$webclient.DownloadFile($url, $git_installer)
#echo "Installing Git from $git_installer"
#& "$git_installer"

# Download Python
$url = "http://www.python.org/ftp/python/2.7.3/python-2.7.3.msi"
$python_msi = "$storagedir\python-2.7.3.msi"
echo "Downloading Python from $url"
$webclient.DownloadFile($url, $python_msi)
echo "Installing Python from $python_msi"
msiexec.exe /qn /I $python_msi


