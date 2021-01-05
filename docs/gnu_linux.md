# GNU/Linux - Manual Usage

Nuxeo Drive can be installed from the source code.

The easiest and safest way to build Nuxeo Drive is to follow the same steps as we do on [Jenkins](#jenkins).

Note that the `xclip` tool is needed for the clipboard copy/paste to work.

## Binary

When you downloaded an official binary (file `.AppImage`), you will have to make it executable before being able to run it:

```shell
chmod a+x *.AppImage
```

## xattr

First note that Nuxeo Drive uses [Extended file attributes](https://en.wikipedia.org/wiki/Extended_file_attributes) through the [xattr](https://pypi.python.org/pypi/xattr/) Python wrapper.

Depending on the distribution, you may need a special mount option (`user_xattr`) to enable them for a given file system, e.g.:

```shell
sudo mount -o remount,user_xattr /dev/sda3
```

## Python

[//]: # (XXX_PYTHON)

Nuxeo Drive is officially supported on **Python 3.9.1+**.

## Installation

Install Nuxeo Drive requirements and Nuxeo Drive itself.
These are common installation actions, not depending on the package manager.
From the folder containing the Nuxeo Drive source code (this repository):

```shell
git checkout "release-4.2.0"  # Or whatever release you want, starting with 4.0.0 and newer

WORKSPACE="$(pwd)" ./tools/linux/deploy_ci_agent.sh --install-release
```

Then, when you want to launch Nuxeo Drive, simply type:

```shell
WORKSPACE="$(pwd)" ./tools/linux/deploy_ci_agent.sh --start
```

## Jenkins

To easily manage all dependencies and packaging steps, we created several Jenkinsfiles you can reuse.
They are located in the [tools/jenkins](https://github.com/nuxeo/nuxeo-drive/blob/master/tools/jenkins) folder.
You may also want to read the [deployment.md](https://github.com/nuxeo/nuxeo-drive/blob/master/docs/deployment.md).


## Docker

The process how to generate the official AppImage file can be found here: [Docker Usage](https://nuxeowiki.atlassian.net/wiki/spaces/DRIVE/pages/865403059/Docker+Usage).
