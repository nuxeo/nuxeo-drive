# dev
Release date: `2018-??-??`

New authentication process using the **user's browser**.

Changes in command line arguments:

- Removed `proxy-exceptions`
- Removed `proxy-type`

### Core
- [NXDRIVE-659](https://jira.nuxeo.com/browse/NXDRIVE-659): Fix permissions awareness when resuming synchronization
- [NXDRIVE-691](https://jira.nuxeo.com/browse/NXDRIVE-691): Upgrade to Python 3 (**breaking change**)
- [NXDRIVE-692](https://jira.nuxeo.com/browse/NXDRIVE-692): Upgrade from PyQt4 to PyQt5 (**breaking change**)
- [NXDRIVE-825](https://jira.nuxeo.com/browse/NXDRIVE-825): Rely on the Python client for all Nuxeo API calls (**breaking change**)
- [NXDRIVE-876](https://jira.nuxeo.com/browse/NXDRIVE-876): Make NotFound exception inherits from OSError
- [NXDRIVE-922](https://jira.nuxeo.com/browse/NXDRIVE-922): Move custom exceptions to exceptions.py
- [NXDRIVE-1068](https://jira.nuxeo.com/browse/NXDRIVE-1068): Move proxy support to a dedicated module (**breaking change**)
- [NXDRIVE-1171](https://jira.nuxeo.com/browse/NXDRIVE-1171): Handle latin accents in Windows session usernames
- [NXDRIVE-1201](https://jira.nuxeo.com/browse/NXDRIVE-1201): Adapt Drive for new Trash API behavior
- [NXDRIVE-1210](https://jira.nuxeo.com/browse/NXDRIVE-1210): Sanitize exported objects
- [NXDRIVE-1238](https://jira.nuxeo.com/browse/NXDRIVE-1238): \[GDPR\] Remove the username from statistics
- [NXDRIVE-1239](https://jira.nuxeo.com/browse/NXDRIVE-1239): DirectEdit should work after network loss
- [NXDRIVE-1240](https://jira.nuxeo.com/browse/NXDRIVE-1240): Use black for a big code clean-up
- [NXDRIVE-1241](https://jira.nuxeo.com/browse/NXDRIVE-1241): Set the --consider-ssl-errors argument default value to True
- [NXDRIVE-1242](https://jira.nuxeo.com/browse/NXDRIVE-1242): Use type annotations everywhere
- [NXDRIVE-1256](https://jira.nuxeo.com/browse/NXDRIVE-1256): Fix the missing synchronization folder icon on Windows
- [NXDRIVE-1258](https://jira.nuxeo.com/browse/NXDRIVE-1258): Better handle unknown digest algorithms
- [NXDRIVE-1262](https://jira.nuxeo.com/browse/NXDRIVE-1262): Do not rely on XCode on macOS
- [NXDRIVE-1279](https://jira.nuxeo.com/browse/NXDRIVE-1279): Use flake8 for another clean-up round
- [NXDRIVE-1286](https://jira.nuxeo.com/browse/NXDRIVE-1286): Ignore documents when the system cannot find the file
- [NXDRIVE-1291](https://jira.nuxeo.com/browse/NXDRIVE-1291): Use the user's browser for authentication
- [NXDRIVE-1292](https://jira.nuxeo.com/browse/NXDRIVE-1292): Make the authentication easier to customize
- [NXDRIVE-1287](https://jira.nuxeo.com/browse/NXDRIVE-1287): Better server error 500 reporting
- [NXDRIVE-1303](https://jira.nuxeo.com/browse/NXDRIVE-1303): Fix using the bind-server CLI argument without --local-folder
- [NXDRIVE-1307](https://jira.nuxeo.com/browse/NXDRIVE-1307): Do not use nxdrive protocol from the FinderSync extension
- [NXDRIVE-1339](https://jira.nuxeo.com/browse/NXDRIVE-1339): Handle boolean parameters
- [NXDRIVE-1342](https://jira.nuxeo.com/browse/NXDRIVE-1342): Handle Windows session names with unicode

### GUI
- [NXDRIVE-600](https://jira.nuxeo.com/browse/NXDRIVE-600): Use the generic JSP to acquire a token
- [NXDRIVE-969](https://jira.nuxeo.com/browse/NXDRIVE-969): Switch to QML for UI
- [NXDRIVE-1183](https://jira.nuxeo.com/browse/NXDRIVE-1183): Make server UI selection smarter
- [NXDRIVE-1195](https://jira.nuxeo.com/browse/NXDRIVE-1195): Add a setting to let the user choose the icons set
- [NXDRIVE-1231](https://jira.nuxeo.com/browse/NXDRIVE-1231): Add a message box to display fatal errors
- [NXDRIVE-1235](https://jira.nuxeo.com/browse/NXDRIVE-1235): Disable Hebrew language as it is not translated
- [NXDRIVE-1267](https://jira.nuxeo.com/browse/NXDRIVE-1267): Add a notification when DirectEdit starts the download of a file
- [NXDRIVE-1300](https://jira.nuxeo.com/browse/NXDRIVE-1300): Display an error on bad configuration parameters
- [NXDRIVE-1314](https://jira.nuxeo.com/browse/NXDRIVE-1314): Add a placeholder text in server URL

### Packaging / Build
- [NXDRIVE-1217](https://jira.nuxeo.com/browse/NXDRIVE-1217): Hide the Dock icon on macOS
- [NXDRIVE-1223](https://jira.nuxeo.com/browse/NXDRIVE-1223): Use a fork of universal-analytics-python that supports Python 3
- [NXDRIVE-1225](https://jira.nuxeo.com/browse/NXDRIVE-1225): Be specific about pyobjc requirements
- [NXDRIVE-1234](https://jira.nuxeo.com/browse/NXDRIVE-1234): Tweak pyup.io parameters
- [NXDRIVE-1244](https://jira.nuxeo.com/browse/NXDRIVE-1244): Ensure Drive is closed before auto-upgrading on Windows
- [NXDRIVE-1323](https://jira.nuxeo.com/browse/NXDRIVE-1323): Use venv instead of virtualenv on Windows
- [NXDRIVE-1343](https://jira.nuxeo.com/browse/NXDRIVE-1343): Archive a zipped version of the package folder when building installers

### Doc
- [NXDRIVE-1276](https://jira.nuxeo.com/browse/NXDRIVE-1276): Add documentation about Nuxeo Platform support

### Tests
- [NXDRIVE-1212](https://jira.nuxeo.com/browse/NXDRIVE-1212): Disable all server converters, enabled on-demand
- [NXDRIVE-1246](https://jira.nuxeo.com/browse/NXDRIVE-1246): Fix pytest randombug plugin STRICT mode
- [NXDRIVE-1293](https://jira.nuxeo.com/browse/NXDRIVE-1293): Tweak timeouts in testing jobs on Jenkins
- [NXDRIVE-1316](https://jira.nuxeo.com/browse/NXDRIVE-1316): Only run tests when code files are modified or build is launched manually

#### Minor changes
- Development: Use the pre-commit tool to ensure a good quality code before committing
- Framework: Make NotFound exception inherits from OSError
- Jenkins: Added the `PYTEST_ADDOPTS` parameter to the Drive-tests job
- Jenkins: Removed the `ENABLE_PROFILER` parameter from the Drive-tests job
- Packaging: Added `distro` 1.3.0
- Packaging: Added `flake8` 3.5.0
- Packaging: Added `nuxeo` 2.0.3
- Packaging: Added `pre-commit` 1.11.0
- Packaging: Updated `psutil` from 5.4.4 to 5.4.7
- Packaging: Updated `pycryptodomex` from 3.6.1 to 3.6.6
- Packaging: Updated `pypac` from 0.8.1 to 0.11.0
- Packaging: Updated `pytest` from 3.5.1 to 3.8.0
- Packaging: Updated `pytest-cov` from 2.5.1 to 2.6.0
- Packaging: Updated `pytest-timeout` from 1.2.1 to 1.3.2
- Packaging: Updated `rfc3987` from 1.3.7 to 1.3.8
- Packaging: Updated `xattr` from 0.9.3 to 0.9.6
- Packaging: Updated `watchdog` from 0.8.4 to 0.9.0
- Packaging: Removed `SIP_VERSION` and `PYQT_VERSION` envars
- Tests: Added `-b -Wall` arguments to the Python interpreter while testing
- \[GNU/Linux\] Packaging: Removed `COMPILE_WITH_DEBUG` envar
- \[Windows\] Packaging: Added the `PYTHON_DIR` envar
- \[Windows\] Packaging: Removed `QT_PATH` and `MINGW_PATH` envars


# 3.1.1
Release date: `2018-06-12`

### Core
- [NXDRIVE-605](https://jira.nuxeo.com/browse/NXDRIVE-605): Handle corrupted SQLite database
- [NXDRIVE-1230](https://jira.nuxeo.com/browse/NXDRIVE-1230): Fix the ability to disable a Worker

### Packaging / Build
- [NXDRIVE-1226](https://jira.nuxeo.com/browse/NXDRIVE-1226): Deprecate macOS 10.10 (Yosemite)
- [NXDRIVE-1229](https://jira.nuxeo.com/browse/NXDRIVE-1229): Do not install Drive in %APPDATA% but %LOCALAPPDATA% folder on Windows
- [NXDRIVE-1232](https://jira.nuxeo.com/browse/NXDRIVE-1232): Split the macOS installer build to support macOS 10.11

#### Minor changes
- Tools: Fixed the changelog latest release tag guess


# 3.1.0
Release date: `2018-05-23`

Changes in command line arguments:
- Added `access-online`
- Renamed `share-link` -> `copy-share-link`
- Renamed `metadata` -> `edit-metadata`

### Core
- [NXDRIVE-626](https://jira.nuxeo.com/browse/NXDRIVE-626): Use Crowdin for label translations
- [NXDRIVE-925](https://jira.nuxeo.com/browse/NXDRIVE-925): Conflict resolve using local is not working
- [NXDRIVE-988](https://jira.nuxeo.com/browse/NXDRIVE-988): Handle local document deletion and restore on macOS
- [NXDRIVE-1121](https://jira.nuxeo.com/browse/NXDRIVE-1121): Set modified date to Nuxeo platform modified date
- [NXDRIVE-1130](https://jira.nuxeo.com/browse/NXDRIVE-1130): Set creation date to Nuxeo platform creation date
- [NXDRIVE-1132](https://jira.nuxeo.com/browse/NXDRIVE-1132): Security fix in the Crypto module (move to PyCryptodome)
- [NXDRIVE-1133](https://jira.nuxeo.com/browse/NXDRIVE-1133): Purge dead code reported by the 'vulture' tool
- [NXDRIVE-1143](https://jira.nuxeo.com/browse/NXDRIVE-1143): New auto-update framework (**breaking change**)
- [NXDRIVE-1147](https://jira.nuxeo.com/browse/NXDRIVE-1147): Do not definitively delete a document synced elsewhere
- [NXDRIVE-1152](https://jira.nuxeo.com/browse/NXDRIVE-1152): Handle document delete operation by server version
- [NXDRIVE-1154](https://jira.nuxeo.com/browse/NXDRIVE-1154): Persist the server's UI into the local configuration database
- [NXDRIVE-1163](https://jira.nuxeo.com/browse/NXDRIVE-1163): Direct Edit does not work with filenames containing spaces
- [NXDRIVE-1174](https://jira.nuxeo.com/browse/NXDRIVE-1174): Efficient `ConfigurationDAO.update_config()`
- [NXDRIVE-1207](https://jira.nuxeo.com/browse/NXDRIVE-1207): Modifying a file overwrites event on its parent folder
- [NXDRIVE-1327](https://jira.nuxeo.com/browse/NXDRIVE-1327): Add the is_frozen decorator

### GUI
- [NXDRIVE-289](https://jira.nuxeo.com/browse/NXDRIVE-289): Use light icons on Windows
- [NXDRIVE-715](https://jira.nuxeo.com/browse/NXDRIVE-715): Use SVG for icons
- [NXDRIVE-891](https://jira.nuxeo.com/browse/NXDRIVE-891): Locked notification displays 'userid' instead of full username
- [NXDRIVE-1025](https://jira.nuxeo.com/browse/NXDRIVE-1025): Filters issue with folders at the same tree level
- [NXDRIVE-1108](https://jira.nuxeo.com/browse/NXDRIVE-1108): Standardize and rename context menu entry
- [NXDRIVE-1123](https://jira.nuxeo.com/browse/NXDRIVE-1123): Access right-click action on folders on Windows
- [NXDRIVE-1124](https://jira.nuxeo.com/browse/NXDRIVE-1124): Right click menu entry on files: "Copy share-link"
- [NXDRIVE-1126](https://jira.nuxeo.com/browse/NXDRIVE-1126): Notifications are size limited
- [NXDRIVE-1136](https://jira.nuxeo.com/browse/NXDRIVE-1136): Change systray icon on update
- [NXDRIVE-1140](https://jira.nuxeo.com/browse/NXDRIVE-1140): Use a GIF for the transferring icon
- [NXDRIVE-1149](https://jira.nuxeo.com/browse/NXDRIVE-1149): New language: Indonesian
- [NXDRIVE-1157](https://jira.nuxeo.com/browse/NXDRIVE-1157): Use file system decoration on macOS
- [NXDRIVE-1158](https://jira.nuxeo.com/browse/NXDRIVE-1158): Restore the context menu "Edit metadata"
- [NXDRIVE-1166](https://jira.nuxeo.com/browse/NXDRIVE-1166): Display a notification on new update on GNU/Linux
- [NXDRIVE-1175](https://jira.nuxeo.com/browse/NXDRIVE-1175): New language: Hebrew
- [NXDRIVE-1193](https://jira.nuxeo.com/browse/NXDRIVE-1193): Switch all HTML messages box to simple Qt box

### Packaging / Build
- [NXDRIVE-136](https://jira.nuxeo.com/browse/NXDRIVE-136): Activate code signing on macOS (valid until 2023-03-10)
- [NXDRIVE-261](https://jira.nuxeo.com/browse/NXDRIVE-261): Activate code signing on Windows (valid until 2021-04-25)
- [NXDRIVE-448](https://jira.nuxeo.com/browse/NXDRIVE-448): Fix version displayed in Windows uninstall
- [NXDRIVE-512](https://jira.nuxeo.com/browse/NXDRIVE-512): Windows application properties not set
- [NXDRIVE-601](https://jira.nuxeo.com/browse/NXDRIVE-601): Provide a user installation mode on Windows
- [NXDRIVE-730](https://jira.nuxeo.com/browse/NXDRIVE-730): Move to PyInstaller (**breaking change**)
- [NXDRIVE-1125](https://jira.nuxeo.com/browse/NXDRIVE-1125): Make Finder interactions through FinderSync extension on macOS
- [NXDRIVE-1146](https://jira.nuxeo.com/browse/NXDRIVE-1146): Drop module availability on PyPi
- [NXDRIVE-1162](https://jira.nuxeo.com/browse/NXDRIVE-1162): Update deploy scripts according to the new auto-update framework
- [NXDRIVE-1187](https://jira.nuxeo.com/browse/NXDRIVE-1187): Fix the PowerShell download command for Windows packaging
- [NXDRIVE-1202](https://jira.nuxeo.com/browse/NXDRIVE-1202): Upgrade to Python 2.7.15

### Tests
- [NXDRIVE-1078](https://jira.nuxeo.com/browse/NXDRIVE-1078): Create a pytest plugin for random bugs
- [NXDRIVE-1173](https://jira.nuxeo.com/browse/NXDRIVE-1173): Fix pip installation on Windows
- [NXDRIVE-1191](https://jira.nuxeo.com/browse/NXDRIVE-1191): Use Java OpenJDK instead of Java Oracle

#### Minor changes
- Auto-update: automatically install a new update if no bound engine
- CLI: Removed `--stop-on-error` argument
- Doc: Removed the "Microsoft Visual C++ Compiler for Python 2.7" requirement
- Framework: Use ecm:isVersion instead of ecm:isCheckedInVersion
- Jenkins: Possibility to launch the beta job on a given branch
- Jenkins: Possibility to launch the release job on a given beta version
- Jenkins: Update the Nuxeo snapshot to 10.2
- Packaging: Fix symlink creation in `deploy.sh`
- Packaging: Merged OS specific requirements-*.txt into one file
- Packaging: Added `pyaml` 17.12.1
- Packaging: Added `requests` 2.18.4
- Packaging: Removed `cffi`, will be installed with `xattr`
- Packaging: Removed `yappi`, useless on CI
- Packaging: Updated `Js2Py` from 0.58 to 0.59
- Packaging: Updated `faulthandler` from 3.0 to 3.1
- Packaging: Updated `psutil` from 5.4.3 to 5.4.4
- Packaging: Updated `pycryptodomex` from 3.5.1 to 3.6.1
- Packaging: Updated `pypac` from 0.4.0 to 0.8.1
- Packaging: Updated `pytest` from 3.3.2 to 3.5.1
- Packaging: Updated `python-dateutil` from 2.6.1 to 2.7.3
- Packaging: Updated `xattr` from 0.9.2 to 0.9.3
- Packaging: Upgraded `SIP` from 4.19.7 to 4.19.8
- Tracker: Removed the `Update` event


# 3.0.6
Release date: `2018-03-02`

### Core
- [NXDRIVE-1138](https://jira.nuxeo.com/browse/NXDRIVE-1138): Fix Direct Edit auto-lock on Windows 10


# 3.0.5
Release date: `2018-02-23`

### Core
- [NXDRIVE-941](https://jira.nuxeo.com/browse/NXDRIVE-941): Use a context manager for Lock
- [NXDRIVE-1008](https://jira.nuxeo.com/browse/NXDRIVE-1008): Document deleted server side when unfiltering and opened elsewhere
- [NXDRIVE-1009](https://jira.nuxeo.com/browse/NXDRIVE-1009): Some folders not deleted on client when file is open
- [NXDRIVE-1062](https://jira.nuxeo.com/browse/NXDRIVE-1062): Fix encoding for string comparisons on macOS
- [NXDRIVE-1085](https://jira.nuxeo.com/browse/NXDRIVE-1085): Review the Auto-Lock feature
- [NXDRIVE-1087](https://jira.nuxeo.com/browse/NXDRIVE-1087): Remove backward compatibility code for Nuxeo <= 5.8
- [NXDRIVE-1088](https://jira.nuxeo.com/browse/NXDRIVE-1088): Ignore Windows symlink suffix by default (.lnk)
- [NXDRIVE-1091](https://jira.nuxeo.com/browse/NXDRIVE-1091): Create the tooltip decorator
- [NXDRIVE-1098](https://jira.nuxeo.com/browse/NXDRIVE-1098): Auto-Lock does not work when there are orphans
- [NXDRIVE-1104](https://jira.nuxeo.com/browse/NXDRIVE-1104): Set invalid credentials on 401,403 errors only
- [NXDRIVE-1105](https://jira.nuxeo.com/browse/NXDRIVE-1105): Avoid unwanted file deletions on Windows 7
- [NXDRIVE-1114](https://jira.nuxeo.com/browse/NXDRIVE-1114): Add server information to analytics
- [NXDRIVE-1118](https://jira.nuxeo.com/browse/NXDRIVE-1118): Windows API used to trash files cannot deal with long paths

### GUI
- [NXDRIVE-1106](https://jira.nuxeo.com/browse/NXDRIVE-1106): Use new branding icons
- [NXDRIVE-1107](https://jira.nuxeo.com/browse/NXDRIVE-1107): Notify user of lost authenticated state during Direct Edit
- [NXDRIVE-1119](https://jira.nuxeo.com/browse/NXDRIVE-1119): Show "remaining items to sync" phrase before items number

### Tests
- [NXDRIVE-887](https://jira.nuxeo.com/browse/NXDRIVE-887): Integrate SonarCloud code quality check

#### Minor changes
- Doc: Add a link to know up-to-date envvars value
- Framework: Do not create test folder for case sensitivity in the Drive folder but in a temporary one
- Framework: Review BlackListQueue class
- Framework: Review DirectEdit class
- Framework: Review EngineNext class
- GUI: Use Web-UI as default value or in case of unknown selected UI for URLs generators
- Jenkins: Discard old builds
- Jenkins: Add a timeout to the packages job
- Packaging: Updated `Send2Trash` from 1.4.2 to 1.5.0
- Tests: Add a simple test for .rvt files
- Tests: Add -W error option to pytest
- Tests: Show failures summary


# 3.0.4
Release date: `2018-01-29`

**Important**: Dropped support for Nuxeo Platform 6.10.

### Core
- [NXDRIVE-836](https://jira.nuxeo.com/browse/NXDRIVE-836): Bad behaviors with read-only documents
- [NXDRIVE-1033](https://jira.nuxeo.com/browse/NXDRIVE-1033): File move operation fails, instead it creates duplicates
- [NXDRIVE-1075](https://jira.nuxeo.com/browse/NXDRIVE-1075): Review how TRACE level is added to loggers

### GUI
- [NXDRIVE-1069](https://jira.nuxeo.com/browse/NXDRIVE-1069): Show filters window on account creation
- [NXDRIVE-1070](https://jira.nuxeo.com/browse/NXDRIVE-1070): Show release notes before auto-upgrading to a new version
- [NXDRIVE-1072](https://jira.nuxeo.com/browse/NXDRIVE-1072): Show notification on document update via DirectEdit

#### Minor changes
- Framework: Review LocalWatcher class, better use of lock
- GUI: Re-enable the possibility to uncheck a root in the filters window
- Packaging: Upgraded `SIP` from 4.19.3 to 4.19.7
- Packaging: Updated `Js2Py` from 0.50 to 0.58
- Packaging: Updated `markdown` from 2.6.10 to 2.6.11
- Packaging: Updated `psutil` from 5.4.2 to 5.4.3
- Packaging: Updated `pytest` from 3.3.2 to 3.3.2
- Tests: Log messages are now less verbose ("thread module level message")
- Updater: Updated minimum server version from 5.6 to 7.10
- \[Windows\] Jenkins: Added `-direct` argument to the deploy script to prevent downloading any dependency


# 3.0.3
Release date: `2017-12-13`

### Core
- Partially revert "[NXDRIVE-1054](https://jira.nuxeo.com/browse/NXDRIVE-1054): Smart remote changes handling". See commit message for information.

### GUI
- [NXDRIVE-1063](https://jira.nuxeo.com/browse/NXDRIVE-1063): Add quotes to filenames and paths in translations
- [NXDRIVE-1064](https://jira.nuxeo.com/browse/NXDRIVE-1064): Better error message on corrupted file

#### Minor changes
- Packaging: Updated `psutil` from 5.4.1 to 5.4.2
- Packaging: Updated `pyobjc` from 4.0.1 to 4.1
- Packaging: Updated `pytest` from 3.2.5 to 3.3.1
- Packaging: Updated `pytest-timeout` from 1.2.0 to 1.2.1


# 3.0.2
Release date: `2017-12-07`

### Core
- [NXDRIVE-1059](https://jira.nuxeo.com/browse/NXDRIVE-1059): Wrong URL for the beta channel
- [NXDRIVE-1061](https://jira.nuxeo.com/browse/NXDRIVE-1061): Remote rename of an accentued folder fails on Windows


# 3.0.1 (unreleased)
Release date: `2017-12-07`

### Core
- [NXDRIVE-1037](https://jira.nuxeo.com/browse/NXDRIVE-1037): Ignore children of folder in duplicate error

#### Minor changes
- Tests: Refactor all de-duplication tests


# 3.0.0
Release date: `2017-12-04`

### Core
- [NXDRIVE-748](https://jira.nuxeo.com/browse/NXDRIVE-748): RemoteWatcher polling now uses timestamp instead of counter
- [NXDRIVE-968](https://jira.nuxeo.com/browse/NXDRIVE-968): Improve logs disk space usage (set level to DEBUG)
- [NXDRIVE-1019](https://jira.nuxeo.com/browse/NXDRIVE-1019): Retrieve the configuration from the server (**breaking change**)
- [NXDRIVE-1036](https://jira.nuxeo.com/browse/NXDRIVE-1036): Cannot unsync an accentued root
- [NXDRIVE-1038](https://jira.nuxeo.com/browse/NXDRIVE-1038): Don't quote parameters when acquiring a token
- [NXDRIVE-1040](https://jira.nuxeo.com/browse/NXDRIVE-1040): Handle documents that are indexed but inexistant
- [NXDRIVE-1046](https://jira.nuxeo.com/browse/NXDRIVE-1046): Review the LocalClient class
- [NXDRIVE-1054](https://jira.nuxeo.com/browse/NXDRIVE-1054): Smart remote changes handling
- [NXP-23113](https://jira.nuxeo.com/browse/NXP-23113): Add new DE and JA translations

### Doc
- [NXDRIVE-755](https://jira.nuxeo.com/browse/NXDRIVE-755): Update deployment documentation

### Tests
- [NXDRIVE-317](https://jira.nuxeo.com/browse/NXDRIVE-317): Test tmp directories are not cleaned up after tear down
- [NXDRIVE-1034](https://jira.nuxeo.com/browse/NXDRIVE-1034): Test folders containing dots
- [NXDRIVE-1035](https://jira.nuxeo.com/browse/NXDRIVE-1035): Update Nuxeo version to 9.10-SNAPSHOT
- [NXDRIVE-1039](https://jira.nuxeo.com/browse/NXDRIVE-1039): Align the test REST API client following [NXP-22542](https://jira.nuxeo.com/browse/NXP-22542)
- [NXDRIVE-1042](https://jira.nuxeo.com/browse/NXDRIVE-1042): Remove non-used jobs parameters
- [NXDRIVE-1045](https://jira.nuxeo.com/browse/NXDRIVE-1045): Fix tests tearDown generating a LoginException server-side
- [NXDRIVE-1047](https://jira.nuxeo.com/browse/NXDRIVE-1047): The setup stage from Jenkins job Drive-tests is useless
- [NXDRIVE-1049](https://jira.nuxeo.com/browse/NXDRIVE-1049): Better use of Mock objects in tests

#### Minor changes
- Packaging: Updated `Send2Trash` from 1.4.1 to 1.4.2
- Packaging: Updated `psutil` from 5.4.0 to 5.4.1
- Packaging: Updated `pyobjc` from 4.0 to 4.0.1
- Packaging: Updated `pypac` from 0.3.1 to 0.4.0
- Packaging: Updated `pytest` from 3.2.3 to 3.2.5
- Packaging: Better SIP check
- \[Windows\] Tests: Use `QT_PATH` and `MINGW_PATH` envars
- \[GNU/Linux\] Tests: Use `COMPILE_WITH_DEBUG` envar


# 2.5.9
Release date: `2017-11-08`

### Packaging / Build
- [NXDRIVE-1032](https://jira.nuxeo.com/browse/NXDRIVE-1032): Bypass PyPI upload


# 2.5.8
Release date: `2017-11-08`

#### Minor changes
- Packaging: Fix bad bash comparison in tools/release.sh to prevent PyPi upload


# 2.5.7
Release date: `2017-11-07`

### Core
- [NXDRIVE-903](https://jira.nuxeo.com/browse/NXDRIVE-903): Renaming folders/files does not sync while network interface is OFF
- [NXDRIVE-1026](https://jira.nuxeo.com/browse/NXDRIVE-1026): Retry in case of connection timeout

#### Minor changes
- Packaging: Do not upload to PyPi if Python < 2.7.13 (NXDRIVE-1027)
- Tests: Report is generated on failure only
- Tests: Less verbosity


# 2.5.6
Release date: `2017-11-02`

### Core
- [NXDRIVE-998](https://jira.nuxeo.com/browse/NXDRIVE-998): Fix behavior if the PAC URL is not reachable
- [NXDRIVE-1006](https://jira.nuxeo.com/browse/NXDRIVE-1006): Improve calls to /site/automation
- [NXDRIVE-1012](https://jira.nuxeo.com/browse/NXDRIVE-1012): Remote watcher is missing keywords
- [NXDRIVE-1013](https://jira.nuxeo.com/browse/NXDRIVE-1013): Fix and improve connection test for new account creation
- [NXDRIVE-1020](https://jira.nuxeo.com/browse/NXDRIVE-1020): Unlock Windows events queue capacity

### GUI
- [NXDRIVE-1004](https://jira.nuxeo.com/browse/NXDRIVE-1004): Dynamically select the JSF or Web UI URLs
- [NXDRIVE-1016](https://jira.nuxeo.com/browse/NXDRIVE-1016): Unity does not use left click in the systray
- [NXDRIVE-1018](https://jira.nuxeo.com/browse/NXDRIVE-1018): Use the user's browser to show the metadata window

### Packaging / Build
- [NXDRIVE-737](https://jira.nuxeo.com/browse/NXDRIVE-737): Use a single launcher
- [NXDRIVE-971](https://jira.nuxeo.com/browse/NXDRIVE-971): Uninstallation fails sometimes on Windows

### Tests
- [NXDRIVE-739](https://jira.nuxeo.com/browse/NXDRIVE-739): Refactor tests that use direct call to ndrive.py
- [NXDRIVE-984](https://jira.nuxeo.com/browse/NXDRIVE-984): Create a script to check any pip installation regressions

#### Minor changes
- Framework: Clean-up queue_manager.py
- Framework: Fix LocalClient.get_path() to use str.partition() and prevent IndexErrors
- GUI: Fix a SEGFAULT when closing the metadata window
- GUI: Add envar `USE_OLD_MENU` to force the use of the old menu
- Jenkins: The beta job now uploads the package to the PyPi server
- Packaging: Updated `psutil` from 5.3.1 to 5.4.0
- \[macOS\] Fix the favorite link creation
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
