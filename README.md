# Nuxeo Drive - Desktop Synchronization Client for Nuxeo

This is an ongoing development project for desktop synchronization of local folders with remote Nuxeo workspaces.

Watch this [screencast](http://www.nuxeo.com/blog/development/2013/04/nuxeo-drive-desktop-synchronization/) to get a 6 min overview of this project.

See [USERDOC/Nuxeo Drive](http://doc.nuxeo.com/x/04HQ) for complete up-to-date documentation.

## License

The source code of Nuxeo Drive is available under the GNU Lesser General Public License v2.1 described in LICENSE.txt.

Though, Nuxeo Drive depends on the [PyQt](http://www.riverbankcomputing.co.uk/software/pyqt/intro) component that is available under the following licenses:

* GNU General Public License v2
* GNU General Public License v3
* PyQt Commercial License
* PyQt Embedded License

Therefore the binary packages resulting of the assembly of the Nuxeo Drive source code and all the third-party libraries that it depends on, among which PyQt, are available under one of the licenses listed above. Indeed, the binary packages are subject to the licenses of the sources from which they have been built. As the GNU General Public Licenses and the PyQt Commercial License are stronger than the GNU Lesser General Public License, these are the ones that apply.

Thus any code written on the top of Nuxeo Drive must be distributed under the terms of one of the licenses available for PyQt.

## Install

Installing Nuxeo Drive requires two components: a server addon for the Nuxeo Platform and a desktop program on the user's computer.

## Server-Side Marketplace Package

### Getting the Marketplace Package

**Stable releases for Nuxeo Drive** are available as a Marketplace package from the Nuxeo Online Services portal: [https://connect.nuxeo.com/nuxeo/site/marketplace/package/nuxeo-drive](https://connect.nuxeo.com/nuxeo/site/marketplace/package/nuxeo-drive)

You can also fetch the **latest development version** of the [Marketplace package for the Nuxeo master branch](http://qa.nuxeo.org/jenkins/job/addons_nuxeo-drive-master-marketplace) from the Continuous Integration server (use at your own risk).

### Installing the Marketplace Package

The Marketplace package can be installed using the **Admin Center** / **Update Center** / **Local Packages** interface of a Nuxeo server.

Alternatively, from the command line:

```
$NUXEO_HOME/bin/nuxeoctl stop
$NUXEO_HOME/bin/nuxeoctl mp-install --nodeps marketplace-<version>.zip
$NUXEO_HOME/bin/nuxeoctl start
```

## Clients

### Ubuntu/Debian (and Other Linux Variants) Client

The .deb (or .rpm) package of the client is not yet available. In the mean time you can install it from source code.

*Has been reported to work on:* Ubuntu >= 12.04.

First note that Nuxeo Drive uses [Extended file attributes](http://en.wikipedia.org/wiki/Extended_file_attributes) through the [xattr](https://pypi.python.org/pypi/xattr/) Python wrapper.

On Linux, FreeBSD, and Mac OS X, xattrs are enabled in the default kernel.

On Linux, depending on the distribution, you may need a special mount option (`user_xattr`) to enable them for a given file system, e.g.:

```
sudo mount -oremount,user_xattr /dev/sda3
```

Then install the required system and Python packages:

Debian package manager:

```
sudo apt-get install python-pip python-dev python-qt4 libffi-dev git
```

Redhat package manager (RPM):

```
sudo yum install python-pip python-devel PyQt4 libffi-devel git
```

Make sure that the latest version of [pip](https://pip.pypa.io/en/stable/) is installed:

```
pip install -U pip
```

Then finally install the Nuxeo Drive requirements and Nuxeo Drive itself.
These are common installation actions, not depending on the package manager (warning: define the version you want in the DRIVE_VERSION variable, ex: 2.1.113):

```
DRIVE_VERSION=release-2.1.113
sudo pip install -U -r https://raw.github.com/nuxeo/nuxeo-drive/$DRIVE_VERSION/requirements.txt
sudo pip install -U -r https://raw.github.com/nuxeo/nuxeo-drive/$DRIVE_VERSION/unix-requirements.txt
sudo pip install -U git+https://github.com/nuxeo/nuxeo-drive.git@$DRIVE_VERSION
```

Waiting for [NXDRIVE-62](https://jira.nuxeo.com/browse/NXDRIVE-62) to be resolved you need to run these commands for Nuxeo Drive to work fine:

```
# increase inotify file watch limit
ofile=/proc/sys/fs/inotify/max_user_instances
sudo sh -c "echo 8192 > $ofile"
cat $ofile
```

### Mac OSX Desktop Client

Once the Marketplace package is installed, the Mac OS X desktop client package can be downloaded from the **Home** > **Nuxeo Drive** tab.

You can also fetch the latest development version for Mac OS X from the [our Continous Integration server](https://qa.nuxeo.org/jenkins/job/nuxeo-drive-dmg).

### Windows Desktop Client

Once the Marketplace package is installed, the Windows desktop client package can be downloaded from the **Home** > **Nuxeo Drive** tab.

You can also fetch the latest development version for nuxeo-drive-<version>-win32.msi Windows installer from [our Continuous Integration server](http://qa.nuxeo.org/jenkins/job/nuxeo-drive-msi/).

Once you installed the package (Administrator rights required) the new folder holding the ndrive.exe and ndrivew.exe programs will be added to your `Path` environment variable automatically.

You can start the Nuxeo Drive program from the "Start..." menu.

All the necessary dependencies (such as the Python interpreter and the QT / PyQt for the client side user interface) are included in this folder and should not impact any alternative version you may have already installed on your computer.


## Configuration and Usage

### Regular Usage

1. Launch the Nuxeo Drive program (e.g. from the Start menu under Windows).

	A new icon should open in the system tray and a popup menu should open asking the user for the URL of the Nuxeo server and credentials.

2. In the Nuxeo web interface, mark workspaces and folders for synchronization.

3. You can now go to the local Nuxeo Drive folder by using the menu of the system tray icon.

### Command-Line Usage (Advanced)

The desktop synchronization client can also be operated from the command-line:

1. Make sure that the `ndrive` program is installed in a folder that has been added to the `PATH` enviroment variable of your OS.

    * You can check by typing the `ndrive --help` command in a console.

    * If you installed the .dmg package for OSX, the binary is:
    
	```
    /Applications/Nuxeo\ Drive.app/Contents/MacOS/ndrive
	```
    
    * You can alias it in your `bashrc` with:
	
	```
    alias ndrive="/Applications/Nuxeo\ Drive.app/Contents/MacOS/ndrive"
	```
2. Launch Nuxeo Drive (no automatic background mode yet, this will come in future versions):

	```
    ndrive
	```  
    Under Windows you can launch ndrivew.exe instead to avoid keeping the cmd console open while Nuxeo Drive is running instead.

3. The first time you run this command a dialog window will open asking for the URL of the Nuxeo server and your user credentials.

    Alternatively you can bind to a Nuxeo server with your user credentials using the following commandline arguments:
    
	```
    ndrive bind-server nuxeo-username http://server:port/nuxeo --password secret
	```
    This will create a new folder called Nuxeo Drive in your home folder under Linux and MacOSX and under the Documents folder under Windows.

4. Go to your Nuxeo with your browser, navigate to workspaces or folder where you have permission to create new documents. 
5. Click on the Nuxeo Drive icon right of the title of the folder to treat this folder as a new synchronization root.

    Alternatively you can do this operation from the commandline with:
    
	```
    ndrive bind-root "/default-domain/workspaces/My Workspace"
	```
	You can now create office documents and folders locally or inside Nuxeo and watch them getting synchronized both ways automatically.

For more options, type:

```
ndrive --help
ndrive subcommand --help
```

## Reporting Issues

1. Generate a bug report in the **Advanced** tab of the **Settings** panel of the Nuxeo Drive client.

	You can also log DEBUG information directly in the console by using the following command-line:

	```
	ndrive --log-level-console=DEBUG
	```

2. Create a GitHub issue mentionning the version of the Nuxeo Platform, your operating system name and version (e.g. Windows 7), the steps to reproduce the error and a copy of the logs.

3. For long running sessions, it is better to dump the debug information in a log file. This can be done with the following command:

	```
	ndrive --log-level-file=DEBUG
	```

	or even:

	```
	ndrive --log-level-file=TRACE
	```

	By default the location of the log file is: `~/.nuxeo-drive/logs/` where `~` stands for the location of the user folder. For instance:

	* Under Windows 7 and 8: `C:\Users\username\.nuxeo-drive\logs`
	* Under Mac OS X: `/Users/username/.nuxeo-drive/logs`
	* Under Ubuntu (and other Linux variants): `/home/username/.nuxeo-drive/logs`

## Roadmap

The [backlog](https://jira.nuxeo.com/issues/?jql=%28project%20%3D%20%22Nuxeo%20Drive%20%22%20OR%20component%20%3D%20%22Nuxeo%20Drive%22%20OR%20project%20%3D%20NXDOC%20AND%20Tags%20%3D%20drive%29%20AND%20resolution%20%3D%20Unresolved%20ORDER%20BY%20Rank%20ASC) is handled on JIRA.

## Developing on Nuxeo Drive

See the [contributor guide](https://github.com/nuxeo/nuxeo-drive/blob/master/DEVELOPERS.md) if you wish to actually contribute to the Nuxeo Drive code base.
