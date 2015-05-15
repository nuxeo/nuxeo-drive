Nuxeo Drive contributor guide
=============================

This guide is for developers willing to work on the Nuxeo Drive codebase itself.

For more details please read the technical documentation available here:

  http://doc.nuxeo.com/x/TYzZ

Note that many behaviors of Nuxeo Drive can be customized without actually
changing the code of Nuxeo Drive but by contributing to the server side
extension points instead.

The projects comes into two parts: the addon deployed on the Nuxeo server,
written in Java and the client written in Python.

Nuxeo Drive Client is a Python daemon that looks for changes on the local
machine filesystem in a specific folder and on a remote workspace on the Nuxeo
server using the Content Automation HTTP API and propagate those changes one way
of the other.

This guide will introduce:

- how to build the java components from source
- how to set your developer environment to work on the client and run the tests
- how to freeze the client into self-hosted binaries packages (.msi and .dmg)


Server side Java components
---------------------------

To build the project and run the tests, use maven::

  mvn install

To build the marketplace package see the related
`Github repository <https://github.com/nuxeo/marketplace-drive>`_.


Client side Architecture
------------------------
.. image:: https://www.lucidchart.com/publicSegments/view/54e8e2a7-d2a4-4ec7-9843-5c740a00c10b/image.png

CommandLine
  Handle the basic commandline arguments, create the Manager, and depending on the argument create a ConsoleApplication or Application.
  
Manager
  Handle all the generic behavior of Nuxeo Drive: auto-updates, bind of an engine, declaration of differents engine types, tracker.

Engine
  Handle one server synchronization, can be extend to customize the behavior, it create all the synchronization structure: QueueManager, LocalWatcher, RemoteWatcher, DAO.

DAO
  Abstraction for accessing the SQLite database, each Engine has its own DAO and so database

LocalWatcher
  Handle the local scan on startup and then the FS events, updating the States stored in DAO, and queueing if needed the State to be processed

RemoteWatcher
  Handle the remote scan for the first synchronization and then the incremental polling from the server

QueueManager
  Handle the different types of Processor to process any remote or local modification

RemoteFileProcessor
  Specialized thread in uploading document

RemoteFolderProcessor
  Specialized thread in create remote folder

LocalFileProcessor
  Specialized thread in download document

LocalFolderProcessor
  Specialized thread in create local folder

AdditionalProcessor
  If the queue is big, some additional Processor will be launch by the QueueManager to either download or upload document

AppUpdater
  Handle the auto-update polling and the update download process

Tracker
  Use for Analytics, anonymous report of usage

ConsoleApplication
  Console behavior implementation
  
Application
  OperatingSystem GUI handle the creation of windows, systray and message

Translator
  Load labels translation and offer the translation service as static method

WebDialog
  Base of all Nuxeo Drive window, it is basically a WebKit view with a drive javascript object mapped by the Javascript API

QT is heavily used in the new client here is a diagram of the signals/slots connexions : https://www.lucidchart.com/publicSegments/view/54efbff4-c180-41d8-9184-0b1d0a00c10b/image.png
Remote Watcher logic : https://www.lucidchart.com/invitations/accept/8dbb7a33-dc61-496c-89db-8914e57ed08e
Local Watcher logic : https://www.lucidchart.com/invitations/accept/8f6b478e-e066-4a92-bf5f-2c8de39b8221

Nuxeo Drive Client under Linux & Mac OS X
-----------------------------------------

**Under OS X**: before installing Python packages, you should probably start by
installing your own non-system version of Python 2.7 using homebrew as explained
in a dedicated section below.

Use pip_ to grab all the dev dependencies and tools at once::

  pip install --user -r requirements.txt
  pip install --user -r unix-requirements.txt
  pip install --user -r mac-requirements.txt		# OS X only

To run the Nuxeo Drive client from your source folder use the following settings::

  export PYTHONPATH=`pwd`/nuxeo-drive-client
  export PATH=`pwd`/nuxeo-drive-client/scripts:$PATH

You can persist this settings in your ``.bashrc``.

You can safely ignore warnings about "Unknown distribution option: 'executables'".

To run the tests, install and start a nuxeo server locally, then::

  . ./tools/posix/integration_env.sh
  cd nuxeo-drive-client; nosetests nxdrive

.. _pip: http://www.pip-installer.org/

**Under OS X** you can also optionally install ``PyObjC`` to get the
``LaunchServices`` API for registering the Nuxeo Drive folder in the OS X
Finder favorite list (a.k.a. "Places")::

  pip install PyObjC

WARNING: this will download many large dependencies and sometimes the remote
server will timeout on some of them: you might need to re-run this command
several times to get it all installed.

Then install Qt and PyQt for graphical user interface (see below).

**Under OS X** you need to install ``PyCrypto`` used for the HTTP proxy password encryption::

  easy_install PyCrypto


Nuxeo Drive Client under Windows
--------------------------------

To setup a build environment under Windows you can run the powershell
script with the administration rights (right click on the powershell
icon in the programs menu to get the opportunity to "Run as
administrator")::

  powershell.exe C:\path\to\tools\windows\nxdrive-setup-dev.ps1

Some dependencies such as `psutil` can be tricky to build under windows.  You
can use a binary installer from `this site
<http://www.lfd.uci.edu/~gohlke/pythonlibs/>`_.

If you get an error message complaining about the lack of signature
for this script you can disable that security check with the following
command::

  Set-ExecutionPolicy Unrestricted

Then install Qt and PyQt for graphical user interface (see below).

You can then run the integration tests against a Nuxeo instance running
``localhost:8080`` with::

  .\tools\windows\integration_env.ps1
  cd nuxeo-drive-client; nosetests nxdrive

You can optionnally install the binary package for the faulthandler module
that helps diagnostic segmentation faults by dumping the tracebacks of the
Python threads on ``stderr``:

  http://www.lfd.uci.edu/~gohlke/pythonlibs/#faulthandler

Using the binary package is a good workaround if you fail to build it with
pip and getting the error: ``error: Unable to find vcvarsall.bat``

You also need to install:

- The binary package for the ``PyCrypto`` module

  http://www.voidspace.org.uk/downloads/pycrypto26/pycrypto-2.6.win32-py2.7.exe

- The binary package for the ``pywin32`` module

  http://sourceforge.net/projects/pywin32/files/pywin32/Build%20218/pywin32-218.win32-py2.7.exe/download


Debian package
--------------

**Prerequisite**: install the following Debian packages::

  sudo apt-get install dpkg-dev devscripts debhelper cdbs

To build the Nuxeo Drive Debian package run::

  virtualenv ENV
  . ENV/bin/activate
  pip install -r requirements.txt
  pip install -r unix-requirements.txt
  mvn clean package -f pom-debian.xml
  deactivate


Installing Qt and PyQt
----------------------

The graphical user interface elements of Nuxeo Drive client (such as the
authentication prompt and the trayicon menu) are built using the PyQt library
that is a Python binding for the Qt C++ library for building cross-platform
interfaces. Beware that:

- Qt is available under both the LGPL and GPL
- PyQt is available either under the GPL or the PyQt commercial license. See `http://www.riverbankcomputing.co.uk/software/pyqt/license` for more details about PyQt license.

When building/running Nuxeo Drive client from sources (i.e. not using the
``.msi`` or ``.dmg`` packages) you should have those libraries installed on your system.

Under Windows
~~~~~~~~~~~~~

Under Windows you need to install the binary package downloaded from the PyQt website:

  http://www.riverbankcomputing.co.uk/software/pyqt/download

Make sure to install the version of the PyQt binaries matching with your
version of Python, typically 2.7 for now as Python 3.3 is not yet supported by
Nuxeo Drive.

Also if you want to use your developer workstation to generate a frozen `.msi`
build of the Nuxeo Drive client to be runnable on all windows platforms (both 32
and 64 bit), be careful to install both the 32 bit versions of Python and PyQt.


Under Mac OS X
~~~~~~~~~~~~~~

Under OS X you can install Qt and PyQt using Homebrew.

First you need to make sure that the brew installed Python will be used when installing PyQt::

  #Override default tools with Cellar ones if available
  #This makes sure homebrew stuff is used
  export PATH=/usr/local/bin:$PATH

  #Point OSX to Cellar python
  export PYTHONPATH=/usr/local/lib/python2.7:$PYTHONPATH

Then install PyQt with Homebrew::

  brew install pyqt

In this case and if you installed a standalone version of Python with Homebrew (recommended), you
might need to symlink the binary install of PyQt to the ``site-packages``
folder of the brewed Python::

  ln -s /Library/Python/2.7/site-packages/PyQt4 /usr/local/lib/python2.7/site-packages/PyQt4

As an alternative method, you can install PyQt from the sources downloaded at:

  http://sourceforge.net/projects/pyqt/files/PyQt4/PyQt-4.10.2/PyQt-mac-gpl-4.10.2.tar.gz

following the documentation at:

  http://pythonschool.net/mac_pyqt

or using MacPorts following the documentation at:

  http://pythonschool.net/cxfreeze_mac


Under Debian / Ubuntu
~~~~~~~~~~~~~~~~~~~~~

You can install the ``python-qt4`` package directly::

  sudo apt-get install python-qt4


Generating OS specific packages
-------------------------------

.msi package for Windows
~~~~~~~~~~~~~~~~~~~~~~~~

To generate the **Windows** ``.msi`` installer, you need to install ``cx_Freeze``
as explained above. Then run::

  C:\Python27\python.exe setup.py --freeze --dev bdist_msi

The generated ``.msi`` file can be found in the ``dist/`` subfolder.

.app and .dmg packages for Mac OS X
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To generate the standalone OS X `.app` bundle, you **need** to install a
standalone version of Python (i.e. not the version that comes pre-installed
with OS X). Otherwise the ``.app`` bundle will be generated in
``semi-standalone`` mode and will likely not work on other versions of OS X.

To install you a standalone version of Python with Homebrew see the dedicated
section below first.

Then install ``py2app`` along with the dependencies::

  pip install py2app
  pip install --user -r requirements.txt
  pip install --user -r unix-requirements.txt
  pip install --user -r mac-requirements.txt

Then run::

  python setup.py py2app --dev

The generated ``.app`` bundle can be found in the ``dist/`` subfolder. You
can then generate a ``.dmg`` archive running::

  sh tools/osx/create-dmg.sh


Installing a standalone Python interpreter on Mac OS X
------------------------------------------------------

To install a standalone version of Python under OS X you can use `Homebrew
<https://github.com/Homebrew/homebrew>`_.

First you need to install Xcode and its Command Line Tools as they are required for compilation with Homebrew.

Then make sure to update the formulae and Homebrew itself and to upgrade everything::

  brew update && brew upgrade

Finally install Python::

  brew install python

This will install a new Python interpreter along with ``pip`` under
``/usr/local/Cellar`` and add publish it using symlinks in ``/usr/local/bin``
and ``/usr/local/lib/python2.7``.

If you already have another version of pip installed in ``/usr/local/bin`` you
can force the overwrite the ``/usr/local/bin/pip`` with::

  brew link --overwrite python

Make sure that you are know using your newly installed version of python / pip::

  $ export PATH=/usr/local/bin:$PATH
  $ which pip
  /usr/local/bin/pip
  $ which python
  /usr/local/bin/python


Signing the binary packages
---------------------------

As OS X and Windows have some default security policies to only allow users to run software they have downloaded off the Internet if it has been signed, we need to sign the Nuxeo Drive binary packages.
For an unsigned application, under Windows, users only need to click Yes in a various number of popups to get through the security check, but under OS X unless the Security & Privacy settings are changed or they right/Ctrl clik on the file,
they simply won't be able to launch the application!

For a full documentation on application signing see:

  https://github.com/nuxeo/nuxeo-drive/blob/master/nuxeo-drive-client/doc/digital_signature.md

Under Windows
~~~~~~~~~~~~~

You need to make sure to have a valid PFX certificate file on the build machine, let's say it is located in ``C:\Users\Nuxeo\certificates\nuxeo.com.pfx``.

Once the msi package has been generated by ``cx_Freeze``, you only need to run the following script, making sure the ``CERTIFICATE_PATH`` variable is pointing to the PFX certificate file, in this case ``"%USERPROFILE%\certificates\nuxeo.com.pfx"``::

  .\tools\windows\sign_msi.bat

It will sign the msi package and verify its signature. It uses the ``signtool`` command which is available as part of the `Windows SDK <http://msdn.microsoft.com/en-us/windowsserver/bb980924.aspx>`_.


Under OS X
~~~~~~~~~~~~~

You need to make sure to have a code signing identity trusted by Apple in one of the machine's keychain, let's say its name is "Developer ID Application: NUXEO CORP (WCLR6985BX)".

Once the application bundle package has been generated by ``py2app``, you only need to make sure the ``SIGNING_IDENTITY`` variable from the ``create-dmg.sh`` script is set with a substring of the code signing identity (unique throughout the keychains), in this case ``NUXEO CORP``.
The signing process will be done when generating the .dmg archive with::

  sh tools/osx/create-dmg.sh

It will sign the dmg package and verify its signature. It uses the ``codesign`` and ``spctl`` commands included by default in OS X.


Manual initialization
---------------------

If you need to manually initialize Nuxeo Drive, for example to preset the Nuxeo server URL and proxy configuration before launching Nuxeo Drive the first time (useful for mass deployment),
please follow the `related instructions <https://github.com/nuxeo/nuxeo-drive/blob/master/nuxeo-drive-client/doc/manual_init.md>`_.

