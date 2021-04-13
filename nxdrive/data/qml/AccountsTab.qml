import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control

    property bool hasAccounts: EngineModel.count > 0

    Connections {
        target: EngineModel

        function onEngineChanged() {
            accountSelect.currentIndex = EngineModel.count - 1
            accountSelect.adaptWidth()
        }
    }

    // The accounts list
    Item {
        visible: hasAccounts
        id: accountSelection

        anchors {
            top: parent.top
            left: parent.left
            topMargin: 40
            leftMargin: 30
        }

        // User selection
        ScaledText { text: qsTr("USERNAME") + tl.tr; color: label }
        GridLayout {
            columns: 2

            anchors {
                left: parent.left
                leftMargin: 185
            }

            // Account icon
            IconLabel {
                icon: MdiFont.Icon.accountCircle
                iconColorDisabled: primaryBg
                enabled: false
            }

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
            top: accountSelection.bottom
            left: parent.left
            topMargin: 35
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
                property bool sync_feature_enabled: feat_synchronization.enabled
                property string forceUi: force_ui || wui


                // Server URL
                ScaledText { text: qsTr("URL") + tl.tr; color: label }
                Link {
                    text: server_url
                    onClicked: api.open_remote_server(accountSelect.getRole("uid"))
                }

                // Server UI (Web-UI or JSF)
                ScaledText {
                    text: qsTr("SERVER_UI") + tl.tr
                    color: label
                    Layout.alignment: Qt.AlignTop
                }
                ColumnLayout {

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
                    visible: sync_feature_enabled
                    color: label
                }
                Link {
                    text: folder
                    visible: sync_feature_enabled
                    onClicked: api.open_local(accountSelect.getRole("uid"), "/")
                }

                // Disk space details
                ScaledText {
                    text: qsTr("STORAGE") + tl.tr;
                    color: label
                }
                Rectangle {
                    height: 20
                    width: 350
                    border.color: progressFilled
                    border.width: 1
                    radius: 2
                    Row {
                        anchors.fill: parent
                        anchors.margins: 2

                        property var disk_info: api.get_disk_space_info_to_width(accountSelect.getRole("uid"), folder, width)

                        RectangleTooltip {
                            color: interactiveLink;
                            width: parent.disk_info[2]
                            height: parent.height
                            tooltip: "%1\n%2".arg(APP_NAME).arg(api.get_drive_disk_space(accountSelect.getRole("uid")))
                        }

                        RectangleTooltip {
                            color: disabledText;
                            width: parent.disk_info[1]
                            height: parent.height
                            tooltip: qsTr("OTHER") + "\n%1".arg(api.get_used_space_without_synced(accountSelect.getRole("uid"), folder)) + tl.tr
                        }

                        RectangleTooltip {
                            width: parent.disk_info[0]
                            height: parent.height
                            tooltip: qsTr("AVAILABLE") + "\n%1".arg(api.get_free_disk_space(folder)) + tl.tr
                        }
                    }
                }

                // Filters
                ScaledText {
                    text: qsTr("SELECTIVE_SYNC") + tl.tr
                    visible: sync_feature_enabled
                    color: label
                    Layout.alignment: Qt.AlignTop
                }
                ColumnLayout {
                    visible: sync_feature_enabled

                    ScaledText {
                        text: qsTr("SELECTIVE_SYNC_DESCR") + tl.tr
                        Layout.maximumWidth: 400
                        wrapMode: Text.WordWrap
                        color: secondaryText
                    }
                    Link {
                        text: qsTr("SELECT_SYNC_FOLDERS") + tl.tr
                        onClicked: api.filters_dialog(uid)
                    }
                }

                // Conflicts/Errors
                ScaledText {
                    visible: sync_feature_enabled
                    text: qsTr("CONFLICTS_AND_ERRORS") + tl.tr
                    color: label
                }
                Link {
                    visible: sync_feature_enabled
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
            primary: false
            onClicked: accountDeletion.open()
        }

        NuxeoButton {
            // Add a new account
            Layout.alignment: Qt.AlignRight
            text: qsTr("NEW_ENGINE") + tl.tr
            onClicked: newAccountPopup.open()
        }
    }

    NewAccountPopup { id: newAccountPopup }

    ConfirmPopup {
        id: accountDeletion
        message: qsTr("CONFIRM_DISCONNECT") + tl.tr
        cb_text: qsTr("PURGE_LOCAL_FILES").arg(APP_NAME).arg(accountSelect.getRole("folder")) + tl.tr

        // Global variable to be able to get the checkbox state from ConfirmPopup.qml
        property bool purge_local_files: false

        onOk: {
            api.unbind_server(accountSelect.getRole("uid"), purge_local_files)
            accountSelect.currentIndex = 0
        }
    }
}
