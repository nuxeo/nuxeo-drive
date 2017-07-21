# dev
Release date: `2017-??-??`

#### Minor changes
- Ignore .nxpart file by default
- Jenkins: use TWANG for packages job


# 2.4.8
Release date: `2017-07-12`

#### Minor changes
- Packaging: Set required versions for `appdirs` (1.4.3) and `setuptools` (36.0.1)
- Jenkins: Removed packages job timeout
- Jenkins: Fail early if the build is unstable on functional tests job
- Tests: Fix `test_direct_edit.py` that uses hard coded Nuxeo URL


# 2.4.7
Release date: `2017-07-05`

### Core
- [NXDRIVE-890](https://jira.nuxeo.com/browse/NXDRIVE-890): Cleanup Windows XP specific code
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
