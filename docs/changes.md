# dev
Release date: `2017-??-??`


# 2.5.1
Release date: `2017-07-28`

### Packaging / Build
- [NXDRIVE-931](https://jira.nuxeo.com/browse/NXDRIVE-931): macOs build 2.5.0 is broken

#### Minor changes
- GUI: Fix context menu position and size when no engine binded
- GUI: Do not hide menu when clicking on suspend/resume


# 2.5.0
Release date: `2017-07-28`

New license: LGPL, version 3

### Core
- [NXDRIVE-897](https://jira.nuxeo.com/browse/NXDRIVE-897): Fix error when editing a DWG file
- [NXDRIVE-907](https://jira.nuxeo.com/browse/NXDRIVE-907): Replace deprecated log.warn with log.warning
- [NXDRIVE-908](https://jira.nuxeo.com/browse/NXDRIVE-908): Support URL parameters in Nuxeo URL
- [NXDRIVE-915](https://jira.nuxeo.com/browse/NXDRIVE-915): Subscribe to pyup.io for requirements checks
- [NXDRIVE-918](https://jira.nuxeo.com/browse/NXDRIVE-918): Ignore .bak files

### Tests
- [NXDRIVE-917](https://jira.nuxeo.com/browse/NXDRIVE-917): Analyze AutoCAD behaviors

### Packaging / Build
- [NXDRIVE-913](https://jira.nuxeo.com/browse/NXDRIVE-913): Jenkins: Drive-prod job requires the esky module
- [NXDRIVE-716](https://jira.nuxeo.com/browse/NXDRIVE-716): Fix warning: Unknown distribution option: 'attribs'

### GUI
- [NXDRIVE-694](https://jira.nuxeo.com/browse/NXDRIVE-694): Systray menu: needs double click to activate
- [NXDRIVE-711](https://jira.nuxeo.com/browse/NXDRIVE-711): System tray menu acts weird
- [NXDRIVE-865](https://jira.nuxeo.com/browse/NXDRIVE-865): Upgrade the Windows deploy script to compile PyQt/SIP/cx_Freeze (**breaking change**)
- [NXDRIVE-898](https://jira.nuxeo.com/browse/NXDRIVE-898): Add a system tray context menu
- [NXDRIVE-929](https://jira.nuxeo.com/browse/NXDRIVE-929): Cleanup JavaScript/HTML code

#### Minor changes
- Packaging: Fixed missing `-start` argument on Windows
- Packaging: Removed `7-Zip` dependency on Windows
- Packaging: Upgraded `SIP` from 4.19 to 4.19.3
- Packaging: Upgraded `PyQt` from 4.12 to 4.12.1 on GNU/Linux and macOS
- Packaging: Upgraded `PyQt` from 4.11.4 to 4.12.1 on Windows
- Packaging: Updated `py2app` from 0.12 to 0.14
- Packaging: Updated `pytest` from 3.0.7 to 3.1.3
- Packaging: Updated `xattr` from 0.9.1 to 0.9.2
- Packaging: Updated `faulthandler` from 2.4 to 2.6
- Packaging: Updated `psutil` from 5.2.0 to 5.2.2
- Packaging: Updated `pypac` from 0.2.1 to 0.3.1
- Packaging: Updated `python-dateutil` from 2.6.0 to 2.6.1
- Packaging: Removed `setuptools` requirement
- Jenkins: use TWANG for packages job


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
