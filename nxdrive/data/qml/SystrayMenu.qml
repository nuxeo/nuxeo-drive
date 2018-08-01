import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3

ShadowRectangle {
    id: control
    visible: false
    width: menuContent.width
    height: menuContent.height
    color: lighterGray
    radius: 2
    spread: 0

    ColumnLayout {
        id: menuContent
        spacing: 0

        SystrayMenuItem {
            text: qsTr("SETTINGS") + tl.tr
            onClicked: {
                api.show_settings("General")
                control.visible = false
            }
        }
        SystrayMenuItem {
            text: qsTr("HELP") + tl.tr
            onClicked: {
                api.open_help()
                control.visible = false
            }
        }

        HorizontalSeparator { color: mediumGray }

        SystrayMenuItem {
            id: engineToggle
            property bool isPaused
            property string suspendAction: isPaused ? "RESUME": "SUSPEND"

            text: qsTr(suspendAction) + tl.tr
            onClicked: {
                api.suspend(isPaused)
                isPaused = !isPaused
                control.visible = false
            }
        }

        HorizontalSeparator { color: mediumGray }

        SystrayMenuItem {
            text: qsTr("QUIT") + tl.tr
            onClicked: {
                application.hide_systray()
                application.quit()
            }
        }
    }
}
