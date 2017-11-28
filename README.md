# Nuxeo Drive - Desktop Synchronization Client for Nuxeo

This is an ongoing development project for desktop synchronization of local folders with remote Nuxeo workspaces.

Watch this [screencast](https://embedwistia-a.akamaihd.net/deliveries/db284a19e500781cdca15ecb0e5901d62154f084/file.mp4) to get a 6 min overview of this project.

See [USERDOC/Nuxeo Drive](http://doc.nuxeo.com/x/04HQ) for complete up-to-date documentation.

Note: this documentation follows the Drive version of the master branch, which could evolve rapidly. To see the documentation of a given Drive release, use this kind of link:

    # For Drive 2.1.113 go to:
    https://github.com/nuxeo/nuxeo-drive/release-2.1.113/README.md


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

You can also fetch the **latest development version** of the [Marketplace package for the Nuxeo master branch](http://qa.nuxeo.org/jenkins/job/master/job/addons_nuxeo-drive-master-marketplace) from the Continuous Integration server (use at your own risk).

### Installing the Marketplace Package

The Marketplace package can be installed using the **Admin Center** / **Update Center** / **Local Packages** interface of a Nuxeo server.

Alternatively, from the command line:

    $NUXEO_HOME/bin/nuxeoctl stop
    $NUXEO_HOME/bin/nuxeoctl mp-install --nodeps marketplace-<version>.zip
    $NUXEO_HOME/bin/nuxeoctl start

## Clients

### Debian based Distributions (and Other GNU/Linux Variants) Client

The .deb (or .rpm) package of the client is not yet available. In the meantime you can install it from source code.

*Has been reported to work on* Ubuntu >= 12.04.

The easiest and safest way to build Drive is to follow the same steps as we do on [Jenkins](#jenkins).

#### xattr

First note that Nuxeo Drive uses [Extended file attributes](http://en.wikipedia.org/wiki/Extended_file_attributes) through the [xattr](https://pypi.python.org/pypi/xattr/) Python wrapper.

On FreeBSD and macOS, xattrs are enabled in the default kernel.

On GNU/Linux, depending on the distribution, you may need a special mount option (`user_xattr`) to enable them for a given file system, e.g.:

    sudo mount -o remount,user_xattr /dev/sda3

#### Python

Nuxeo Drive is officially supported on **Python 2.7 only**.

#### Install Nuxeo Drive

Let's say you have installed Qt4 (from official repository or compiled manually), then install Nuxeo Drive requirements and Nuxeo Drive itself.
These are common installation actions, not depending on the package manager:

    # For Drive < 2.2.227:
    DRIVE_VERSION=release-2.1.113
    pip install -r https://raw.github.com/nuxeo/nuxeo-drive/$DRIVE_VERSION/requirements.txt
    pip install -r https://raw.github.com/nuxeo/nuxeo-drive/$DRIVE_VERSION/unix-requirements.txt
    pip install git+https://github.com/nuxeo/nuxeo-drive.git@$DRIVE_VERSION

    # For Drive >= 2.2.227:
    DRIVE_VERSION=release-2.2.323
    pip install -r https://raw.github.com/nuxeo/nuxeo-drive/$DRIVE_VERSION/requirements.txt
    pip install -r https://raw.github.com/nuxeo/nuxeo-drive/$DRIVE_VERSION/requirements-unix.txt
    pip install git+https://github.com/nuxeo/nuxeo-drive.git@$DRIVE_VERSION


### macOS and Windows Desktop Clients

Once the Marketplace package is installed, the macOS/Windows desktop client package can be downloaded from the **Home** > **Nuxeo Drive** tab. Administrator rights are required.

You can also fetch the latest development version from the [our Continous Integration server](https://qa.nuxeo.org/jenkins/view/Drive/job/Drive/job/Drive-packages/).

All the necessary dependencies (such as the Python interpreter and the Qt / PyQt for the client side user interface) are included and will not impact any alternative version you may have already installed on your computer.

### Jenkins

*Since Drive 2.2.227* 

To easily manage all dependencies and packaging steps, we created several Jenkinsfiles you can reuse. They are located in the **tools/jenikins** folder. You may also want to read the [docs/deployment.md](https://github.com/nuxeo/nuxeo-drive/blob/master/docs/deployment.md).

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
    Under Windows you can launch `ndrivew.exe` instead to avoid keeping the cmd console open while Nuxeo Drive is running instead.

3. The first time you run this command a dialog window will open asking for the URL of the Nuxeo server and your user credentials.

    Alternatively you can bind to a Nuxeo server with your user credentials using the following commandline arguments:

    ```
    ndrive bind-server nuxeo-username http://server:port/nuxeo --password secret
    ```
    This will create a new folder called Nuxeo Drive in your home folder on GNU/Linux & macOS and under the Documents folder on  Windows.

4. Go to your Nuxeo with your browser, navigate to workspaces or folder where you have permission to create new documents.
5. Click on the Nuxeo Drive icon right of the title of the folder to treat this folder as a new synchronization root.

    Alternatively you can do this operation from the commandline with:

    ```
    ndrive bind-root "/default-domain/workspaces/My Workspace"
    ```
    You can now create office documents and folders locally or inside Nuxeo and watch them getting synchronized both ways automatically.

For more options, type:

    ndrive --help
    ndrive subcommand --help

### Building pip Package

This is as simple as:

    python setup.py sdist

On macOS you can face an issue with your locale with a message like:

    ValueError: unknown locale: UTF-8

In that case you need to specify your locale as :

    export LC_ALL=en_US.UTF-8
    export LANG=en_US.UTF-8

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
    * Under macOS: `/Users/username/.nuxeo-drive/logs`
    * Under Ubuntu (and other GNU/Linux variants): `/home/username/.nuxeo-drive/logs`

## Roadmap

The [backlog](https://jira.nuxeo.com/issues/?jql=%28project%20%3D%20%22Nuxeo%20Drive%20%22%20OR%20component%20%3D%20%22Nuxeo%20Drive%22%20OR%20project%20%3D%20NXDOC%20AND%20Tags%20%3D%20drive%29%20AND%20resolution%20%3D%20Unresolved%20ORDER%20BY%20Rank%20ASC) is handled on JIRA.

## Developing on Nuxeo Drive

See the [contributor guide](DEVELOPERS.md) if you wish to actually contribute to the Nuxeo Drive code base.
