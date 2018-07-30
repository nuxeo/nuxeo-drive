import QtQuick 2.3
import QtQuick.Window 2.2

QtObject {

    property var settingsWindow: Settings {
        id: settings
        objectName: "settingsWindow"
        visible: false
    }

    property var systrayWindow: Systray {
        id: systray
        objectName: "systrayWindow"
        visible: false
    }

    property var conflictsWindow: Conflicts {
        id: conflicts
        objectName: "conflictsWindow"
        visible: true
    }
}