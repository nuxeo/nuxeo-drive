import QtQuick 2.15
import QtQuick.Layouts 1.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control
    width: parent ? parent.width : 0
    height: authenticated ? 120 : 140
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
                columnSpacing: 50
                rowSpacing: 10
                anchors.fill: parent
                anchors.margins: 14

                // Server URL and Username
                ScaledText { text: remote_user; color: label; font.bold: true }
                Link {
                    text: server_url
                    onClicked: api.open_remote_server(uid)
                }

                // Server UI (Web-UI or JSF)
                ScaledText {
                    text: qsTr("SERVER_UI") + tl.tr
                    color: label
                }
                RowLayout {
                    id: uiSelect
                    spacing: 5
                    property string suffix: " (" + qsTr("SERVER_DEFAULT") + ")"

                    Connections {
                        target: EngineModel

                        function onUiChanged() {
                            webUiButton.defaultUi = (wui == "web")
                            jsfUiButton.defaultUi = (wui == "jsf")
                            webUiButton.checked = (forceUi == "web")
                            jsfUiButton.checked = (forceUi == "jsf")
                        }

                        function onAuthChanged() {
                            authenticated = !api.has_invalid_credentials(uid)
                        }
                    }

                    NuxeoRadioButton {
                        id: webUiButton
                        property bool defaultUi: (wui == "web")

                        text: "Web UI" + (defaultUi ? uiSelect.suffix : "")
                        onClicked: api.set_server_ui(uid, "web")
                        checked: (forceUi == "web")
                    }
                    NuxeoRadioButton {
                        id: jsfUiButton
                        property bool defaultUi: (wui == "jsf")

                        text: "JSF UI" + (defaultUi ? uiSelect.suffix : "")
                        onClicked: api.set_server_ui(uid, "jsf")
                        checked: (forceUi == "jsf")
                    }
                }

                // Conflicts/Errors
                ScaledText {
                    visible: sync_enabled
                    text: qsTr("CONFLICTS_AND_ERRORS") + tl.tr
                    color: label
                }
                Link {
                    visible: sync_enabled
                    text: qsTr("OPEN_WINDOW") + tl.tr
                    onClicked: api.show_conflicts_resolution(uid)
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
