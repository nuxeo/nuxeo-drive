======================================================
Nuxeo Drive - Desktop synchronization client for Nuxeo
======================================================

This is an ongoing development project for desktop synchronization
of local folders with remote Nuxeo workspaces.

Watch this `screencast`_ to get 6 min overview of this project.

.. _`screencast`: http://www.nuxeo.com/blog/development/2013/04/nuxeo-drive-desktop-synchronization/

The documentation is available here:

  http://doc.nuxeo.com/x/04HQ


Install
=======

Installing Nuxeo Drive needs two components: a server addon for Nuxeo and a
desktop program on the user's computer.


Server-side marketplace package
-------------------------------

**Stable releases for Nuxeo Drive** are available as a marketplace package from Nuxeo Connect:

  https://connect.nuxeo.com/nuxeo/site/marketplace/package/nuxeo-drive

You can also fetch the **latest development version** of the
`marketplace package <http://qa.nuxeo.org/jenkins/job/addons_nuxeo-drive-master-marketplace>`_
for the Nuxeo master branch from the Continuous Integration server (use at your own risk).

The marketplace package can be installed using the Admin Center /
Update Center / Local Packages interface of a Nuxeo server.

Alternatively, from the command line::

  $NUXEO_HOME/bin/nuxeoctl stop
  $NUXEO_HOME/bin/nuxeoctl mp-install --nodeps marketplace-<version>.zip
  $NUXEO_HOME/bin/nuxeoctl start


Windows Desktop Client
----------------------

Once the marketplace package is installed, the windows desktop client package
can be downloaded from the ``Home > Nuxeo Drive`` tab.

You can also fetch the latest development version for
``nuxeo-drive-<version>-win32.msi``
windows installer from the `Continous Integration <http://qa.nuxeo.org/jenkins/job/addons_nuxeo-drive-master-msi/>`_.

Once you installed the package (Administrator rights required) the new folder
holding the ``ndrive.exe`` and ``ndrivew.exe`` programs will be added to your
``Path`` environment variable automatically.

You can start the ``Nuxeo Drive`` program from the "Start..." menu.

All the necessary dependencies (such as the Python interpreter and the QT /
PyQt for the client side user interface) are included in this folder and
should not impact any alternative version possibly already installed on your
computer.


Mac OSX Desktop Client
----------------------

Once the marketplace package is installed, the OSX desktop client package
can be downloaded from the ``Home > Nuxeo Drive`` tab.

You can also fetch the latest development version for
`Nuxeo Drive.dmg
<https://qa.nuxeo.org/jenkins/job/addons_nuxeo-drive-master-dmg/lastSuccessfulBuild/artifact/dist/Nuxeo%20Drive.dmg>`_
from the Continous Integration.


Ubuntu/Debian (and other Linux variants) Client
-----------------------------------------------

The ``.deb`` package of the client is not yet available. In the mean time you
can install it from source::

  sudo apt-get install python-pip python-dev python-qt4
  sudo pip install -U -r https://raw.github.com/nuxeo/nuxeo-drive/master/requirements.txt
  sudo pip install -U git+https://github.com/nuxeo/nuxeo-drive.git


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

   If you installed the ``.dmg`` package for OSX, the binary is::

       /Applications/Nuxeo\ Drive.app/Contents/MacOS/Nuxeo\ Drive

   You can alias it in your bashrc with:

       alias ndrive="/Applications/Nuxeo\ Drive.app/Contents/MacOS/Nuxeo\ Drive"

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


Developing on Nuxeo Drive
=========================

See the `contributors guide
<https://github.com/nuxeo/nuxeo-drive/blob/master/DEVELOPERS.rst>`_
if you wish to actually contribute to the Nuxeo Drive code base.
