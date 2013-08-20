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


Nuxeo Drive Client under Linux & MacOSX
---------------------------------------

**Under OS X**: before installing Python packages, you should probably start by
installing your own non-system version of Python 2.7 using homebrew as explained
in a dedicated section below.

Use pip_ to grab all the dev dependencies and tools at once::

  sudo pip install -r requirements.txt

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

Then install QT and PyQt for graphical user interface (see below).


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

Then install QT and PyQt for graphical user interface (see below).

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


Installing QT and PyQt
------------------------

The graphical user interface elements of Nuxeo Drive client (such as the
authentication prompt and the trayicon menu) are built using the PyQt library
that is a Python binding for the QT C++ library for building cross-platform
interfaces. Beware that:

- QT is available under both the LGPL and GPL
- PyQt is available either under the GPL or the PyQt commercial license. See `http://www.riverbankcomputing.co.uk/software/pyqt/license` for more details about PyQt license.

When building/running Nuxeo Drive client from sources (i.e. not using the
``.msi`` package) you should have those libraries installed on your system.

Under Windows
~~~~~~~~~~~~~

Under Windows you can install the binaries downloaded from the PyQt website:

  http://www.riverbankcomputing.co.uk/software/pyqt/download

Beware to install the matching version of the PyQt binaries (for your
version of Python, typically 2.7 for now as Python 3.3 is not yet supported by
Nuxeo Drive).

Also if you want to use your developer workstation to generate frozen a `.msi`
build of the Nuxeo Drive client to be runnable on all windows platforms (both 32
and 64 bit), be careful to install both the 32 bit version of Python and PyQt.


Under Mac OSX
~~~~~~~~~~~~~

Under OS X you can install Qt and PyQt using Homebrew.

First you need to make sure that the brew installed Python will be used when installing PyQt::

  #Override default tools with Cellar ones if available
  #This makes sure homebrew stuff is used
  export PATH=/usr/local/bin:$PATH

  #Point OSX to Cellar python
  export PYTHONPATH=/usr/local/lib/python:$PYTHONPATH

Then install PyQt with Homebrew::

  sudo brew install pyqt

You can also install the binary package downloaded from the PyQt website:

  http://sourceforge.net/projects/pyqt/files/PyQt4/PyQt-4.10.2/PyQt-mac-gpl-4.10.2.tar.gz

In this case and if you installed a standalone version of Python with Homebrew (recommended), you
might need to symlink the binary install of PyQt to the ``site-packages``
folder of the brewed Python::

  ln -s /Library/Python/2.7/site-packages/PyQt4 /usr/local/lib/python2.7/site-packages/PyQt4


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

