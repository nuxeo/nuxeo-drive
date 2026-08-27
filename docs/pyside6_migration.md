# PySide6 Migration

Last updated: 2026-08-27

## Status

The application Qt binding and the Direct Transfer flow now use PySide6 6.10.1. PyQt6 is no longer a runtime dependency.

This file is the migration ledger. Update it whenever another PySide6 migration task is completed, deferred, or validated.

## Completed

### Core binding

- Switched the top-level exports in `nxdrive/drive/qt/imports.py` from PyQt6 to PySide6.
- Replaced the `pyqtSignal`, `pyqtSlot`, `pyqtProperty`, and `pyqtBoundSignal` compatibility aliases and all call sites with PySide6's native `Signal`, `Slot`, `Property`, and `SignalInstance` names.
- Defined `QT_VERSION_STR` with `qVersion()` because PySide6 does not export `QT_VERSION_STR`.
- Moved `QFileSystemModel` to its PySide6 module, `QtWidgets`.
- Removed the unsupported `QVariant` export.
- Kept the existing `PySide` namespace temporarily for the dedicated Settings host.

### Settings/Features POC (NXDRIVE-3237)

- Integrated Anindya Roy's Settings Features-tab POC from commit `f22405ca1`.
- Added `PySideSettingsHost`, which lazily loads `Settings.qml` in a dedicated PySide6 `QQuickView` and routes `Application.show_settings()` to the requested Settings section.
- Added PySide6 adapters for the QML API, manager, OS integration, translator, engine model, language model, and feature models consumed by the Settings tabs and Add Account flow.
- Kept adapter objects alive for the QML context and relayed relevant model and message signals into the PySide6 object graph.
- Added the original secondary `PySide` namespace, mirrored constants, and PySide6 dependencies needed by the mixed-binding POC.
- The POC also moved the metrics consent dialog to PySide6; the later application-wide migration simplified that dialog to use the primary PySide6 imports directly.
- The application-wide migration made the cross-binding adapters redundant. Runtime Settings routing now uses the `settings_window` already instantiated by `Main.qml`; the adapter module remains pending deletion in a separate cleanup.

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
- Replaced the stacked `@Slot()`/`@if_frozen` decorators on the update notification callback with an in-slot frozen guard. Frozen builds converted the decorated callback to a `MetaFunction`, causing `Signal.connect()` to fail during startup after metrics consent.
- Disabled automatic Accounts Settings display during startup. Both constructor-time and event-loop-deferred `QWindow.show()` calls crashed frozen macOS builds in QV4 while evaluating the nested Settings QML window. Startup now continues so the systray remains available while Settings presentation is migrated separately.
- Registered the tray activation, systray focus-change, and custom-window visibility callbacks as explicit PySide6 slots. Frozen macOS builds crashed in `callPythonMetaMethod` when clicking the tray icon and focusing the QML window while these native signal targets were plain Python methods.
- Replaced the Windows-only five-`QQuickView` startup path with the shared `QQmlApplicationEngine`/`Main.qml` architecture and `QQuickWindow` subclasses. Frozen Windows stopped in the first `QQuickView.setSource(Conflicts.qml)` while its separate QML engine interacted with the Python translator.
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

- Use PySide6's native `Signal`, `Slot`, `Property`, and `SignalInstance` names throughout the application.
- Do not add a second `QApplication`, QML engine, or cross-binding adapters for Direct Transfer. All connected Qt objects use PySide6.
- Keep `pyside_settings_host.py` temporarily for follow-up cleanup, but do not instantiate it. Loading a second `Settings.qml` engine in a frozen build can deadlock while its QML worker waits for the GIL in the Python `QTranslator` override.

## Validation

Passed:

- Central shim smoke check: exported `QObject`, `QApplication`, signals, and Qt version are PySide6-backed.
- 113 focused Direct Transfer model and folder-dialog unit tests.
- 54 Alfresco OAuth bridge and macOS key-event tests.
- Settings routing unit tests passed, including generic section forwarding and the Add Account/error paths that reopen the `Accounts` section.
- Feature-state and feature-list unit tests passed as part of the complete unit matrix.
- A real PySide6 signal-to-slot regression test verifies that the update notification callback connects successfully and still honors frozen/non-frozen behavior.
- Settings routing tests verify that the existing `Main.qml` Settings window receives the requested section and is centered, without constructing a second QML engine.
- A startup regression test verifies that missing or invalid accounts do not show Settings during `Application.__init__` and that manager startup continues.
- Meta-object regression coverage verifies that all native tray/window callbacks are registered Qt slots with the expected signatures.
- Window inheritance and application tests verify that every platform uses `QQuickWindow` children owned by one application QML engine.
- Direct Transfer scheduling tests using `QDateTime.toPython()`.
- Offscreen load of `DirectTransferWindow.qml` with all six real PySide6 transfer models; the root instantiated as a `PySide6.QtQuick` object.
- Offscreen load of `Main.qml` with the real registered `CustomWindow` and `SystrayWindow` types; one `QQmlApplicationEngine` created all five named application windows.
- Complete common, Nuxeo, and Alfresco unit matrix under offscreen PySide6.
- Python compilation and focused flake8 validation for migration files.
- Source scan: no executable PyQt6 imports remain under `nxdrive`, `tests`, or `tools`.

The editor still reports pre-existing typing issues in `folders_dialog.py` and platform-conditional Windows code in `multi_folder_dialog.py`; the PySide6-specific `QDateTime` diagnostic was resolved.

The Settings host does not yet have a dedicated QML load or interaction smoke test in this migration. Its current validation is limited to routing, feature behavior, and the complete unit matrix.

Blocked by environment:

- Selected Nuxeo functional Application tests require a live server at `http://localhost:8080/nuxeo`; fixture setup failed before reaching the migrated Qt code.

## Remaining work

- Remove the now-unused `pyside_settings_host.py` adapters and secondary `PySide` namespace after confirming no downstream imports depend on them.
- Run the complete unit, functional, integration, type, lint, and packaging matrices in their normal CI environments.
- Perform manual macOS, Windows, and Linux checks for Direct Upload: open window, select remote folder, add files/folders, upload now, schedule upload, create remote folder, pause/resume/cancel, and inspect history/monitoring.
- Verify both PyInstaller products include the required PySide6 Qt plugins in release builds.
