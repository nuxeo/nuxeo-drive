# Development Workflow

The development workflow is described on that [Wiki](https://nuxeowiki.atlassian.net/wiki/spaces/DRIVE/pages/861602188/Development+Workflow).

# The Stack

[![Dependabot Status](https://api.dependabot.com/badges/status?host=github&repo=nuxeo/nuxeo-drive)](https://dependabot.com)

Nuxeo Drive is written in Python and make heavily use of the Qt framework.
This allowes to easily create a multi-platform desktop application using the same code base.

# Coding Style Guide

We tend to follow the [PEP8](http://pep8.org), that's all.

To help with this requirement, you can automate checks and formatting using [pre-commit](https://pre-commit.com/):
it will call predefined hooks and [black](https://github.com/ambv/black) for you to ensure there is no regression and to keep the code clean.

For core developers, the whole mechanism is installed with the [developer environment](docs/deployment.md). But if you are a contributor, you can easily use it:

```shell
python -m pip install pre-commit
pre-commit install
```

Note: on Windows you will need to have [Git](https://www.gitforwindows.org) installed.

# Nuxeo Drive Contributor Guide

This guide is for developers willing to work on the Nuxeo Drive codebase itself.

Note that many behaviors of Nuxeo Drive can be customized without actually changing the code of Nuxeo Drive but by contributing to the server side extension points instead.

The projects comes into two parts: the addon deployed on the Nuxeo server, written in Java, and the client written in Python.

Nuxeo Drive client is a Python desktop application that looks for changes on the local machine filesystem in a specific folder and on a remote workspace on the Nuxeo server using the Content Automation HTTP API and propagates those changes one way or the other.

## Building the Server Addon

To build the nuxeo-drive addon see the related [nuxeo](https://github.com/nuxeo/nuxeo/tree/master/addons/nuxeo-drive-server) GitHub repository.

To build the Marketplace package see the related [marketplace-drive](https://github.com/nuxeo/marketplace-drive) GitHub repository.

## Building the Nuxeo Drive Client

See [docs/deployment.md](docs/deployment.md).

## Requirements Notes

- The [Dependabot](https://dependabot.com) will automatically check for updates and opend a PR if needed.
- :warning: **SECURITY**: before upgrading a package, ensure its source code and its updated dependencies are safe to distribute.

## Client Architecture

![Nuxeo Drive architecture][nuxeo-drive-architecture-schema]

[nuxeo-drive-architecture-schema]: https://www.lucidchart.com/publicSegments/view/54e8e2a7-d2a4-4ec7-9843-5c740a00c10b/image.png

**CommandLine**

Handle the basic commandline arguments, create the Manager, and depending on the argument create a ConsoleApplication or Application.

**Manager**

Handle all the generic behavior of Nuxeo Drive: auto-updates, bind of an engine, declaration of different engine types, tracker.

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
