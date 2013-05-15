
Developping Nuxeo Drive
=======================

This guide is for developers will to work on the Nuxeo Drive codebase it-self.

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


Nuxeo Drive Client under Linux & MacOSX
---------------------------------------

**Under OS X**: before installing Python packages, you should probably start by
installing your own non-system version of Python 2.7 using homebrew as explained
in a dedicated section below.

Use pip_ to grab all the dev dependencies and tools at once::

  sudo pip install -r requirements.txt

You can then put the following in your ``.bashrc`` to be able to run the Nuxeo
Drive client from your source folder::

  export PYTHONPATH=`pwd`/nuxeo-drive-client
  export PATH=`pwd`/nuxeo-drive-client/bin:$PATH

You can safely ignore warnings about "Unknown distribution option: 'executables'".

To run the tests, install and start a nuxeo server locally, then::

  . nuxeo-drive-client/tools/posix/integration_env.sh
  nosetests nuxeo-drive-client/nxdrive

.. _pip: http://www.pip-installer.org/

**Under OS X** you can also optionally install ``PyObjC`` to get the
``LaunchServices`` API for registering the Nuxeo Drive folder in the OS X
Finder favorite list (a.k.a. "Places")::

  pip install PyObjC

WARNING: this will download many large dependencies and sometimes the remote
server will timeout on some of them: you might need to re-run this command
several times to get it all installed.

Then install QT and PySide for graphical user interface (see below).


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

Then install QT and PySide for graphical user interface (see below).

You can then run the integration tests against a Nuxeo instance running
``localhost:8080`` with:

  . nuxeo-drive-client/tools/windows/integration_env.ps1
  nosetests nuxeo-drive-client/nxdrive


Installing QT and PySide
------------------------

The graphical user interface elements of Nuxeo Drive client (such as the
authentication prompt and the trayicon menu) are built using the PySide library
that is a Python binding for the QT C++ library for building cross-platform
interfaces. Both PySide and QT are licensed under the LGPL.

When building/running Nuxeo Drive client from sources (i.e. not using the
``.msi`` package) you should have those libraries installed on your system.

Under Windows
~~~~~~~~~~~~~

Under Windows you can install the binaries by following the instructions of
the PySide website:

  http://qt-project.org/wiki/PySide_Binaries_Windows

Beware to install the matching version of the PySide binaries (for your
version of Python, typically 2.7 for now as Python 3.3 is not yet supported by
Nuxeo Drive).

Also if you want to use your developer workstation to generate frozen a `.msi`
build of the Nuxeo Drive client to be runnable on all windows platforms (both 32
and 64 bit), be careful to install both the 32 bit version of Python and PySide.


Under Mac OSX
~~~~~~~~~~~~~

Under OSX you can either install the binaries by following the instruction
of the PySide website:

  http://qt-project.org/wiki/PySide_Binaries_MacOSX

If you installed a standlone version of Python with homebrew (recommended), you
can symlink the binary install of PySide to the ``site-packages`` folder of the
homebre Python::

  ln -s /Library/Python/2.7/site-packages/PySide /usr/local/lib/python2.7/site-packages/PySide

**Alternatively** you can install PySide and QT from source using homebrew
with::

  brew install pyside

If this fails to build, here are some intructions to help solve any common
build issues for PySide and QT under OSX:

- first uninstall any previous install of PySide and QT on your machine::

    sudo pip uninstall PySide
    brew uninstall pyside shiboken qt
    sudo python /Developer/Tools/uninstall-qt.py

- then update brew to get the latest recipes::

    brew update

- then fix all the issues reported by ``brew doctor``::

    brew doctor

In particular make sure to have an up-to-date the version of the Command Line
Tools package to match XCode's version using the "Downloads" tab of the
Preferences menu of XCode.

- finally re-running the the pyside build should now work::

    brew install pyside


Under Debian / Ubuntu
~~~~~~~~~~~~~~~~~~~~~

You can install the ``python-pyside`` package directly::

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

To install you a standalone version of Python with homebrew see the dedicated
section below first.

Then install ``py2app`` along with the dependencies if ::

  pip install py2app
  pip install -r requirements.txt

Then run::

  python setup.py py2app

The generated ``.app`` bundle can be found in the ``dist/`` subfolder. You
can then generate a ``.dmg`` archive using::

  hdiutil create -srcfolder "dist/Nuxeo Drive.app" "dist/Nuxeo Drive.dmg"


Installing a standalone Python interpreter on Mac OSX
------------------------------------------------------

To install a standalone version of Python under OSX you can use `HomeBrew
<http://mxcl.github.com/homebrew/>`_::

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

