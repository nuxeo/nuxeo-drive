# PySide6 Migration

Last updated: 2026-08-21

## Status

The application Qt binding and the Direct Transfer flow now use PySide6 6.10.1. PyQt6 is no longer a runtime dependency.

This file is the migration ledger. Update it whenever another PySide6 migration task is completed, deferred, or validated.

## Completed

### Core binding

- Switched the top-level exports in `nxdrive/drive/qt/imports.py` from PyQt6 to PySide6.
- Kept `pyqtSignal`, `pyqtSlot`, `pyqtProperty`, and `pyqtBoundSignal` as compatibility aliases for `Signal`, `Slot`, `Property`, and `SignalInstance`.
- Defined `QT_VERSION_STR` with `qVersion()` because PySide6 does not export `QT_VERSION_STR`.
- Moved `QFileSystemModel` to its PySide6 module, `QtWidgets`.
- Removed the unsupported `QVariant` export.
- Kept the existing `PySide` namespace temporarily for the dedicated Settings host.

### Direct Transfer flow

- Kept `DirectTransferWindow.qml`, `DirectTransfer.qml`, `DirectDownloadTab.qml`, and their delegates unchanged; their Qt 6 QML APIs are binding-independent.
- Updated folder tree loaders to store Python objects directly with `QStandardItem.setData()` instead of wrapping them in `QVariant`.
- Updated `DirectTransferModel` and `ActiveSessionModel` to emit a list of role IDs through `dataChanged` instead of a role-name dictionary.
- Replaced the PyQt-only `QDateTime.toPyDateTime()` scheduling conversion with PySide6's `QDateTime.toPython()`.
- Confirmed that `Application`, `QMLDriveApi`, Direct Transfer models, `Engine`, `FoldersDialog`, `FolderTreeView`, `MultiFolderDialog`, `ScheduleDialog`, and `NewFolderDialog` now receive Qt types from the same PySide6 shim.

### Signal and lifecycle compatibility

- Converted the overloaded `directEditError` declaration to PySide6 tuple syntax.
- Registered constructor-connected `Engine` and `Manager` methods as explicit Qt slots.
- Aligned `Engine._check_sync_start` with the positional object emitted by its queue signal.
- Simplified the metrics consent dialog to use the primary PySide6 imports instead of the legacy secondary namespace.
- Updated worker tests to request direct signal delivery when they call worker methods without starting the worker's assigned `QThread`.
- Replaced unsafe test patching of inherited PySide6 C++ virtual methods with Python subclass overrides.

### Tests and tooling

- Changed direct test imports and patch targets from PyQt6 to PySide6 or `nxdrive.drive.qt.imports`.
- Changed the shared test event-loop fixture to create a `QApplication`, preventing a prior `QCoreApplication` singleton from aborting later QWidget tests.
- Removed `pyqt6`, `pyqt6-sip`, `PyQt6-Qt6`, and `pyqt6-stubs` from `tools/deps/requirements.txt`.
- Updated POSIX and Windows installation checks to require PySide6.
- Removed the Windows deployment workaround that deleted PyQt6 Bluetooth binaries.

## Compatibility decisions

- Keep the existing `pyqt*` names as aliases for now. Renaming every call site would add churn without changing behavior.
- Do not add a second `QApplication`, QML engine, or cross-binding adapters for Direct Transfer. All connected Qt objects use PySide6.
- Leave the dedicated `PySideSettingsHost` adapter architecture in place for this change. It is now redundant, but simplifying Settings is a separate behavior surface.

## Validation

Passed:

- Central shim smoke check: exported `QObject`, `QApplication`, signals, and Qt version are PySide6-backed.
- 113 focused Direct Transfer model and folder-dialog unit tests.
- 54 Alfresco OAuth bridge and macOS key-event tests.
- Direct Transfer scheduling tests using `QDateTime.toPython()`.
- Offscreen load of `DirectTransferWindow.qml` with all six real PySide6 transfer models; the root instantiated as a `PySide6.QtQuick` object.
- Complete common, Nuxeo, and Alfresco unit matrix under offscreen PySide6.
- Python compilation and focused flake8 validation for migration files.
- Source scan: no executable PyQt6 imports remain under `nxdrive`, `tests`, or `tools`.

The editor still reports pre-existing typing issues in `folders_dialog.py` and platform-conditional Windows code in `multi_folder_dialog.py`; the PySide6-specific `QDateTime` diagnostic was resolved.

Blocked by environment:

- Selected Nuxeo functional Application tests require a live server at `http://localhost:8080/nuxeo`; fixture setup failed before reaching the migrated Qt code.

## Remaining work

- Simplify or remove `PySideSettingsHost` mirror objects now that the main application uses PySide6. Its `pyqt_*` variable names describe the old architecture but remain functional.
- Run the complete unit, functional, integration, type, lint, and packaging matrices in their normal CI environments.
- Perform manual macOS, Windows, and Linux checks for Direct Upload: open window, select remote folder, add files/folders, upload now, schedule upload, create remote folder, pause/resume/cancel, and inspect history/monitoring.
- Verify both PyInstaller products include the required PySide6 Qt plugins in release builds.
