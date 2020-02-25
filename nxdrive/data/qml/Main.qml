import QtQuick 2.13
import QtQuick.Window 2.13
import SystrayWindow 1.0

QtObject {

    property var settingsWindow: Window {
        id: settingsWindow
        minimumWidth: 640
        minimumHeight: 540
        objectName: "settingsWindow"
        title: qsTr("SETTINGS_WINDOW_TITLE").arg(APP_NAME) + tl.tr
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

        signal appUpdate(string version)
        signal getLastFiles(string uid)
        signal setStatus(string sync, string error, string update)
        signal updateAvailable()
        signal updateProgress(int progress)

        onSetStatus: systray.setStatus(sync, error, update)
        onUpdateAvailable: systray.updateAvailable()
        onUpdateProgress: systray.updateProgress(progress)

        Systray {
            id: systray
            onAppUpdate: systrayWindow.appUpdate(version)
            onGetLastFiles: systrayWindow.getLastFiles(uid)
        }
    }

    property var conflictsWindow: Window {
        id: conflictsWindow
        objectName: "conflictsWindow"
        minimumWidth: 550
        minimumHeight: 600
        visible: false

        signal changed(string uid)
        signal setEngine(string uid)

        onSetEngine: conflicts.setEngine(uid)

        Conflicts {
            id: conflicts
            onChanged: conflictsWindow.changed(uid)
        }
    }
}
