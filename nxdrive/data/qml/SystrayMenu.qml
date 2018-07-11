import QtQuick 2.10
import QtQuick.Controls 2.3

Menu {
    id: control

    topPadding: 2
    bottomPadding: 2

    onAboutToShow: engineToggle.isPaused = api.is_paused()

    SystrayMenuItem {
        text: qsTr("SETTINGS") + tl.tr
        onTriggered: api.show_settings("General")
    }
    SystrayMenuItem {
        text: qsTr("HELP") + tl.tr
        onTriggered: api.open_help()
    }

    MenuSeparator {
        contentItem: Rectangle {
            implicitWidth: control.width
            implicitHeight: 1
            color: lightGray
        }
    }

    SystrayMenuItem {
        id: engineToggle
        property bool isPaused
        property string suspendAction: isPaused ? "RESUME": "SUSPEND"

        text: qsTr(suspendAction) + tl.tr
        onTriggered: { api.suspend(isPaused); isPaused = !isPaused }
    }

    MenuSeparator {
        contentItem: Rectangle {
            implicitWidth: control.width
            implicitHeight: 1
            color: lightGray
        }
    }

    SystrayMenuItem {
        text: qsTr("QUIT") + tl.tr
        onTriggered: {
            systray.hide()
            application.quit()
        }
    }

    background: ShadowRectangle {
        implicitWidth: 100
        implicitHeight: contentHeight + 4
        color: lighterGray
        samples: 80
        radius: 2
        vOffset: 4
    }
}
