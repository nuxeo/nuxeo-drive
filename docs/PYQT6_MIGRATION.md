# PyQt5 to PyQt6 Migration Guide

This document outlines the changes made when migrating Nuxeo Drive from PyQt5 to PyQt6, along with important notes for maintainers.

## Overview

PyQt6 introduces several breaking changes compared to PyQt5. This migration guide documents the key differences and how they've been addressed in the codebase.

## Key Changes

### 1. Import Statements

All imports have been updated from `PyQt5` to `PyQt6`:

```python
# Before (PyQt5)
from PyQt5.QtCore import Qt, QObject
from PyQt5.QtWidgets import QApplication

# After (PyQt6)
from PyQt6.QtCore import Qt, QObject
from PyQt6.QtWidgets import QApplication
```

### 2. QRegExp Removed - Use QRegularExpression

PyQt6 has removed `QRegExp` and `QRegExpValidator` in favor of `QRegularExpression` and `QRegularExpressionValidator`.

**Migration in this codebase:**
- All imports are centralized in `nxdrive/qt/imports.py`
- Compatibility aliases have been added:
  ```python
  QRegExp = QRegularExpression
  QRegExpValidator = QRegularExpressionValidator
  ```

**For maintainers:**
- When writing new code, prefer using `QRegularExpression` directly
- The old `QRegExp` API is different from `QRegularExpression` - review usage carefully if adding new regex code
- Key differences:
  - Pattern syntax: PCRE (Perl-Compatible) vs Qt's simplified syntax
  - API methods: `exactMatch()` vs `match()` with different return types

### 3. Enum Access

PyQt6 requires explicit enum access. The codebase already uses the modern approach:

```python
# Correct (works in both PyQt5 and PyQt6)
Qt.AlignmentFlag.AlignCenter
Qt.Key.Key_Escape

# Old style (doesn't work in PyQt6)
Qt.AlignCenter
Qt.Key_Escape
```

All enum constants in `nxdrive/qt/constants.py` follow the explicit access pattern.

### 4. QtWebKit Removed

PyQt6 has removed QtWebKit. If your code needs web rendering:
- Use `QtWebEngineWidgets` (based on Chromium)
- Or use QML with WebView

**Current status:** Nuxeo Drive does not use QtWebKit, so no migration needed.

### 5. Signal and Slot Signatures

PyQt6 is stricter about signal/slot type matching:

```python
# Ensure signal signatures match slot signatures
mySignal = pyqtSignal(int, str)  # Must connect to slots accepting (int, str)
```

### 6. QVariant Removed

In PyQt6, `QVariant` is largely removed. Python types are used directly:

```python
# Before (PyQt5)
value = QVariant(42)

# After (PyQt6)
value = 42  # Direct Python type
```

**Note:** The codebase still imports `QVariant` for backwards compatibility, but direct Python types should be preferred.

### 7. File Dialog Changes

The `getOpenFileName()` and similar methods return different types:

```python
# PyQt5
filename, _ = QFileDialog.getOpenFileName(...)

# PyQt6 (same API, but implementation differs)
filename, _ = QFileDialog.getOpenFileName(...)
```

The API is the same, but be aware of potential behavioral differences.

## Package Changes

### Dependencies Updated

| PyQt5 Package | PyQt6 Replacement |
|---------------|-------------------|
| `pyqt5==5.15.10` | `PyQt6==6.8.1` |
| `pyqt5-sip==12.17.0` | `PyQt6-sip==13.9.1` |
| `PyQt5-Qt5==5.15.x` | `PyQt6-Qt6==6.8.1` |
| `pyqt5-stubs==5.15.6.0` | `PyQt6-stubs==6.5.0.240813` |

### Platform-Specific Considerations

#### Windows
- Qt6 Bluetooth DLLs path changed: `PyQt6\Qt6\bin\Qt6Bluetooth.dll` (was `PyQt5\Qt\bin\Qt5Bluetooth.dll`)

#### macOS
- Qt6 framework paths changed: `PyQt6/Qt6/qml/...` (was `PyQt5/Qt/qml/...`)
- The `fix_app_qt_folder_names_for_codesign.py` script has been updated accordingly

#### Linux
- No specific migration notes

## Testing

After migration, ensure to test:

1. **GUI functionality**: All dialogs, windows, and UI elements
2. **Signals and slots**: All connections work correctly
3. **File dialogs**: Open/save dialogs function properly
4. **System tray**: Icons and notifications work
5. **Regular expressions**: If using regex patterns, verify they work with QRegularExpression

## Common Pitfalls

### 1. Implicit Enum Values

```python
# Will fail in PyQt6
if alignment == Qt.AlignCenter:  # NameError

# Correct
if alignment == Qt.AlignmentFlag.AlignCenter:
```

### 2. QRegExp Pattern Syntax

QRegularExpression uses PCRE syntax, which differs from QRegExp:

```python
# QRegExp (Qt syntax)
pattern = QRegExp("*.txt")

# QRegularExpression (PCRE syntax)
pattern = QRegularExpression(r".*\.txt")
```

### 3. QVariant Type Checking

```python
# PyQt5 style (don't use in new code)
if isinstance(value, QVariant):
    value = value.value()

# PyQt6 style (preferred)
# Just use Python types directly
```

### 4. Exec_ Method Renamed

```python
# PyQt5
app.exec_()
dialog.exec_()

# PyQt6
app.exec()
dialog.exec()
```

**Note:** Check if the codebase uses `exec_()` and update to `exec()` if needed.

## Future Considerations

1. **Type Hints**: Consider adding more specific type hints now that PyQt6 has better typing support
2. **QML**: If expanding QML usage, review PyQt6's QML API changes
3. **Web Engine**: If adding web functionality, use QtWebEngineWidgets
4. **Async Support**: PyQt6 has better asyncio integration - consider for future features

## References

- [PyQt6 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [PyQt5 to PyQt6 Migration Guide](https://www.riverbankcomputing.com/static/Docs/PyQt6/pyqt5_differences.html)
- [Qt6 Changes](https://doc.qt.io/qt-6/portingguide.html)

## Rollback Procedure

If issues arise and rollback is needed:

1. Revert changes to `tools/deps/requirements.txt`
2. Revert changes to `nxdrive/qt/imports.py`
3. Revert test file imports
4. Revert deployment script changes
5. Run `pip install -r tools/deps/requirements.txt` to restore PyQt5

## Support

For questions or issues related to this migration, please:
1. Check this migration guide
2. Review the PyQt6 documentation
3. Consult the development team
