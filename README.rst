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

Fetch the latest development version of the marketplace package from the
Continuous Integraton server:

  http://qa.nuxeo.org/jenkins/job/IT-nuxeo-drive-master-windows/

The filename should be ``nuxeo-drive-marketplace-<version>.zip``.

The marketplace package can be installed using the Admin Center /
Update Center / Local Packages interface of a Nuxeo server.

Alternatively, from the command line::

  $NUXEO_HOME/bin/nuxeoctl stop
  $NUXEO_HOME/bin/nuxeoctl mp-install --nodeps nuxeo-drive-marketplace-<version>.zip
  $NUXEO_HOME/bin/nuxeoctl start


Windows Desktop Client
----------------------

Fetch the latest development version for ``nuxeo-drive-<version>.msi`` windows
installer from the Continous Integration server at:

  http://qa.nuxeo.org/jenkins/job/IT-nuxeo-drive-master-windows/

Once you installed the package (Administrator rights required) put
the folder holding the ``ndrive.exe`` program in your ``Path``
environment variable.


Mac OSX Desktop Client
----------------------

The ``.dmg`` package of the client is not yet available. In the
mean time you can install it from source::

  sudo easy_install pip
  sudo pip install -U -r https://raw.github.com/nuxeo/nuxeo-drive/master/requirements.txt
  sudo pip install -U git+https://github.com/nuxeo/nuxeo-drive.git


Ubuntu/Debian (and other Linux variants) Client
-----------------------------------------------

The ``.deb`` package of the client is not yet available. In the mean time you
can install it from source::

  sudo apt-get install python-pip
  sudo pip install -U -r https://raw.github.com/nuxeo/nuxeo-drive/master/requirements.txt
  sudo pip install -U git+https://github.com/nuxeo/nuxeo-drive.git


Configuration and usage
=======================

Once Nuxeo Drive is installed on the client desktop (either from a
ready to use ``.msi`` binary installer or buy installing from source,
see below), the synchronization client can be operated from the
commandline.

1. Ensure that ``ndrive`` program is installed in a folder that has been
   added to the PATH enviroment variable of your OS.

2. Register a binding to a Nuxeo server with your user credentials::

     ndrive bind-server nuxeo-username http://server:port/nuxeo --password secret

   This will create a new folder called ``Nuxeo Drive`` in your home
   folder under Linux and MacOSX and under the ``Documents`` folder
   under Windows.

3. Launch the synchronization process (no automatic background mode
   yet, this will come in future versions)::

     ndrive console

4. Go to your Nuxeo with your browser, navigate to workspaces or
   folder where you have permission to create new documents. Click
   on the double arrows button right of the title of the folder to
   treat this folder as a new synchronization root.

   You can alternatively do this operation from the commandline with::

     ndrive bind-root "/default-domain/workspaces/My Workspace"

5. You can now create office documents and folders locally or inside
   Nuxeo and watch them getting synchronized both ways automatically.


For more options, type::

    ndrive --help
    ndrive subcommand --help


Reporting bugs
==============

You can log DEBUG information directly in the console by using the
following commandline::

    ndrive --log-level-console=DEBUG console

Then you can create a new jira_ issue mentionning the version of the Nuxeo
platform, your operating system name and version (e.g. Windows 7), the steps to
reproduce the error and a copy of the logs.

For long running sessions, it is better to dump the debug information in a log
file. This can be done with the following command::

    ndrive --log-level-file=DEBUG console

or even::

    ndrive --log-level-file=TRACE console

By default the location of the log file is: ``~/.nuxeo-drive/logs/``
where ``~`` stands for the location of the user folder. For instance:

- under Windows 7 and 8: ``C:\Users\username\.nuxeo-drive\logs``
- under Mac OSX: ``/Users/username/.nuxeo-drive/logs``
- under Ubuntu (and other Linux variants): ``/home/username/.nuxeo-drive/logs``

.. _jira: https://jira.nuxeo.com


Roadmap
=======

The backlog_ is handled by Jira.

.. _backlog: https://jira.nuxeo.com/secure/IssueNavigator.jspa?reset=true&jqlQuery=component+%3D+%22Nuxeo+Drive%22+AND+Tags+%3D+%22Backlog%22+ORDER+BY+%22Backlog+priority%22+DESC


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

To install in "editable" mode (aka "develop" mode), you can then do::

  sudo pip install -e .

The editable mode makes it possible to edit the python source code
in the ``nuxeo-drive-client/nxdrive`` folder and test the changes
by running ``ndrive`` directly without having to re-rerun the ``pip
install`` command.

You can safely ignore warnings about "Unknown distribution option: 'executables'".

To run the tests, install and start a nuxeo server locally, then::

  . ./tools/posix/integration_env.sh
  nosetests nxdrive

.. _pip: http://www.pip-installer.org/


Nuxeo Drive Client under Windows
--------------------------------

To setup a build environment under Windows you can run the powershell
script with the administration rights (right click on the powershell
icon in the programs menu to get the opportunity to "Run as
administrator")::

  powershell.exe C:\path\to\nuxeo-drive-client\tools\windows\nxdrive-setup-dev.ps1

If you get an error message complaining about the lack of signature
for this script you can disable that security check with the following
command::

  Set-ExecutionPolicy Unrestricted

Then you should be able to build the standalone ``.msi`` installer with::

  C:\Python27\python.exe setup.py --freeze bdist_msi

The generated package should then be available in the ``dist/`` subfolder.


Additional resources
--------------------

- `Continuous Integration Linux`_
- `Continuous Integration Windows`_
- `Coverage Report`_

.. _`Continuous Integration Linux`: http://qa.nuxeo.org/jenkins/job/IT-nuxeo-drive-master-linux/
.. _`Continuous Integration Windows`: http://qa.nuxeo.org/jenkins/job/IT-nuxeo-drive-master-windows/
.. _`Coverage report`: http://qa.nuxeo.org/jenkins/job/IT-nuxeo-drive-master-linux/lastSuccessfulBuild/artifact/nuxeo-drive/nuxeo-drive-client/coverage/index.html

