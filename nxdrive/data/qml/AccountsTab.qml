import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3
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

    Item {
        visible: hasAccounts

        anchors {
            top: parent.top
            left: parent.left
            topMargin: 40
            leftMargin: 30
        }

        ScaledText { text: qsTr("ACCOUNT_NAME") + tl.tr; color: mediumGray }

        AccountsComboBox {
            id: accountSelect
            anchors {
                left: parent.left
                leftMargin: 185
            }
        }
    }

    StackLayout {
        visible: hasAccounts
        currentIndex: accountSelect.currentIndex

        anchors {
            top: parent.top
            left: parent.left
            topMargin: 70
            leftMargin: 30
        }

        Repeater {
            id: accounts
            model: EngineModel
            delegate: GridLayout {
                columns: 2
                columnSpacing: 50
                rowSpacing: 20
                ScaledText { text: qsTr("URL") + tl.tr; color: mediumGray }
                ScaledText { text: url }

                ScaledText {
                    text: qsTr("SERVER_UI") + tl.tr
                    color: mediumGray
                    Layout.alignment: Qt.AlignTop
                }

                ColumnLayout {

                    Connections {
                        target: EngineModel
                        onUiChanged: {
                            webUiButton.defaultUi = (ui == "web")
                            jsfUiButton.defaultUi = (ui == "jsf")
                            webUiButton.checked = (forceUi == "web")
                            jsfUiButton.checked = (forceUi == "jsf")
                        }
                    }
                    id: uiSelect

                    property string suffix: " (" + qsTr("SERVER_DEFAULT") + ")"
                    spacing: 0
                    NuxeoRadioButton {
                        id: webUiButton
                        property bool defaultUi: (ui == "web")

                        text: "Web UI" + (defaultUi ? uiSelect.suffix : "")
                        onClicked: api.set_server_ui(uid, "web")
                        checked: (forceUi == "web")
                        Layout.alignment: Qt.AlignTop
                        Layout.leftMargin: -8
                        Layout.topMargin: -10
                    }
                    NuxeoRadioButton {
                        id: jsfUiButton
                        property bool defaultUi: (ui == "jsf")

                        text: "JSF UI" + (defaultUi ? uiSelect.suffix : "")
                        onClicked: api.set_server_ui(uid, "jsf")
                        checked: (forceUi == "jsf")
                        Layout.alignment: Qt.AlignTop
                        Layout.leftMargin: -8
                        Layout.topMargin: -5
                    }
                }

                ScaledText { text: qsTr("ENGINE_FOLDER") + tl.tr; color: mediumGray }
                ScaledText { text: folder }

                ScaledText {
                    text: qsTr("SELECTIVE_SYNC") + tl.tr
                    color: mediumGray
                    Layout.alignment: Qt.AlignTop
                }

                ColumnLayout {
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
            pointSize: 14; font.weight: Font.Bold
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
        onOk: {
            api.unbind_server(accountSelect.getRole("uid"))
            accountSelect.currentIndex = 0
        }
    }
}
