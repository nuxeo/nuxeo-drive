# Nuxeo Drive

**Desktop Synchronization Client for Nuxeo**

This is an ongoing development project for desktop synchronization of local folders with remote Nuxeo workspaces.

Watch this [screencast](https://embedwistia-a.akamaihd.net/deliveries/db284a19e500781cdca15ecb0e5901d62154f084/file.mp4) to get a 6 min overview of this project.

See [USERDOC/Nuxeo Drive](https://doc.nuxeo.com/x/04HQ) for complete up-to-date documentation.

Note: this documentation follows the Drive version of the master branch, which could evolve rapidly. To see the documentation of a given Drive release, use this kind of link:

```shell
# For Drive 2.1.113 go to:
https://github.com/nuxeo/nuxeo-drive/tree/release-2.1.113
```

## License

The source code of Nuxeo Drive is available under the GNU LGPL v2.1 described in [LICENSE.txt](LICENSE.txt).

## Install

Installing Nuxeo Drive requires two components: the `nuxeo-drive` server addon for the Nuxeo Platform and a desktop program on the user's computer.

## Clients

### macOS and Windows Desktop Clients

Once the Marketplace package is installed, the macOS/Windows desktop client package can be downloaded from the **Home** > **Nuxeo Drive** tab or from the [update website](https://community.nuxeo.com/static/drive-updates/). Administrator rights are not required.

You can also fetch the latest development version from the [our Continous Integration server](https://qa.nuxeo.org/jenkins/view/Drive/job/Drive/job/Drive-packages/).

All the necessary dependencies (such as the Python interpreter and the Qt / PyQt for the client side user interface) are included and will not impact any alternative version you may have already installed on your computer.

### Debian based Distributions (and Other GNU/Linux Variants) Client

There is currently no universal package to download. In the meantime you can install it from the source code.

*Has been reported to work on* Ubuntu >= 12.04.

The easiest and safest way to build Drive is to follow the same steps as we do on [Jenkins](#jenkins).

Note that the `xclip` tool is needed for the clipboard copy/paste to work.

#### xattr

First note that Nuxeo Drive uses [Extended file attributes](https://en.wikipedia.org/wiki/Extended_file_attributes) through the [xattr](https://pypi.python.org/pypi/xattr/) Python wrapper.

On FreeBSD and macOS, xattrs are enabled in the default kernel.

On GNU/Linux, depending on the distribution, you may need a special mount option (`user_xattr`) to enable them for a given file system, e.g.:

```shell
sudo mount -o remount,user_xattr /dev/sda3
```

#### Python

Nuxeo Drive is officially supported on **Python 3.6+**.

#### Install Nuxeo Drive

Install Nuxeo Drive requirements and Nuxeo Drive itself.
These are common installation actions, not depending on the package manager.
From the folder containing the Nuxeo Drive source code (this repository):

```shell
git checkout "release-4.0.0"  # Or whatever release you want, starting with 4.0.0 and newer

export WORKSPACE="$(pwd)"
./tools/linux/deploy_jenkins_slave.sh --install
```

Then, when you want to launch Drive, simply type:

```shell
export WORKSPACE="$(pwd)"
./tools/linux/deploy_jenkins_slave.sh --start
```

### Jenkins

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

    * If you installed the .dmg package for macOS, the binary is:

    ```shell
    /Applications/Nuxeo\ Drive.app/Contents/MacOS/ndrive
    ```

    * You can alias it in your `~/.bashrc` with:

    ```shell
    alias ndrive="/Applications/Nuxeo\ Drive.app/Contents/MacOS/ndrive"
    ```

2. Launch Nuxeo Drive:

    ```shell
    ndrive
    ```

    Under Windows you can launch `ndrive.exe` instead to avoid keeping the cmd console open while Nuxeo Drive is running instead.

3. The first time you run this command a dialog window will open asking for the URL of the Nuxeo server and your user credentials.

    Alternatively you can bind to a Nuxeo server with your user credentials using the following commandline arguments:

    ```shell
    ndrive bind-server nuxeo-username https://server:port/nuxeo [--password="secret"] [--local-folder="~/Nuxeo Drive"]
    ```

    This will create a new folder called Nuxeo Drive in your home folder on GNU/Linux & macOS and under the Documents folder on Windows.

4. Go to your Nuxeo with your browser, navigate to workspaces or folder where you have permission to create new documents.
5. Click on the Nuxeo Drive icon right of the title of the folder to treat this folder as a new synchronization root.

    Alternatively you can do this operation from the commandline with:

    ```shell
    ndrive bind-root "/default-domain/workspaces/My Workspace"
    ```

    You can now create office documents and folders locally or inside Nuxeo and watch them getting synchronized both ways automatically.

## Localization

[![Crowdin](https://d322cqt584bo4o.cloudfront.net/nuxeo-drive/localized.svg)](https://crowdin.com/project/nuxeo-drive)

Translations are managed with [Crowdin](https://crowdin.com/).

The reference file [i18n.json](https://github.com/nuxeo/nuxeo-drive/blob/master/nxdrive/data/i18n/i18n.json) contains the labels and the English values.

Translations for other languages are managed in the [nuxeo-drive](https://crowdin.com/project/nuxeo-drive) Crowdin project, e.g. [French](https://crowdin.com/translate/nuxeo-drive/40/en-fr).

The [sync-nuxeo-drive-crowdin](https://qa.nuxeo.org/jenkins/job/Private/job/Crowdin/job/sync-nuxeo-drive-crowdin/) Jenkins job triggers a daily synchronization of:

* The i18n.json reference file to Crowdin. This file can be edited and changes must be pushed to the current repository.
* The Crowdin translation files to the i18n folder, e.g. i18n-fr.json. These files must never be edited from the source tree.

## Reporting Issues

1. Generate a bug report in the **Advanced** tab of the **Settings** panel of the Nuxeo Drive client.

    You can also log DEBUG information directly in the console by using the following command-line:

    ```shell
    ndrive --log-level-console=DEBUG
    ```

2. Create a GitHub issue mentionning the version of the Nuxeo Platform, your operating system name and version (e.g. Windows 7), the steps to reproduce the error and a copy of the logs.

3. For long running sessions, it is better to dump the debug information in a log file. This can be done with the following command:

    ```shell
    ndrive --log-level-file=DEBUG
    ```

    By default the location of the log file is: `~/.nuxeo-drive/logs/` where `~` stands for the location of the user folder. For instance:

    * GNU/Linux: `/home/username/.nuxeo-drive/logs`
    * macOS: `/Users/username/.nuxeo-drive/logs`
    * Windows: `C:\Users\username\.nuxeo-drive\logs`

## Roadmap

The [backlog](https://jira.nuxeo.com/issues/?jql=%28project%20%3D%20%22Nuxeo%20Drive%20%22%20OR%20component%20%3D%20%22Nuxeo%20Drive%22%20OR%20project%20%3D%20NXDOC%20AND%20Tags%20%3D%20drive%29%20AND%20resolution%20%3D%20Unresolved%20ORDER%20BY%20Rank%20ASC) is handled on JIRA.

## Developing on Nuxeo Drive

See the [contributor guide](DEVELOPERS.md) if you wish to actually contribute to the Nuxeo Drive code base.
