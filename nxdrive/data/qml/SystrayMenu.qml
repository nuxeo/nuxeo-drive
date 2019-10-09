import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13

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
            visible: !api.restart_needed()

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

        SystrayMenuItem {
            // If the NXDRIVE_URL envar is set, use it (for testing purpose only!)
            visible: application._nxdrive_url_env() != ""
            text: "nxdrive://"
            onClicked: {
                application._handle_nxdrive_url(application._nxdrive_url_env())
            }
        }
    }
}
