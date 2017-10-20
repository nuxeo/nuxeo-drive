# dev
Release date: `2017-??-??`

### Core
- [NXDRIVE-1012](https://jira.nuxeo.com/browse/NXDRIVE-1012): Remote watcher is missing keywords

### Packaging / Build
- [NXDRIVE-737](https://jira.nuxeo.com/browse/NXDRIVE-737): Use a single launcher
- [NXDRIVE-971](https://jira.nuxeo.com/browse/NXDRIVE-971): Uninstallation fails sometimes on Windows

### Tests
- [NXDRIVE-984](https://jira.nuxeo.com/browse/NXDRIVE-984): Create a script to check any pip installation regressions

#### Minor changes
- Framework: Clean-up queue_manager.py
- Framework: Fix LocalClient.get_path() to use str.partition() and prevent IndexErrors
- GUI: Fix a SEGFAULT when closing the metadata window
- Jenkins: The beta job now uploads the package to the PyPi server
- \[Windows\] Packaging: Prevent infinite loop when uninstalling
- \[Windows\] Packaging: Fix symbolic link creation
- \[Windows\] Packaging: Create the desktop shortcut at installation
- \[Windows\] Packaging: Removed "Launch Nuxeo Drive" checkbox from the installer
- \[Windows\] Packaging: The configuration stored in the registry moved from `HKEY_LOCAL_MACHINE` to `HKEY_CURRENT_USER`


# 2.5.5
Release date: `2017-10-13`

### Core
- [NXDRIVE-950](https://jira.nuxeo.com/browse/NXDRIVE-950): Invalid credentials loop when revoking the user's token
- [NXDRIVE-964](https://jira.nuxeo.com/browse/NXDRIVE-964): Impossible to use an old local folder from another user
- [NXDRIVE-990](https://jira.nuxeo.com/browse/NXDRIVE-990): "Other docs" folder is deleted after disconnect and reconnect with same user
- [NXDRIVE-994](https://jira.nuxeo.com/browse/NXDRIVE-994): Bad use of tuple for keyword xattr_names of LocalClient.update_content()
- [NXDRIVE-995](https://jira.nuxeo.com/browse/NXDRIVE-995): Prevent renaming from 'folder' to 'folder ' on Windows

### GUI
- [NXDRIVE-963](https://jira.nuxeo.com/browse/NXDRIVE-963): Crash when deleting an account
- [NXDRIVE-978](https://jira.nuxeo.com/browse/NXDRIVE-978): Wrong resume/suspend icon after pause and disconnect/reconnect
- [NXDRIVE-982](https://jira.nuxeo.com/browse/NXDRIVE-982): After disconnect and connect, systray menu alignment is not proper

### Packaging / Build
- [NXDRIVE-991](https://jira.nuxeo.com/browse/NXDRIVE-991): Upgrade Python from 2.7.13 to 2.7.14
- [NXDRIVE-992](https://jira.nuxeo.com/browse/NXDRIVE-992): Rollback release tag on Drive-package job failure

### Tests
- [NXDRIVE-1001](https://jira.nuxeo.com/browse/NXDRIVE-1001): Prevent failures in tearDownServer()

### Doc
- [NXDRIVE-974](https://jira.nuxeo.com/browse/NXDRIVE-974): Document Windows CLI related to Drive
- [NXDRIVE-1003](https://jira.nuxeo.com/browse/NXDRIVE-1003): Add MSI arguments documentation

#### Minor changes
- GUI: Add more versions informations in About (Python, Qt, WebKit and SIP)
- Jenkins: Better artifacts deployment on the server
- Jenkins: Update `pyenv` to take into account new Python versions
- Packaging: Updated `cffi` from 1.10.0 to 1.11.2
- Packaging: Updated `faulthandler` from 2.6 to 3.0
- Packaging: Updated `pyobjc` from 3.2.1 to 4.0
- Packaging: Updated `pytest` from 3.2.2 to 3.2.3
- Tools: Fix JSON delivery in check_update_process.py
- \[Windows\] Packaging: Bypass use of get-pip.py for `pip` installation


# 2.5.4
Release date: `2017-09-16`

### Core
- [NXDRIVE-904](https://jira.nuxeo.com/browse/NXDRIVE-904): Renaming folders and removing files does not sync while not running

### Packaging / Build
- [NXDRIVE-977](https://jira.nuxeo.com/browse/NXDRIVE-977): Drive-packages should fail on error
- [NXDRIVE-983](https://jira.nuxeo.com/browse/NXDRIVE-983): Windows pip installation failure because of inexistant DLL
- [NXDRIVE-985](https://jira.nuxeo.com/browse/NXDRIVE-985): The pyjs module is missing from the final package

#### Minor changes
- Utils: `guess_server_url()` now checks for the good HTTP status code
- Tests: Moved a big part of RemoteDocumentClient methods into tests
- Packaging: Updated `psutil` from 5.2.2 to 5.3.1
- Packaging: Updated `pytest` from 3.2.1 to 3.2.2
- Packaging: Updated `pytest-sugar` from 0.8.0 to 0.9.0


# 2.5.3
Release date: `2017-09-06`

### Core
- [NXDRIVE-975](https://jira.nuxeo.com/browse/NXDRIVE-975): Missing OpenSSL DLL in the Windows package

### GUI
- [NXDRIVE-958](https://jira.nuxeo.com/browse/NXDRIVE-958): Disallow root uncheck in the filter list
- [NXDRIVE-959](https://jira.nuxeo.com/browse/NXDRIVE-959): Disable the filter list when syncing


# 2.5.2
Release date: `2017-08-31`

### Core
- [NXDRIVE-729](https://jira.nuxeo.com/browse/NXDRIVE-729): Homogenize headers in source files
- [NXDRIVE-731](https://jira.nuxeo.com/browse/NXDRIVE-731): Remove nuxeo-jsf-ui package dependency
- [NXDRIVE-836](https://jira.nuxeo.com/browse/NXDRIVE-836): Bad behaviors with read-only documents on Windows
- [NXDRIVE-956](https://jira.nuxeo.com/browse/NXDRIVE-956): Uniformize actions on local deletion of read-only documents
- [NXDRIVE-957](https://jira.nuxeo.com/browse/NXDRIVE-957): Update process from 2.5.0 to 2.5.1 is broken

### GUI:
- [NXDRIVE-934](https://jira.nuxeo.com/browse/NXDRIVE-934): Try to guess the server URL
- [NXDRIVE-953](https://jira.nuxeo.com/browse/NXDRIVE-953): After disconnect, Drive is not showing set account window
- [NXDRIVE-954](https://jira.nuxeo.com/browse/NXDRIVE-954): Disconnect, quit and set account, Drive is not showing systray menu

### Tests:
- [NXDRIVE-961](https://jira.nuxeo.com/browse/NXDRIVE-961): Create a script to check any auto-update process regressions

#### Minor changes
- Account: Unset read-only when overwriting local folder
- Tools: Updated `changelog.py` from 1.2.3 to 1.2.5
- Packaging: Updated `Js2Py` from 0.44 to 0.50
- Packaging: Updated `Send2Trash` from 1.3.0 to 1.4.1
- Packaging: Updated `pytest` from 3.1.3 to 3.2.1
- \[Windows\] Tests: Use `QT_PATH` and `MINGW_PATH` envars


# 2.5.1
Release date: `2017-08-04`

### Core
- [NXDRIVE-926](https://jira.nuxeo.com/browse/NXDRIVE-926): Automatically retry on 409 (Conflict)
- [NXDRIVE-935](https://jira.nuxeo.com/browse/NXDRIVE-935): Allow big files (+2 Go) when creating a report

### Packaging / Build
- [NXDRIVE-931](https://jira.nuxeo.com/browse/NXDRIVE-931): macOs build 2.5.0 is broken

### GUI
- [NXDRIVE-936](https://jira.nuxeo.com/browse/NXDRIVE-936): Add pause/resume icons in the left click menu

#### Minor changes
- GUI: Fix context menu position and size when no engine binded
- GUI: Fix Windows bug when the systray icon was still visible after exit
- GUI: More tooltips for better information
- Metrics: Retrieve the SIP version


# 2.5.0
Release date: `2017-07-27`

### Core
- [NXDRIVE-897](https://jira.nuxeo.com/browse/NXDRIVE-897): Fix error when editing a DWG file
- [NXDRIVE-907](https://jira.nuxeo.com/browse/NXDRIVE-907): Replace deprecated log.warn with log.warning
- [NXDRIVE-908](https://jira.nuxeo.com/browse/NXDRIVE-908): Support URL parameters in Nuxeo URL
- [NXDRIVE-915](https://jira.nuxeo.com/browse/NXDRIVE-915): Subscribe to pyup.io for requirements checks
- [NXDRIVE-918](https://jira.nuxeo.com/browse/NXDRIVE-918): Ignore .bak files

### Tests
- [NXDRIVE-917](https://jira.nuxeo.com/browse/NXDRIVE-917): Analyze AutoCAD behaviors

### Packaging / Build
- [NXDRIVE-716](https://jira.nuxeo.com/browse/NXDRIVE-716): Fix warning: Unknown distribution option: 'attribs'
- [NXDRIVE-913](https://jira.nuxeo.com/browse/NXDRIVE-913): Jenkins: Drive-prod job requires the esky module

### GUI
- [NXDRIVE-694](https://jira.nuxeo.com/browse/NXDRIVE-694): Systray menu: needs double click to activate
- [NXDRIVE-711](https://jira.nuxeo.com/browse/NXDRIVE-711): System tray menu acts weird
- [NXDRIVE-865](https://jira.nuxeo.com/browse/NXDRIVE-865): Upgrade the Windows deploy script to compile PyQt/SIP/cx_Freeze (**breaking change**)
- [NXDRIVE-898](https://jira.nuxeo.com/browse/NXDRIVE-898): Add a system tray context menu
- [NXDRIVE-929](https://jira.nuxeo.com/browse/NXDRIVE-929): Cleanup JavaScript/HTML code

#### Minor changes
- Packaging: Upgraded `SIP` from 4.19 to 4.19.3
- Packaging: Updated `py2app` from 0.12 to 0.14
- Packaging: Updated `pytest` from 3.0.7 to 3.1.3
- Packaging: Updated `xattr` from 0.9.1 to 0.9.2
- Packaging: Updated `faulthandler` from 2.4 to 2.6
- Packaging: Updated `psutil` from 5.2.0 to 5.2.2
- Packaging: Updated `pypac` from 0.2.1 to 0.3.1
- Packaging: Updated `python-dateutil` from 2.6.0 to 2.6.1
- Packaging: Removed `setuptools` requirement
- Jenkins: Use TWANG for packages job
- \[Unix\] Packaging: Upgraded `PyQt` from 4.12 to 4.12.1
- \[Windows\] Packaging: Fixed missing `-start` argument
- \[Windows\] Packaging: Removed `7-Zip` dependency
- \[Windows\] Packaging: Upgraded `PyQt` from 4.11.4 to 4.12.1


# 2.4.8
Release date: `2017-07-12`

### Core
- [NXDRIVE-862](https://jira.nuxeo.com/browse/NXDRIVE-862): Infinite loop when renaming a folder from lower case to upper case on Windows
- [NXDRIVE-867](https://jira.nuxeo.com/browse/NXDRIVE-867): DirectEdit file opening does not work with filenames containing accents

### Tests
- [NXDRIVE-837](https://jira.nuxeo.com/browse/NXDRIVE-837): Launch tests against Nuxeo 8.10

### GUI
- [NXDRIVE-895](https://jira.nuxeo.com/browse/NXDRIVE-895): No menu when update site not reachable

#### Minor changes
- Packaging: Set required versions for `appdirs` (1.4.3) and `setuptools` (36.0.1)
- Jenkins: Removed packages job timeout
- Jenkins: Fail early if the build is unstable on functional tests job
- Tests: Fix test_direct_edit.py that uses hard coded Nuxeo URL


# 2.4.7
Release date: `2017-07-05`

### Core
- [NXDRIVE-890](https://jira.nuxeo.com/browse/NXDRIVE-890): Cleanup Windows XP specific code (**breaking change**)
- Revert [NXDRIVE-895](https://jira.nuxeo.com/browse/NXDRIVE-895) that caused troubles when displaying update progress bar

#### Minor changes
- Jenkins: Update the Nuxeo snapshot to 9.3


# 2.4.6
Release date: `2017-06-29`

### Core
- [NXDRIVE-680](https://jira.nuxeo.com/browse/NXDRIVE-680): Fix unwanted local upload when offline (on connection lost for instance)
- [NXDRIVE-880](https://jira.nuxeo.com/browse/NXDRIVE-880): Folder remotely created then moved does not sync
- [NXDRIVE-881](https://jira.nuxeo.com/browse/NXDRIVE-881): Handle folder remote rename when doing full remote scan

### GUI
- [NXDRIVE-878](https://jira.nuxeo.com/browse/NXDRIVE-878): Conflicts resolution does not seem to be active since 2.4.4
- [NXDRIVE-895](https://jira.nuxeo.com/browse/NXDRIVE-895): Systray menu is blocker when the update website is not responding
- [NXP-22493](https://jira.nuxeo.com/browse/NXP-22493): Review EN label and apply capitalization properly for 9.2

### Packaging / Build
- [NXDRIVE-838](https://jira.nuxeo.com/browse/NXDRIVE-838): Update Jenkins jobs to use new macOS slaves

### Doc
- [NXDRIVE-882](https://jira.nuxeo.com/browse/NXDRIVE-882): Add changes documents (for history)

#### Minor changes
- GUI: Removed "version" from Settings > About
- Jenkins: Set job to UNSTABLE if it fails outside FT
- Jenkins: Use the TWANG slave for macOS packaging
