======================================================
Nuxeo Drive - Desktop synchronization client for Nuxeo
======================================================

This is an ongoing development project for desktop synchronization
of local folders with remote Nuxeo workspaces.

Watch this `early screencast`_ to get 2 min overview of this project.

WARNING: The status is EARLY ALPHA. Don't run on a production server
as you might loose data!

.. _`early screencast`: http://lounge.blogs.nuxeo.com/2012/07/nuxeo-drive-desktop-synchronization-client-nuxeo.html


Install
=======

Installing Nuxeo Drive needs two components: a server addon for Nuxeo and a
desktop program on the user's computer.


Server-side marketplace package
-------------------------------

Fetch the latest development version of the marketplace package
`nuxeo-drive-marketplace-5.7-SNAPSHOT.zip <http://qa.nuxeo.org/jenkins/job/IT-nuxeo-drive-master-marketplace/lastSuccessfulBuild/artifact/packaging/nuxeo-drive-marketplace/target/nuxeo-drive-marketplace-5.7-SNAPSHOT.zip>`_
from the Continuous Integration server.

The marketplace package can be installed using the Admin Center /
Update Center / Local Packages interface of a Nuxeo server.

Alternatively, from the command line::

  $NUXEO_HOME/bin/nuxeoctl stop
  $NUXEO_HOME/bin/nuxeoctl mp-install --nodeps nuxeo-drive-marketplace-<version>.zip
  $NUXEO_HOME/bin/nuxeoctl start


Windows Desktop Client
----------------------

Once the marketplace package is installed, the windows desktop client package
can be downloaded from the ``Home > Nuxeo Drive`` tab.

You can also fetch the latest development version for
``nuxeo-drive-<version>-win32.msi``
windows installer from the `Continous Integration <http://qa.nuxeo.org/jenkins/job/IT-nuxeo-drive-master-windows/>`_.

Once you installed the package (Administrator rights required) the new folder
holding the ``ndrive.exe`` and ``ndrivew.exe`` programs will be added to your
``Path`` environment variable automatically.

You can start the ``Nuxeo Drive`` program from the "Start..." menu.

All the necessary dependencies (such as the Python interpreter and the QT /
PySide for the client side user interface) are included in this folder and
should not impact any alternative version possibly already installed on your
computer.


Mac OSX Desktop Client
----------------------

Once the marketplace package is installed, the OSX desktop client package
can be downloaded from the ``Home > Nuxeo Drive`` tab.

You can also fetch the latest development version for
`Nuxeo Drive.dmg <http://qa.nuxeo.org/jenkins/job/IT-nuxeo-drive-master-osx/lastSuccessfulBuild/artifact/dist/Nuxeo%20Drive.dmg>`_
from the Continous Integration.


Ubuntu/Debian (and other Linux variants) Client
-----------------------------------------------

The ``.deb`` package of the client is not yet available. In the mean time you
can install it from source::

  sudo apt-get install python-pip python-dev
  sudo pip install -U -r https://raw.github.com/nuxeo/nuxeo-drive/master/requirements.txt
  sudo pip install -U git+https://github.com/nuxeo/nuxeo-drive.git

The install QT and PySide for graphical user interface (see below).


Configuration and usage
=======================

Regular usage
-------------

1. Launch the Nuxeo Drive program (e.g. from the start menu under Windows).

2. A new icon should open in the system tray and a popup menu should open asking
   the user for the URL of the Nuxeo server and credentials.

3. In the Nuxeo web interface, mark workspaces and folders for synchronization.

4. It is then possible to go to the local Nuxeo Drive folder by using the menu
   of the system tray icon.


Command-line usage (advanced)
----------------------------

The desktop synchronization client can also be operated from the command-line:

1. Ensure that ``ndrive`` program is installed in a folder that has been
   added to the PATH enviroment variable of your OS.

   You can check by typing the ``ndrive --help`` command in a console.

2. Launch the synchronization program (no automatic background mode
   yet, this will come in future versions)::

     ndrive

   Under Windows you can launch ``ndrivew.exe`` instead to avoid
   keeping the cmd console open while Nuxeo Drive is running instead.

   The first time you run this command a dialog window will open asking for the
   URL of the Nuxeo server and your user credentials.

   Alternatively you can bind to a Nuxeo server with your user credentials
   using the following commandline arguments::

     ndrive bind-server nuxeo-username http://server:port/nuxeo --password secret

   This will create a new folder called ``Nuxeo Drive`` in your home
   folder under Linux and MacOSX and under the ``Documents`` folder
   under Windows.

3. Go to your Nuxeo with your browser, navigate to workspaces or
   folder where you have permission to create new documents. Click
   on the double arrows button right of the title of the folder to
   treat this folder as a new synchronization root.

   Alternatively you can do this operation from the commandline with::

     ndrive bind-root "/default-domain/workspaces/My Workspace"

4. You can now create office documents and folders locally or inside
   Nuxeo and watch them getting synchronized both ways automatically.

For more options, type::

    ndrive --help
    ndrive subcommand --help


Reporting bugs
==============

You can log DEBUG information directly in the console by using the
following command-line::

    ndrive --log-level-console=DEBUG

Then you can create a new jira_ issue mentionning the version of the Nuxeo
platform, your operating system name and version (e.g. Windows 7), the steps to
reproduce the error and a copy of the logs.

For long running sessions, it is better to dump the debug information in a log
file. This can be done with the following command::

    ndrive --log-level-file=DEBUG

or even::

    ndrive --log-level-file=TRACE

By default the location of the log file is: ``~/.nuxeo-drive/logs/``
where ``~`` stands for the location of the user folder. For instance:

- under Windows 7 and 8: ``C:\Users\username\.nuxeo-drive\logs``
- under Mac OSX: ``/Users/username/.nuxeo-drive/logs``
- under Ubuntu (and other Linux variants): ``/home/username/.nuxeo-drive/logs``

.. _jira: https://jira.nuxeo.com


Roadmap
=======

The backlog_ is handled by Jira.

.. _backlog: https://jira.nuxeo.com/secure/IssueNavigator.jspa?reset=true&jqlQuery=component+%3D+%22Nuxeo+Drive%22+AND+project+%3D+NXP++and+type+%3D+%22User+story%22+and+resolution+%3D+Unresolved+ORDER+BY+%22Backlog+priority%22+DESC


Developers
==========

The projects comes into two parts: the addon deployed on the Nuxeo
server, written in Java and the client written in Python.

Nuxeo Drive Client is a Python daemon that looks for changes
on the local machine filesystem in a specific folder and on a
remote workspace on the Nuxeo server using the Content Automation
HTTP API and propagate those changes one way of the other.


Server side Java components
---------------------------

To build the project and run the tests, use maven::

  mvn -Ppackaging install

The resulting marketplace package can be found in::

  packaging/nuxeo-drive-marketplace/target/nuxeo-drive-marketplace-<version>.zip


Nuxeo Drive Client under Linux & MacOSX
---------------------------------------

Install pip_ using your favorite package manager and then use it to grab all the
dev dependencies and tools at once::

  sudo pip install -r requirements.txt
  export PYTHONPATH=`pwd`/nuxeo-drive-client
  export PATH=`pwd`/nuxeo-drive-client/bin:$PATH

You can safely ignore warnings about "Unknown distribution option: 'executables'".

To run the tests, install and start a nuxeo server locally, then::

  . nuxeo-drive-client/tools/posix/integration_env.sh
  nosetests nuxeo-drive-client/nxdrive

.. _pip: http://www.pip-installer.org/

The install QT and PySide for graphical user interface (see below).


Nuxeo Drive Client under Windows
--------------------------------

To setup a build environment under Windows you can run the powershell
script with the administration rights (right click on the powershell
icon in the programs menu to get the opportunity to "Run as
administrator")::

  powershell.exe C:\path\to\nuxeo-drive-client\tools\windows\nxdrive-setup-dev.ps1

Some dependencies such as `psutil` can be tricky to build under windows.  You
can use a binary installer from `this site
<http://www.lfd.uci.edu/~gohlke/pythonlibs/>`_.

If you get an error message complaining about the lack of signature
for this script you can disable that security check with the following
command::

  Set-ExecutionPolicy Unrestricted

The install QT and PySide for graphical user interface (see below).

Then you should be able to build the standalone ``.msi`` installer with::

  C:\Python27\python.exe setup.py --freeze bdist_msi

The generated package should then be available in the ``dist/`` subfolder.


Installing QT and PySide
------------------------

The graphical user interface elements of Nuxeo Drive client (such as the
authentication prompt and the trayicon menu) are built using the PySide library
that is a Python binding for the QT C++ library for building cross-platform
interfaces. Both PySide and QT are licensed under the LGPL.

When building/running Nuxeo Drive client from sources (i.e. not using the
``.msi`` package) you should have those libraries installed on your system.

Under Windows and OSX you can install the binaries (take the latest stable
version). The Windows binary is named
``qt-win-opensource-<version>-vs2010.exe`` while the OSX binary is named
``qt-mac-opensource-<version>.dmg``:

- `QT opensource binaries <http://get.qt.nokia.com/qt/source/>`_

The install the matching version of the PySide binaries (for your version of
Python, typically 2.7 for now as Python 3.3 is not yet supported).

- `PySide Windows binaries <http://qt-project.org/wiki/PySide_Binaries_Windows>`_
- `PySide OSX binaries <http://pyside.markus-ullmann.de/>`_

Under Debian / Ubuntu you can install the ``python-pyside`` package directly::

    sudo apt-get install python-pyside


Generating OS specific packages
-------------------------------

.msi package for Windows
~~~~~~~~~~~~~~~~~~~~~~~~

To generate the **Windows** ``.msi`` installer, you need to install ``cx_Freeze``
as explained above. Then run::

    C:\Python27\python.exe setup.py --freeze bdist_msi

The generated ``.msi`` file can be found in the ``dist/`` subfolder.

.app and .dmg packages for OSX
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To generate the standalone OSX `.app` bundle, you **need** to install a
standalone version of Python (i.e. not the version that comes pre-installed
with OSX). Otherwise the ``.app`` bundle will be generated in
``semi-standalone`` mode and will likely not work on other versions of OSX.

To install a standalone version of Python under OSX you can use `HomeBrew
<http://mxcl.github.com/homebrew/>`_::

  $ brew install python

This will install a new Python interpreter along with ``pip`` under
``/usr/local/Cellar`` and add publish it using symlinks in ``/usr/local/bin``
and ``/usr/local/lib/python2.7``.

If you already have another version of pip installed in ``/usr/local/bin`` you
can force the overwrite the ``/usr/local/bin/pip`` with::

  $ brew link --overwrite python

Make sure that you are know using your newly installed version of python / pip::

  $ export PATH=/usr/local/bin:$PATH
  $ which pip
  /usr/local/bin/pip
  $ which python
  /usr/local/bin/python

If you installed PySide from the original binary distribution, you can
symlink it to the hombrew version of Python::

  $ ln -s /Library/Python/2.7/site-packages/PySide /usr/local/lib/python2.7/site-packages/PySide

Then install ``py2app`` along with the dependencies if ::

  $ pip install py2app
  $ pip install -r requirements.txt

Then run::

  $ python setup.py py2app

The generated ``.app`` bundle can be found in the ``dist/`` subfolder. You
can then generate a ``.dmg`` archive using::

  $ hdiutil create -srcfolder "dist/Nuxeo Drive.app" "dist/Nuxeo Drive.dmg"
