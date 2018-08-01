import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
import QtQuick.Window 2.2
import "icon-font/Icon.js" as MdiFont

Item {
    id: systray
    width: Screen.width; height: Screen.height
    state: ""

    property bool hasAccounts: EngineModel.count > 0
    property string stateMessage
    property string stateSubMessage

    signal getLastFiles(string uid)
    signal hide()
    signal setStatus(string state, string message, string submessage)
    signal setTrayPosition(int x, int y)

    Connections {
        target: EngineModel
        onEngineChanged: accountSelect.currentIndex = EngineModel.count - 1
    }

    onSetStatus:  {
        systray.state = state
        systray.stateMessage = message
        systray.stateSubMessage = submessage
    }

    onSetTrayPosition: {
        systrayContainer.x = x
        systrayContainer.y = y
    }

    MouseArea {
        width: parent.width; height: parent.height
        anchors.centerIn: parent
        onClicked: systray.hide()
    }

    FontLoader {
        id: iconFont
        source: "icon-font/materialdesignicons-webfont.ttf"
    }

    ColumnLayout {
        id: systrayContainer
        visible: hasAccounts

        width: 300; height: 370
        z: 5; spacing: 0

        Rectangle {
            Layout.fillWidth: true
            color: lighterGray
            height: 50; z: 10

            RowLayout {
                anchors.fill: parent

                IconLabel {
                    Layout.alignment: Qt.AlignRight
                    icon: MdiFont.Icon.accountOutline
                }

                ColumnLayout {
                    Layout.alignment: Qt.AlignLeft

                    AccountsComboBox {
                        id: accountSelect
                        // When picking an account, run the refresh timer (without repeat)
                        // to update the last files list.
                        onActivated: refreshTimer.running = true
                    }

                    ScaledText {
                        text: accountSelect.getRole("url")
                        pointSize: 10
                        color: mediumGray
                    }
                }

                IconLabel {
                    icon: MdiFont.Icon.openInNew
                    Layout.alignment: Qt.AlignRight; Layout.rightMargin: 4
                    onClicked: api.open_remote(accountSelect.getRole("uid"))

                }

                IconLabel {
                    icon: MdiFont.Icon.folder; size: 24
                    Layout.alignment: Qt.AlignLeft
                    onClicked: api.open_local(accountSelect.getRole("uid"), "/")
                }

                IconLabel {
                    id: settingsContainer
                    icon: MdiFont.Icon.dotsVertical
                    Layout.alignment: Qt.AlignLeft

                    onClicked: contextMenu.open()

                    SystrayMenu {
                        id: contextMenu
                        x: settingsContainer.width - width
                        y: settingsContainer.height
                    }
                }

            }
        }

        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true

            Timer {
                id: refreshTimer
                interval: 1000; running: false; repeat: false
                onTriggered: systray.getLastFiles(accountSelect.getRole("uid"))
            }

            ListView {
                id: recentFiles
                anchors.fill: parent

                clip: true
                delegate: SystrayFile {}
                model: FileModel
                highlight: Rectangle { color: lighterGray }

                ScrollBar.vertical: ScrollBar {}
            }
        }

        HoverRectangle {
            id: systrayBottom
            color: lighterGray
            Layout.fillWidth: true; height: 40
            opacity: 1

            RowLayout {
                anchors.fill: parent

                Item { Layout.fillWidth: true }

                ColumnLayout {
                    spacing: 0

                    ScaledText {
                        id: statusText
                        text: qsTr("SYNCHRONIZATION_COMPLETED") + tl.tr
                        color: mediumGray
                        Layout.alignment: Qt.AlignRight
                    }

                    ScaledText {
                        id: statusSubText
                        visible: text
                        color: statusText.color
                        pointSize: 10
                        opacity: 0.8
                        Layout.alignment: Qt.AlignRight
                    }
                }

                IconLabel {
                    id: statusIcon
                    icon: MdiFont.Icon.check
                    Layout.alignment: Qt.AlignRight
                    Layout.rightMargin: 10

                    SequentialAnimation on rotation {
                        id: syncAnim
                        running: false
                        loops: Animation.Infinite; alwaysRunToEnd: true
                        NumberAnimation { from: 360; to: 0; duration: 1000; easing.type: Easing.InOutQuad }
                        PauseAnimation { duration: 250 }
                    }
                }
            }
            ProgressBar {
                id: updateProgress
                width: parent.width
                anchors.bottom: parent.bottom
                visible: false
                indeterminate: value == 0
                from: 0; to: 100
            }
        }
    }

    Rectangle {
        visible: !hasAccounts
        width: systrayContainer.width
        height: systrayContainer.height
        x: systrayContainer.x
        y: systrayContainer.y
        z: 5
        color: "white"

        ColumnLayout {
            width: parent.width * 3/4
            anchors.centerIn: parent

            IconLabel {
                icon: MdiFont.Icon.accountPlus
                size: 96; Layout.alignment: Qt.AlignHCenter
            }

            ScaledText {
                text: qsTr("NO_ACCOUNT") + tl.tr
                font.weight: Font.Bold
                pointSize: 14
                Layout.maximumWidth: parent.width
                Layout.alignment: Qt.AlignHCenter
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }

            Link {
                text: qsTr("OPEN_SETTINGS") + tl.tr
                pointSize: 14
                Layout.maximumWidth: parent.width
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 50
                onClicked: api.show_settings("Accounts")
            }

            Link {
                text: qsTr("QUIT") + tl.tr
                pointSize: 14
                Layout.maximumWidth: parent.width
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 10
                onClicked: {
                    systray.hide()
                    application.quit()
                }
            }
        }
    }

    states: [
        State {
            name: "suspended"
            PropertyChanges { target: statusIcon; icon: MdiFont.Icon.pause }
            PropertyChanges { target: statusText; text: qsTr("ENGINE_PAUSED") + tl.tr }
        },
        State {
            name: "syncing"
            PropertyChanges { target: statusIcon; icon: MdiFont.Icon.sync }
            PropertyChanges { target: statusText; text: qsTr("SYNCHRONIZATION_ITEMS_LEFT").arg(FileModel.count) + tl.tr }
            PropertyChanges { target: refreshTimer; repeat: true; running: true }
            PropertyChanges { target: syncAnim; running: true }
        },
        State {
            name: "update"
            PropertyChanges {
                target: updatePopup
                version: stateMessage
                channel: stateSubMessage
            }
            PropertyChanges {
                target: systrayBottom
                color: lightBlue
                onClicked: updatePopup.open()
            }
            PropertyChanges {
                target: statusIcon
                icon: MdiFont.Icon.update
                color: "white"
            }
            PropertyChanges {
                target: statusText
                text: qsTr("NOTIF_UPDATE_TITLE") + tl.tr
                color: "white"
            }
        },
        State {
            name: "updating"
            PropertyChanges {
                target: systrayBottom
                color: lightBlue
            }
            PropertyChanges {
                target: statusIcon
                icon: MdiFont.Icon.update
                color: "white"
            }
            PropertyChanges {
                target: statusText
                text: qsTr("UPDATING_VERSION").arg(stateMessage) + tl.tr
                color: "white"
            }
            PropertyChanges {
                target: updateProgress
                visible: true
                value: parseInt(stateSubMessage)
            }
        },
        State {
            name: "conflicted"
            PropertyChanges {
                target: systrayBottom
                color: orange
                onClicked: api.show_conflicts_resolution(accountSelect.getRole("uid"))
            }
            PropertyChanges {
                target: statusIcon
                icon: MdiFont.Icon.alert
                color: "white"
            }
            PropertyChanges {
                target: statusText
                text: qsTr("CONFLICTS_SYSTRAY").arg(stateMessage) + tl.tr
                color: "white"
            }
        },
        State {
            name: "auth_expired"
            PropertyChanges {
                target: systrayBottom
                color: red
                onClicked: api.web_update_token(accountSelect.getRole("uid"))
            }
            PropertyChanges {
                target: statusIcon
                icon: MdiFont.Icon.alert
                color: "white"
            }
            PropertyChanges {
                target: statusText
                text: qsTr("AUTH_EXPIRED") + tl.tr
                color: "white"
            }
            PropertyChanges {
                target: statusSubText
                text: qsTr("AUTH_UPDATE_ACTION") + tl.tr
            }
        },
        State {
            name: "downgrade"
            PropertyChanges {
                target: updatePopup
                version: stateMessage
                channel: stateSubMessage
            }
            PropertyChanges {
                target: systrayBottom
                color: red
                onClicked: updatePopup.open()
            }
            PropertyChanges {
                target: statusIcon
                icon: MdiFont.Icon.alert
                color: "white"
            }
            PropertyChanges {
                target: statusText
                text: qsTr("NOTIF_UPDATE_DOWNGRADE").arg(stateMessage) + tl.tr
                color: "white"
            }
        },
        State {
            name: "error"
            PropertyChanges {
                target: systrayBottom
                color: red
                onClicked: api.show_conflicts_resolution(accountSelect.getRole("uid"))
            }
            PropertyChanges {
                target: statusIcon
                icon: MdiFont.Icon.alert
                color: "white"
            }
            PropertyChanges {
                target: statusText
                text: qsTr("ERRORS_SYSTRAY").arg(stateMessage) + tl.tr
                color: "white"
            }
        }
    ]

    ConfirmPopup {
        id: updatePopup
        property string version
        property string channel

        message: qsTr("CONFIRM_UPDATE_MESSAGE").arg(channel).arg(version) + tl.tr
        onOk: api.app_update(version)
    }
}
