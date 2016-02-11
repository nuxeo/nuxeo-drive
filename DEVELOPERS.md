# Nuxeo Drive Contributor Guide

This guide is for developers willing to work on the Nuxeo Drive codebase itself.

Note that many behaviors of Nuxeo Drive can be customized without actually changing the code of Nuxeo Drive but by contributing to the server side extension points instead.

The projects comes into two parts: the addon deployed on the Nuxeo server, written in Java and the client written in Python.

Nuxeo Drive Client is a Python daemon that looks for changes on the local machine filesystem in a specific folder and on a remote workspace on the Nuxeo server using the Content Automation HTTP API and propagates those changes one way or the other.

This guide will introduce:

* How to build the Java components from source code
* How to set your developer environment to work on the client and run the tests
* How to freeze the client into self-hosted binaries packages (.msi and .dmg)

## Building the Server Addon

To build the nuxeo-drive addon see the related [nuxeo-drive-server](https://github.com/nuxeo/nuxeo-drive-server) GitHub repository.

To build the Marketplace package see the related [marketplace-drive](https://github.com/nuxeo/marketplace-drive) GitHub repository.

## Client-Side Architecture

![Nuxeo Drive architecture][nuxeo-drive-architecture-schema]
[nuxeo-drive-architecture-schema]: https://www.lucidchart.com/publicSegments/view/54e8e2a7-d2a4-4ec7-9843-5c740a00c10b/image.png

**CommandLine**

Handle the basic commandline arguments, create the Manager, and depending on the argument create a ConsoleApplication or Application.

**Manager**

Handle all the generic behavior of Nuxeo Drive: auto-updates, bind of an engine, declaration of differents engine types, tracker.

**Engine**

Handle one server synchronization, can be extend to customize the behavior, it creates all the synchronization structure: QueueManager, LocalWatcher, RemoteWatcher, DAO.

**DAO**

Abstraction for accessing the SQLite database, each Engine has its own DAO and so database

**LocalWatcher**


Handle the local scan on startup and then the FS events, updating the States stored in DAO, and if needed queueing the State to be processed

**RemoteWatcher**

Handle the remote scan for the first synchronization and then the incremental polling from the server

**QueueManager**

Handle the different types of Processor to process any remote or local modification

**RemoteFileProcessor**

Specialized thread in uploading document

**RemoteFolderProcessor**

Specialized thread in create remote folder

**LocalFileProcessor**

Specialized thread in download document

**LocalFolderProcessor**

Specialized thread in create local folder

**AdditionalProcessor**

If the queue is big, some additional Processor will be launch by the QueueManager to either download or upload document

**AppUpdater**

Handle the auto-update polling and the update download process

**Tracker**

Use for Analytics, anonymous report of usage

**ConsoleApplication**

Console behavior implementation

**Application**

OperatingSystem GUI handles the creation of windows, systray and message

**Translator**

Load labels translation and offer the translation service as static method

**WebDialog**

Base of all Nuxeo Drive window, it is basically a WebKit view with a Drive JavaScript object mapped by the JavaScript API

QT is heavily used in the new client. Here is a diagram of the signals/slots connections: 
![Signals/slots connections][signals-slots-connections]
[signals-slots-connections]: https://www.lucidchart.com/publicSegments/view/54efbff4-c180-41d8-9184-0b1d0a00c10b/image.png

RemoteWatcher logic schemas: [https://www.lucidchart.com/documents/view/3081771a-786b-486e-bfaa-ee7ae77a3807](https://www.lucidchart.com/documents/view/3081771a-786b-486e-bfaa-ee7ae77a3807)

LocalWatcher logic schemas: [https://www.lucidchart.com/documents/view/21ec315b-3917-44aa-b9bd-5ccedfcfb02f](https://www.lucidchart.com/documents/view/21ec315b-3917-44aa-b9bd-5ccedfcfb02f)

## Building the Nuxeo Drive Client

### Mac OS X Requirements

#### Compilation Tools

To be able to build the Nuxeo Drive client on Mac OS X, you must install your own non-system version of Python 2.7 using [Homebrew](https://github.com/Homebrew/homebrew).

First you need to install Xcode and its Command Line Tools as they are required for compilation with Homebrew.

Then make sure to update the formulae and Homebrew itself and to upgrade everything:

```
brew update && brew upgrade
```

#### OpenSSL Hack

Since Python 2.7.9, SSL verification is enabled by default. Unsurprisingly, it broke some Python scripts that connected to servers with self-signed certificates. Surprisingly, it broke scripts - among which the Nuxeo Drive one - that connected to servers with valid SSL certificates.

Why is that? Because the OpenSSL library as shipped with Mac OS X (which is still 0.9.8) has special hooks in it so that it falls back to OS X keyring if verification fails against the CAs given to OpenSSL itself, whereas the OpenSSL built with Homebrew does not have this fallback.

This means that if we use the built-in OpenSSL with python2 it will successfully verify the site if it finds a CA inside the OS X keyring. But if we compile python2 against our own OpenSSL it will look for the CAs in `/usr/local/etc/openssl/cert.pem` which is the location where Homebrew clones the system keyring when installing `openssl`. This would work on a dev environment with a Homebrew installation of `openssl` but not on a standard OS X machine!

Therefore we need to compile python with the OpenSSL library shipped with OS X, thus the following procedure. It is hackish but we haven't found a better way.

1. Make sure the system OpenSSL provided by Apple is installed.

        $ openssl version
        OpenSSL 0.9.8zf 19 Mar 2015

2. Install `openssl` with Homebrew.

        brew install openssl

3. Link the `openssl` installed with Homebrew to the system one.

        mv /usr/local/opt/openssl /usr/local/opt/openssl.brew
        ln -s /usr /usr/local/opt/openssl

For details about this "feature" of Mac OS X and the problems it introduces see this [great article](https://hynek.me/articles/apple-openssl-verification-surprises/).

Also see the related [JIRA issue](https://jira.nuxeo.com/browse/NXDRIVE-506).

#### Python Installation

Let's install Python with Homebrew.

Thanks to the previous step the system OpenSSL will be used as a dependency instead of the one installed with Homebrew.

    brew install python

This will install a new Python interpreter along with `pip` under `/usr/local/Cellar` and add publish it using symlinks in `/usr/local/bin` and `/usr/local/lib/python2.7`.

If you already have another version of [pip](http://www.pip-installer.org/) installed in `/usr/local/bin` you can force the overwrite the `/usr/local/bin/pip` with:

    brew link --overwrite python

Make sure that you are know using your newly installed version of Python / pip:

    $ export PATH=/usr/local/bin:$PATH
    $ which pip
    /usr/local/bin/pip
    $ which python
    /usr/local/bin/python

You can check the version of Python and OpenSSL with:

    $ python
    Python 2.7.11 (default, Dec 14 2015, 16:44:00) 
    [GCC 4.2.1 Compatible Apple LLVM 5.1 (clang-503.0.40)] on darwin
    Type "help", "copyright", "credits" or "license" for more information.
    >>> import ssl
    >>> ssl.OPENSSL_VERSION
    'OpenSSL 0.9.8y 5 Feb 2013'

### Installing Qt and PyQt

The graphical user interface elements of Nuxeo Drive client (such as the authentication prompt and the trayicon menu) are built using the PyQt library that is a Python binding for the Qt C++ library for building cross-platform interfaces. Beware that:

* Qt is available under both the LGPL and GPL
* PyQt is available either under the GPL or the PyQt commercial license. See [http://www.riverbankcomputing.co.uk/software/pyqt/license](http://www.riverbankcomputing.co.uk/software/pyqt/license) for more details about PyQt license.

When building/running Nuxeo Drive client from sources (i.e. not using the .msi or .dmg packages) you should have those libraries installed on your system.


#### Debian / Ubuntu

You can install the `python-qt4` package directly:

```
sudo apt-get install python-qt4
```

#### Mac OS X

Under OS X you can install Qt and PyQt using [Homebrew](https://github.com/Homebrew/homebrew).

First you need to make sure that the brew installed Python will be used when installing PyQt:

    export PATH=/usr/local/bin:$PATH

Then install PyQt following these steps:

1. Install qt

    Thanks to the previous step the system OpenSSL will be used as a dependency instead of the one installed with Homebrew.

        brew install qt

2. Install pyqt

    You need to remove the symlink used for the OpenSSL hack since it makes the installation of `pyqt` with Homebrew fail.

        rm /usr/local/opt/openssl
        mv /usr/local/opt/openssl.brew /usr/local/opt/openssl

        brew install pyqt

**Alternative methods**

* You can install PyQt from the sources downloaded at [http://sourceforge.net/projects/pyqt/files/PyQt4/PyQt-4.11.4/PyQt-mac-gpl-4.11.4.tar.gz](http://sourceforge.net/projects/pyqt/files/PyQt4/PyQt-4.11.4/PyQt-mac-gpl-4.11.4.tar.gz).

* You can also use MacPorts.

In this case and if you installed a standalone version of Python with Homebrew (recommended), you might need to symlink the binary install of PyQt to the site-packages folder of the brewed Python:

```
ln -s /Library/Python/2.7/site-packages/PyQt4 /usr/local/lib/python2.7/site-packages/PyQt4
```

#### Windows

Under Windows you need to install the binary package downloaded from the PyQt website:
[http://www.riverbankcomputing.co.uk/software/pyqt/download](http://www.riverbankcomputing.co.uk/software/pyqt/download)

**Notes**

* Make sure to install the version of the PyQt binaries matching with your version of Python, typically 2.7 for now as Python 3.3 is not yet supported by Nuxeo Drive.

* If you want to use your developer workstation to generate a frozen .msi build of the Nuxeo Drive client to be runnable on all Windows platforms (both 32 and 64 bit), be careful to install both the 32 bit versions of Python and PyQt.

### Setting up Your Build Environment

#### Linux

Grab all the dev dependencies and tools at once using [pip](http://www.pip-installer.org/):

```
pip install --user -r requirements.txt
pip install --user -r unix-requirements.txt
```
Run the Nuxeo Drive client from your source folder using the following settings:

```
export PYTHONPATH=`pwd`/nuxeo-drive-client
export PATH=`pwd`/nuxeo-drive-client/scripts:$PATH
```

You can persist this settings in your `.bashrc`.

You can safely ignore warnings about "Unknown distribution option: 'executables'".

To run the tests install and start a Nuxeo server locally, then:

```
. ./tools/posix/integration_env.sh
cd nuxeo-drive-client; nosetests nxdrive
```

#### Mac OS X

In case of problem about libffi while retrieving xattr (for exampe) during pip requirements installation, you might need to run this command and retry: `brew reinstall libffi`

Grab all the dev dependencies and tools at once using [pip](http://www.pip-installer.org/):

```
pip install --user -r requirements.txt
pip install --user -r unix-requirements.txt
pip install --user -r mac-requirements.txt
```

WARNING: This will download many large dependencies and sometimes the remote server will timeout on some of them. You might need to re-run this command several times to get it all installed.

Run the Nuxeo Drive client from your source folder using the following settings:

```
export PYTHONPATH=`pwd`/nuxeo-drive-client
export PATH=`pwd`/nuxeo-drive-client/scripts:$PATH
```

To run the tests, install and start a Nuxeo server locally, then:

```
. ./tools/posix/integration_env.sh
cd nuxeo-drive-client; nosetests nxdrive
```

#### Windows

To set up a build environment under Windows run the PowerShell script with the administration rights (right click on the PowerShell icon in the Programs menu to get the opportunity to "Run as administrator"):

```
powershell.exe C:\path\to\tools\windows\nxdrive-setup-dev.ps1
```

Some dependencies such as `psutil` can be tricky to build under Windows. You can use a binary installer from [this site](http://www.lfd.uci.edu/~gohlke/pythonlibs/).

If you get an error message complaining about the lack of signature for this script you can disable that security check with the following command:

```
Set-ExecutionPolicy Unrestricted
```

You can optionnally install the binary package for the `faulthandler` module that helps diagnostic segmentation faults by dumping the tracebacks of the Python threads on `stderr`:
[http://www.lfd.uci.edu/~gohlke/pythonlibs/#faulthandler](http://www.lfd.uci.edu/~gohlke/pythonlibs/#faulthandler)

If you fail to build it with pip and get the error: `error: Unable to find vcvarsall.bat` use the binary package.

You also need to install:

* The binary package for the `PyCrypto` module: [http://www.voidspace.org.uk/downloads/pycrypto26/pycrypto-2.6.win32-py2.7.exe](http://www.voidspace.org.uk/downloads/pycrypto26/pycrypto-2.6.win32-py2.7.exe)
* The binary package for the `pywin32` module: [http://sourceforge.net/projects/pywin32/files/pywin32/Build%20218/pywin32-218.win32-py2.7.exe/download](http://sourceforge.net/projects/pywin32/files/pywin32/Build%20218/pywin32-218.win32-py2.7.exe/download)

You can then run the integration tests against a Nuxeo instance running `localhost:8080` with:

```
.\tools\windows\integration_env.ps1
cd nuxeo-drive-client; nosetests nxdrive
```

## Generating OS Specific Packages

### Debian Package

Install the following required Debian packages:

```
sudo apt-get install dpkg-dev devscripts debhelper cdbs
```

To build the Nuxeo Drive Debian package run:

```
virtualenv ENV
. ENV/bin/activate
pip install -r requirements.txt
pip install -r unix-requirements.txt
mvn clean package -f pom-debian.xml
deactivate
```

### .app and .dmg Packages for Mac OS X

To generate the standalone OS X .app bundle, you need to install a standalone version of Python (i.e. not the version that comes pre-installed with OS X). Otherwise the .app bundle will be generated in semi-standalone mode and will likely not work on other versions of OS X. See the Mac OS X requirements section.

Then install py2app along with the dependencies:

```
pip install py2app
```

Generate the .app bundle by running:

```
python setup.py bdist_esky
```

The generated .app bundle can be found in the `dist/` subfolder. 

Now generate a .dmg archive by running:

```
sh tools/osx/create-dmg.sh
```

### .msi Package for Windows

To generate the Windows .msi installer, you need to install `cx_Freeze`. 

Then run:

```
C:\Python27\python.exe setup.py --freeze bdist_msi
```

The generated .msi file can be found in the `dist/` subfolder.

## Signing the Binary Packages

As OS X and Windows have some default security policies to only allow users to run software they have downloaded off the Internet if it has been signed, we need to sign the Nuxeo Drive binary packages. For an unsigned application, under Windows, users only need to click "Yes" in a various number of popups to get through the security check, but under OS X unless the Security & Privacy settings are changed or they right/Ctrl clik on the file, they simply won't be able to launch the application!

For a full documentation on application signing see [https://github.com/nuxeo/nuxeo-drive/blob/master/nuxeo-drive-client/doc/digital_signature.md](https://github.com/nuxeo/nuxeo-drive/blob/master/nuxeo-drive-client/doc/digital_signature.md)

### Mac OS X

You need to make sure to have a code signing identity trusted by Apple in one of the machine's keychain. Let's say its name is "Developer ID Application: NUXEO CORP (WCLR6985BX)".

Once the application bundle package has been generated by py2app, you only need to make sure the `SIGNING_IDENTITY` variable from the `create-dmg.sh` script is set with a substring of the code signing identity (unique throughout the keychains), in this case NUXEO CORP. The signing process will be done when generating the .dmg archive with:

```
sh tools/osx/create-dmg.sh
```

It will sign the DMG package and verify its signature. It uses the `codesign` and `spctl` commands included by default in Mac OS X.

### Windows

You need to make sure to have a valid PFX certificate file on the build machine, let's say it is located in `C:\Users\Nuxeo\certificates\nuxeo.com.pfx`.

Once the MSI package has been generated by `cx_Freeze`, run the following script, making sure the `CERTIFICATE_PATH` variable is pointing to the PFX certificate file, in this case "%USERPROFILE%\certificates\nuxeo.com.pfx":

```
.\tools\windows\sign_msi.bat
```

It will sign the MSI package and verify its signature. It uses the `signtool` command which is available as part of the [Windows SDK](http://msdn.microsoft.com/en-us/windowsserver/bb980924.aspx).

