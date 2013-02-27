# Powershell script: save on Desktop and Right Click "Run with PowerShell"

# Get ready to download and install dev tools from the web
$storagedir = "$pwd\nxdrive-downloads"
mkdir $storagedir -ErrorAction SilentlyContinue
$webclient = New-Object System.Net.WebClient

# Download Git
#$url = "https://github.com/downloads/msysgit/git/Git-1.7.11-preview20120620.exe"
#$git_installer = "$storagedir\Git-1.7.11-preview20120620.exe"
#echo "Downloading Git from $url"
#$webclient.DownloadFile($url, $git_installer)
#echo "Installing Git from $git_installer"
#& "$git_installer"
Set-Item -path env:Path -value ($env:Path + ";C:\Program Files (x86)\Git\bin")

# Download Python
$url = "http://www.python.org/ftp/python/2.7.3/python-2.7.3.msi"
$python_msi = "$storagedir\python-2.7.3.msi"
echo "Downloading Python from $url"
$webclient.DownloadFile($url, $python_msi)
echo "Installing Python from $python_msi"
msiexec.exe /qn /I $python_msi
# Add the python interpreter and scripts to the path
Set-Item -path env:Path -value ($env:Path + ";C:\Python27;C:\Python27\Scripts;")

# Install setuptools and pip
$url = "http://peak.telecommunity.com/dist/ez_setup.py"
$ez_setup = "$storagedir\ez_setup.py"
echo "Downloading Python from $url"
$webclient.DownloadFile($url, $ez_setup)
echo "Installing Setuptools from $ez_setup"
python $ez_setup
echo "Installing pip"
easy_install pip

# Install cx_Freeze manually as pip does not work for this package
$url = "http://downloads.sourceforge.net/project/cx-freeze/4.3/cx_Freeze-4.3.win32-py2.7.msi?r=http%3A%2F%2Fcx-freeze.sourceforge.net%2F&ts=1342189378&use_mirror=dfn"
$cx_freeze = "$storagedir\cx_Freeze-4.3.win32-py2.7.msi"
echo "Downloading cx_Freeze from $url"
$webclient.DownloadFile($url, $cx_freeze)
echo "Installing cx_Freeze from $cx_freeze"
msiexec.exe /qn /I $cx_freeze

echo "You can now clone the nuxeo-drive repo:"
echo "git clone https://github.com/nuxeo/nuxeo-drive.git"
echo ""
echo "Then install the developer dependencies:"
echo "pip install -r nuxeo-drive/requirements.txt"
