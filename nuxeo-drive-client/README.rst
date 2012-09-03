======================================================
Nuxeo Drive - Desktop synchronization client for Nuxeo
======================================================

This is an ongoing development project for desktop synchronization
of local folders with remote Nuxeo workspaces.

Watch this `early screencast`_ to get 2 min overview of this project.

WARNING: The status is EARLY ALPHA. Don't run on a production server
as you might loose data!

.. _`early screencast`: http://lounge.blogs.nuxeo.com/2012/07/nuxeo-drive-desktop-synchronization-client-nuxeo.html


Binary download
===============

A self-contained Windows binary download (`.msi` archive) is automatically
generated from the master branch of this repository by the Continuous
Integration server:

  http://qa.nuxeo.org/jenkins/job/IT-nuxeo-drive-master-windows/

Under Mac OSX and Linux, you can build the client from the source
as explained in the "Developers" section.


Command line configuration
==========================

Once Nuxeo Drive is installed on the client desktop (either from a
ready to use `.msi` binary installer or buy installing from source,
see below), the synchronization client can be operated from the
commandline.

1. Ensure that `ndrive` program is installed in a folder that has been
   added to the PATH enviroment variable of your OS.

2. Register a binding to a Nuxeo server with your user credentials::

     ndrive bind-server nuxeo-username http://server:port/nuxeo --password secret

   This will create a new folder called `Nuxeo Drive` in your home
   folder under Linux and MacOSX and under the `Documents` folder
   under Windows.

3. Register a binding to a Nuxeo workspace, use the `bind-root` subcommand::

     ndrive bind-root "/default-domain/workspaces/My Workspace"

   This will create a new folder named `My Workspace` under `Nuxeo
   Drive` and will recursively populate it with the content of the
   remote Nuxeo workspace.

4. Launch the synchronization process (no automatic background mode yet)::

     ndrive console

5. You can now create office documents and folders locally or inside
   Nuxeo and watch them getting synchronized both ways automatically.


For more options, type::

    ndrive --help
    ndrive subcommand --help


Roadmap
=======

The backlog_ is handled by Jira.

.. _backlog: https://jira.nuxeo.com/secure/IssueNavigator.jspa?reset=true&jqlQuery=component+%3D+%22Nuxeo+Drive%22+AND+Tags+%3D+%22Backlog%22+ORDER+BY+%22Backlog+priority%22+DESC


Developers
==========

Nuxeo Drive Client is a Python daemon that looks for changes
on the local machine filesystem in a specific folder and on a
remote workspace on the Nuxeo server using the Content Automation
HTTP API and propagate those changes one way of the other.


Linux & MacOSX
--------------

Install pip_ using your favorite package manager and then use it to grab all the
dev dependencies and tools at once::

    sudo pip install -r dev-requirements.txt

To install in "dev" mode, you can then do::

    sudo pip install -e .

You can safely ignore warnings about "Unknown distribution option: 'executables'".


To run the tests, install and start a nuxeo server locally, then::

    . ./tools/posix/integration_env.sh
    nosetests nxdrive

.. _pip: http://www.pip-installer.org/



Windows
-------

To setup a build environment under Windows you can run the powershell
script with the administration rights (right click on the powershell
icon in the programs menu to get the opportunity to "Run as
administrator")::

    powershell.exe C:\path\to\nuxeo-drive-client\tools\windows\nxdrive-setup-dev.ps1

If you get an error message complaining about the lack of signature for
this script you can disable that security check with the following command:

    Set-ExecutionPolicy Unrestricted

Then you should be able to build the standalone `.msi` installer with::

    C:\Python27\python.exe setup.py bdist_msi

The generated package should then be available in the `dist/` subfolder.


Additional resources
--------------------

- `Continuous Integration`_
- `Coverage Report`_

.. _`Continuous Integration`: http://qa.nuxeo.org/jenkins/job/IT-nuxeo-drive-master-linux/
.. _`Coverage report`: http://qa.nuxeo.org/jenkins/job/IT-nuxeo-drive-master-linux/lastSuccessfulBuild/artifact/nuxeo-drive/nuxeo-drive-client/coverage/index.html

