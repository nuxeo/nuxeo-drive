import QtQuick 2.3
import QtQuick.Window 2.2
import SystrayWindow 1.0

QtObject {

    property var settingsWindow: Window {
        id: settingsWindow
        objectName: "settingsWindow"
        title: qsTr("SETTINGS_WINDOW_TITLE") + tl.tr
        width: settings.width; height: settings.height
        visible: false

        signal setMessage(string msg, string type)
        signal setSection(int index)

        onSetMessage: settings.setMessage(msg, type)
        onSetSection: settings.setSection(index)

        Settings { id: settings }
    }

    property var systrayWindow: SystrayWindow {
        id: systrayWindow
        objectName: "systrayWindow"
        width: systray.width; height: systray.height
        visible: false
        flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Popup

        signal getLastFiles(string uid)
        signal setStatus(string state, string message, string submessage)

        onSetStatus: systray.setStatus(state, message, submessage)

        Systray {
            id: systray
            onGetLastFiles: systrayWindow.getLastFiles(uid)
        }
    }

    property var conflictsWindow: Window {
        id: conflictsWindow
        objectName: "conflictsWindow"
        width: conflicts.width; height: conflicts.height
        visible: false

        signal changed()
        signal setEngine(string uid)

        onSetEngine: conflicts.setEngine(uid)

        Conflicts {
            id: conflicts
            onChanged: conflictsWindow.changed()
        }
    }
}
