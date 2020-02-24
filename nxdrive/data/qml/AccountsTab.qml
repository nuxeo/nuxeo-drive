import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control

    property bool hasAccounts: EngineModel.count > 0

    Connections {
        target: EngineModel
        onEngineChanged: {
            accountSelect.currentIndex = EngineModel.count - 1
            accountSelect.adaptWidth()
        }
    }

    // The accounts list
    Item {
        visible: hasAccounts

        anchors {
            top: parent.top
            left: parent.left
            topMargin: 40
            leftMargin: 30
        }

        GridLayout {
            columns: 3
            columnSpacing: 5

            // Account icon
            IconLabel {
                icon: MdiFont.Icon.account
                enabled: false
            }

            // Accounts label
            ScaledText { text: qsTr("SELECT_ACCOUNT") + tl.tr }

            // Dropdown list
            AccountsComboBox {
                id: accountSelect
                Layout.maximumWidth: 400
            }
        }
    }

    StackLayout {
        visible: hasAccounts
        currentIndex: accountSelect.currentIndex

        anchors {
            top: parent.top
            left: parent.left
            topMargin: 100
            leftMargin: 30
        }

        Repeater {
            id: accounts
            model: EngineModel
            delegate: GridLayout {
                columns: 2
                columnSpacing: 50
                rowSpacing: 20
                property bool authenticated: !api.has_invalid_credentials(uid)
                property string forceUi: force_ui || wui

                // Server URL
                ScaledText { text: qsTr("URL") + tl.tr; color: mediumGray }
                Link {
                    text: server_url
                    onClicked: api.open_remote_server(accountSelect.getRole("uid"))
                }

                // Server UI (Web-UI or JSF)
                ScaledText {
                    text: qsTr("SERVER_UI") + tl.tr
                    color: mediumGray
                    Layout.alignment: Qt.AlignTop
                }
                ColumnLayout {

                    Connections {
                        target: EngineModel
                        onUiChanged: {
                            webUiButton.defaultUi = (wui == "web")
                            jsfUiButton.defaultUi = (wui == "jsf")
                            webUiButton.checked = (forceUi == "web")
                            jsfUiButton.checked = (forceUi == "jsf")
                        }
                        onAuthChanged: authenticated = !api.has_invalid_credentials(uid)
                    }
                    id: uiSelect

                    property string suffix: " (" + qsTr("SERVER_DEFAULT") + ")"
                    spacing: 0
                    NuxeoRadioButton {
                        id: webUiButton
                        property bool defaultUi: (wui == "web")

                        text: "Web UI" + (defaultUi ? uiSelect.suffix : "")
                        onClicked: api.set_server_ui(uid, "web")
                        checked: (forceUi == "web")
                        Layout.alignment: Qt.AlignTop
                        Layout.topMargin: -10
                    }
                    NuxeoRadioButton {
                        id: jsfUiButton
                        property bool defaultUi: (wui == "jsf")

                        text: "JSF UI" + (defaultUi ? uiSelect.suffix : "")
                        onClicked: api.set_server_ui(uid, "jsf")
                        checked: (forceUi == "jsf")
                        Layout.alignment: Qt.AlignTop
                        Layout.topMargin: -5
                    }
                }

                // Local folder
                ScaledText {
                    text: qsTr("ENGINE_FOLDER") + tl.tr
                    visible: sync_enabled
                    color: mediumGray
                }
                Link {
                    text: folder
                    visible: sync_enabled
                    onClicked: api.open_local(accountSelect.getRole("uid"), "/")
                }

                // Disk space details
                ScaledText {
                    text: qsTr("STORAGE") + tl.tr;
                    color: mediumGray
                }
                Rectangle {
                        height: 18
                        width: 300
                        border.color: lighterGray
                        border.width: 4
                        radius: 2
                        Row {
                            height: parent.height - parent.border.width
                            anchors.fill: parent
                            anchors.leftMargin: 2
                            anchors.rightMargin: 2
                            anchors.bottomMargin: 2
                            anchors.topMargin: 2

                            property var disk_info: api.get_disk_space_info_to_width(accountSelect.getRole("uid"), folder, parent.width - parent.border.width)

                            RectangleTooltip {
                                color: nuxeoBlue;
                                width: parent.disk_info[2]
                                height: parent.height
                                tooltip: qsTr("DRIVE_DISK_SPACE_TOOLTIP").arg(api.get_drive_disk_space(accountSelect.getRole("uid"))) + tl.tr
                            }

                            RectangleTooltip {
                                color: lightGray;
                                width: parent.disk_info[1]
                                height: parent.height
                                tooltip: qsTr("USED_DISK_SPACE_TOOLTIP").arg(api.get_used_space_without_synced(accountSelect.getRole("uid"), folder)) + tl.tr
                            }

                            RectangleTooltip {
                                width: parent.disk_info[0]
                                height: parent.height
                                tooltip: qsTr("FREE_DISK_SPACE_TOOLTIP").arg(api.get_free_disk_space(folder)) + tl.tr
                            }

                        }
                }

                // Filters
                ScaledText {
                    text: qsTr("SELECTIVE_SYNC") + tl.tr
                    visible: sync_enabled
                    color: mediumGray
                    Layout.alignment: Qt.AlignTop
                }
                ColumnLayout {
                    visible: sync_enabled

                    ScaledText {
                        text: qsTr("SELECTIVE_SYNC_DESCR") + tl.tr
                        Layout.maximumWidth: 400
                        wrapMode: Text.WordWrap
                        color: mediumGray
                    }
                    Link {
                        text: qsTr("SELECT_SYNC_FOLDERS") + tl.tr
                        onClicked: api.filters_dialog(uid)
                    }
                }

                // Conflicts/Errors
                ScaledText {
                    visible: sync_enabled
                    text: qsTr("CONFLICTS_AND_ERRORS") + tl.tr
                    color: mediumGray
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
                    color: red
                }
                Link {
                    visible: !authenticated
                    text: qsTr("AUTH_UPDATE_ACTION") + tl.tr
                    color: red
                    onClicked: api.web_update_token(uid)
                }
            }
        }
    }

    ColumnLayout {
        id: noAccountPanel
        visible: !hasAccounts

        width: parent.width * 3/4
        anchors {
            horizontalCenter: parent.horizontalCenter
            top: parent.top
            topMargin: 100
        }

        IconLabel {
            icon: MdiFont.Icon.accountPlus
            size: 128; Layout.alignment: Qt.AlignHCenter
            onClicked: newAccountPopup.open()
        }

        ScaledText {
            text: qsTr("NO_ACCOUNT") + tl.tr
            font{
                pointSize: point_size * 1.2
                weight: Font.Bold
            }
            Layout.alignment: Qt.AlignHCenter
            wrapMode: Text.WordWrap
        }

        ScaledText {
            text: qsTr("NO_ACCOUNT_DESCR").arg(qsTr("NEW_ENGINE")) + tl.tr
            color: mediumGray
            Layout.maximumWidth: parent.width
            Layout.alignment: Qt.AlignHCenter
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }
    }

    RowLayout {
        width: parent.width - 60
        anchors {
            horizontalCenter: parent.horizontalCenter
            bottom: parent.bottom
            bottomMargin: 30
        }

        NuxeoButton {
            // Remove the account
            visible: hasAccounts
            text: qsTr("DISCONNECT") + tl.tr
            color: red
            onClicked: accountDeletion.open()
        }

        NuxeoButton {
            // Add a new account
            Layout.alignment: Qt.AlignRight
            text: qsTr("NEW_ENGINE") + tl.tr
            color: hasAccounts ? mediumGray : nuxeoBlue
            inverted: !hasAccounts
            onClicked: newAccountPopup.open()
        }
    }

    NewAccountPopup { id: newAccountPopup }

    ConfirmPopup {
        id: accountDeletion
        message: qsTr("CONFIRM_DISCONNECT") + tl.tr
        okColor: red

        // Global variable to be able to get the checkbox state from ConfirmPopup.qml
        property bool purge_local_files: false

        onOk: {
            api.unbind_server(accountSelect.getRole("uid"), purge_local_files)
            accountSelect.currentIndex = 0
        }
    }
}
