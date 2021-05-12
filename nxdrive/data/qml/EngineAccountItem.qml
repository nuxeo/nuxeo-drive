import QtQuick 2.15
import QtQuick.Layouts 1.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    width: parent ? parent.width : 0
    height: authenticated ? 100 : 125
    property bool authenticated: !api.has_invalid_credentials(uid)
    property string forceUi: force_ui || wui
    property bool sync_enabled: feat_synchronization.enabled

    RowLayout {
        anchors.fill: parent
        anchors.rightMargin: 60

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            border.width: 1
            border.color: grayBorder
            radius: 10

            IconLabel {
                id: disconnectIcon
                icon: MdiFont.Icon.close
                tooltip: qsTr("DISCONNECT") + tl.tr
                iconColor: iconFailure
                onClicked: {
                    accountDeletion.open()
                }
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: 7
            }

            GridLayout {
                columns: 2
                rowSpacing: 10
                columnSpacing: 50
                anchors.fill: parent
                anchors.margins: 14

                // Server URL and Username
                ScaledText { text: remote_user; color: label; font.bold: true }
                Link {
                    text: server_url
                    onClicked: api.open_remote_server(uid)
                    width: parent.width
                }

                // Server UI (Web-UI or JSF)
                ScaledText {
                    text: qsTr("SERVER_UI") + tl.tr
                    color: label
                }
                RowLayout {
                    id: uiSelect
                    spacing: 5
                    Layout.fillWidth: true

                    Connections {
                        target: EngineModel

                        function onUiChanged(engineUid) {
                            if (engineUid != uid) return
                            control.forceUi = force_ui || wui
                            webUiButton.checked = (forceUi == "web")
                            jsfUiButton.checked = (forceUi == "jsf")
                        }

                        function onAuthChanged(engineUid) {
                            if (engineUid != uid) return
                            authenticated = !api.has_invalid_credentials(uid)
                        }
                    }

                    NuxeoRadioButton {
                        id: webUiButton

                        text: "Web UI"
                        onClicked: api.set_server_ui(uid, "web")
                        checked: (forceUi == "web")
                    }
                    NuxeoRadioButton {
                        id: jsfUiButton

                        text: "JSF UI"
                        onClicked: api.set_server_ui(uid, "jsf")
                        checked: (forceUi == "jsf")
                    }
                }

                // Conflicts/Errors
                ScaledText {
                    text: qsTr("CONFLICTS_AND_ERRORS") + tl.tr
                    color: label
                }
                Link {
                    text: qsTr("OPEN_WINDOW") + tl.tr
                    onClicked: api.show_conflicts_resolution(uid)
                    Layout.fillWidth: true
                }

                // Bad or outdated credentials
                ScaledText {
                    visible: !authenticated
                    text: qsTr("AUTH_EXPIRED") + tl.tr
                    color: errorContent
                }
                Link {
                    visible: !authenticated
                    text: qsTr("AUTH_UPDATE_ACTION") + tl.tr
                    color: errorContent
                    onClicked: api.web_update_token(uid)
                    Layout.fillWidth: true
                }
            }
        }
    }

    ConfirmPopup {
        id: accountDeletion
        message: qsTr("CONFIRM_DISCONNECT") + tl.tr
        cb_text: qsTr("PURGE_LOCAL_FILES").arg(APP_NAME).arg(folder) + tl.tr

        // Global variable to be able to get the checkbox state from ConfirmPopup.qml
        property bool purge_local_files: false

        onOk: {
            api.unbind_server(uid, purge_local_files)
        }
    }
}
