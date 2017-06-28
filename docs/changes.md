# 2.4.6

Release date: `2017-06-xx`

## Core

- [NXDRIVE-680](https://jira.nuxeo.com/browse/NXDRIVE-680): Fix unwanted local upload when offline (on connection lost for instance)
- [NXDRIVE-880](https://jira.nuxeo.com/browse/NXDRIVE-880): Folder remotely created then moved does not sync
- [NXDRIVE-881](https://jira.nuxeo.com/browse/NXDRIVE-881): Handle folder remote rename when doing full remote scan

## GUI

- [NXDRIVE-878](https://jira.nuxeo.com/browse/NXDRIVE-878): Confliction resolution does not seem to be active since 2.4.4
- [NXDRIVE-895](https://jira.nuxeo.com/browse/NXDRIVE-895): Systray menu is blocker when the update website is not responding

## Minor changes

- GUI: Removed "version" from Settings > About
- Jenkins: Set job to UNSTABLE if it fails outside FT
- Jenkins: Use TWANG slave for macOS packaging
