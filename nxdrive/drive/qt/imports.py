"""
Central Qt-binding shim used across the project.

Primary binding: **PySide6**. All top-level names re-exported by this module
come from PySide6 and drive the entire application (systray, sync engines,
workers, Direct Transfer, Direct Edit, task manager, and every other window).

Native PySide6 signal, slot, and property names are exported directly.
The ``PySide`` namespace at the bottom remains available to the settings host
until its now-redundant adapter layer is removed separately.
"""

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QCoreApplication,
    QDate,
    QDateTime,
    QDir,
    QEvent,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QRegularExpression,
    QRunnable,
    QSize,
    Qt,
    QThread,
    QThreadPool,
    QTime,
    QTimer,
    QTranslator,
    QUrl,
    Property,
    Signal,
    SignalInstance,
    Slot,
    qVersion,
)
from PySide6.QtGui import (
    QCursor,
    QDesktopServices,
    QFont,
    QFontMetricsF,
    QIcon,
    QIntValidator,
    QKeyEvent,
    QPixmap,
    QRegularExpressionValidator,
    QStandardItem,
    QStandardItemModel,
    QValidator,
    QWindow,
)
from PySide6.QtNetwork import (
    QAbstractSocket,
    QHostAddress,
    QHostInfo,
    QLocalServer,
    QLocalSocket,
    QSslSocket,
    QTcpServer,
    QTcpSocket,
)
from PySide6.QtQml import QQmlApplicationEngine, QQmlContext, qmlRegisterType
from PySide6.QtQuick import QQuickView, QQuickWindow
from PySide6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFileSystemModel,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QTimeEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# PySide6 namespace — retained for the existing settings-host adapters.
#
# Access via ``from nxdrive.drive.qt.imports import PySide as ps`` and use
# ``ps.QDialog``, ``ps.Signal``, ``ps.QQmlApplicationEngine`` etc.
# ---------------------------------------------------------------------------
from PySide6 import QtCore as _ps_QtCore
from PySide6 import QtGui as _ps_QtGui
from PySide6 import QtQml as _ps_QtQml
from PySide6 import QtQuick as _ps_QtQuick
from PySide6 import QtWidgets as _ps_QtWidgets

QT_VERSION_STR = qVersion()


class PySide:
    """Curated PySide6 symbols for the POC windows (Share Debug Info,
    Settings, Add Account tab).

    Only the names actually needed by those windows are exposed. Add more as
    additional windows opt in.
    """

    # QtCore
    QObject = _ps_QtCore.QObject
    Qt = _ps_QtCore.Qt
    QUrl = _ps_QtCore.QUrl
    QTimer = _ps_QtCore.QTimer
    QAbstractListModel = _ps_QtCore.QAbstractListModel
    QModelIndex = _ps_QtCore.QModelIndex
    QByteArray = _ps_QtCore.QByteArray
    QSize = _ps_QtCore.QSize
    Signal = _ps_QtCore.Signal
    Slot = _ps_QtCore.Slot
    Property = _ps_QtCore.Property
    SignalInstance = _ps_QtCore.SignalInstance

    # QtGui
    QIcon = _ps_QtGui.QIcon
    QPixmap = _ps_QtGui.QPixmap

    # QtWidgets — Share Debug Info dialog
    QApplication = _ps_QtWidgets.QApplication
    QDialog = _ps_QtWidgets.QDialog
    QVBoxLayout = _ps_QtWidgets.QVBoxLayout
    QLabel = _ps_QtWidgets.QLabel
    QCheckBox = _ps_QtWidgets.QCheckBox
    QDialogButtonBox = _ps_QtWidgets.QDialogButtonBox

    # QtQml + QtQuick — Settings window (hosts Add Account tab)
    QQmlApplicationEngine = _ps_QtQml.QQmlApplicationEngine
    QQmlContext = _ps_QtQml.QQmlContext
    qmlRegisterType = _ps_QtQml.qmlRegisterType
    QQuickWindow = _ps_QtQuick.QQuickWindow
    QQuickView = _ps_QtQuick.QQuickView


__all__ = (
    "PySide",
    "QAbstractListModel",
    "QAbstractSocket",
    "QApplication",
    "QByteArray",
    "QCalendarWidget",
    "QCheckBox",
    "QComboBox",
    "QCoreApplication",
    "QCursor",
    "QDate",
    "QDateTime",
    "QDesktopServices",
    "QDialog",
    "QDialogButtonBox",
    "QDir",
    "QEvent",
    "QFileDialog",
    "QFileSystemModel",
    "QFrame",
    "QFont",
    "QFontMetricsF",
    "QGroupBox",
    "QHBoxLayout",
    "QHostAddress",
    "QHostInfo",
    "QIcon",
    "QIntValidator",
    "QItemSelectionModel",
    "QKeyEvent",
    "QLabel",
    "QLineEdit",
    "QListWidget",
    "QListWidgetItem",
    "QLocalServer",
    "QLocalSocket",
    "QMenu",
    "QMessageBox",
    "QModelIndex",
    "QObject",
    "QPixmap",
    "QPoint",
    "QPushButton",
    "QQmlApplicationEngine",
    "QQmlContext",
    "QQuickView",
    "QQuickWindow",
    "QRect",
    "QRegularExpression",
    "QRegularExpressionValidator",
    "QRunnable",
    "QSize",
    "QSizePolicy",
    "QSpacerItem",
    "QSslSocket",
    "QStandardItem",
    "QStandardItemModel",
    "QStyle",
    "QSystemTrayIcon",
    "QT_VERSION_STR",
    "QTcpServer",
    "QTcpSocket",
    "QTextEdit",
    "QThread",
    "QThreadPool",
    "QTime",
    "QTimeEdit",
    "QTimer",
    "QTranslator",
    "QTreeView",
    "QUrl",
    "QValidator",
    "QVBoxLayout",
    "QWidget",
    "QWindow",
    "Qt",
    "Property",
    "Signal",
    "SignalInstance",
    "Slot",
    "qmlRegisterType",
)
