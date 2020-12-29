"""
Put here all PyQt constants used across the project.
"""
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtNetwork import QAbstractSocket, QLocalServer
from PyQt5.QtWidgets import (
    QDialogButtonBox,
    QLineEdit,
    QMessageBox,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
)

AA_EnableHighDpiScaling = Qt.ApplicationAttribute.AA_EnableHighDpiScaling
AcceptRole = QMessageBox.ButtonRole.AcceptRole
ActionRole = QDialogButtonBox.ButtonRole.ActionRole
AlignCenter = Qt.AlignmentFlag.AlignCenter
AlignHCenter = Qt.AlignmentFlag.AlignHCenter
AlignVCenter = Qt.AlignmentFlag.AlignVCenter
Apply = QDialogButtonBox.StandardButton.Apply
BusyCursor = Qt.CursorShape.BusyCursor
Cancel = QDialogButtonBox.StandardButton.Cancel
Checked = Qt.CheckState.Checked
ConnectedState = QAbstractSocket.SocketState.ConnectedState
Critical = QMessageBox.Icon.Critical
Drawer = Qt.WindowType.Drawer
FixedPixelWidth = QTextEdit.LineWrapMode.FixedPixelWidth
FocusOut = QEvent.Type.FocusOut
FramelessWindowHint = Qt.WindowType.FramelessWindowHint
Horizontal = Qt.Orientation.Horizontal
IPv4Protocol = QAbstractSocket.NetworkLayerProtocol.IPv4Protocol
Information = QMessageBox.Icon.Information
ItemIsEditable = Qt.ItemFlag.ItemIsEditable
ItemIsEnabled = Qt.ItemFlag.ItemIsEnabled
ItemIsSelectable = Qt.ItemFlag.ItemIsSelectable
LeftToRight = Qt.LayoutDirection.LeftToRight
MiddleClick = QSystemTrayIcon.ActivationReason.MiddleClick
MouseButtonPress = QEvent.Type.MouseButtonPress
Ok = QDialogButtonBox.StandardButton.Ok
PartiallyChecked = Qt.CheckState.PartiallyChecked
Password = QLineEdit.EchoMode.Password
Popup = Qt.WindowType.Popup
Question = QMessageBox.Icon.Question
RejectRole = QMessageBox.ButtonRole.RejectRole
RichText = Qt.TextFormat.RichText
SP_DialogCloseButton = QStyle.StandardPixmap.SP_DialogCloseButton
SP_FileDialogInfoView = QStyle.StandardPixmap.SP_FileDialogInfoView
SP_MessageBoxQuestion = QStyle.StandardPixmap.SP_MessageBoxQuestion
Selected = QIcon.Mode.Selected
Trigger = QSystemTrayIcon.ActivationReason.Trigger
Unchecked = Qt.CheckState.Unchecked
UserRole = Qt.ItemDataRole.UserRole
WA_DeleteOnClose = Qt.WidgetAttribute.WA_DeleteOnClose
WaitCursor = Qt.CursorShape.WaitCursor
Warning = QSystemTrayIcon.MessageIcon.Warning
WindowStaysOnTopHint = Qt.WindowType.WindowStaysOnTopHint
WorldAccessOption = QLocalServer.SocketOption.WorldAccessOption
