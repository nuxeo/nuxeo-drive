import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Dialogs 1.3
import QtQuick.Layouts 1.3
import QtQuick.Window 2.2
import QtWebEngine 1.0
import "icon-font/Icon.js" as MdiFont

Rectangle {
    id: control

    property var currentAccount //: accountListView.currentItem.accountData
    property bool invalidCredentials: false
    signal pickAccount(var account)

    onPickAccount: {
        if (currentAccount == undefined) {
            // trick to display the selected UI value right away
            var idx = 0
            while (idx < uiSelect.model.count) {
                var ui = account.forceUi || account.ui
                if (uiSelect.model.get(idx).value == ui) {
                    uiSelect.currentIndex = idx
                    break
                }
                idx++
            }
        }
        currentAccount = account
        if (api.has_invalid_credentials(currentAccount.uid)) {
            control.invalidCredentials = true
        } else {
            control.invalidCredentials = false
        }
    }

    FontLoader {
        id: iconFont
        source: "icon-font/materialdesignicons-webfont.ttf"
    }

    Rectangle {
        id: content
        anchors.fill: parent

        Rectangle {
            // Left panel for account list
            id: accountList
            width: 150; height: parent.height
            color: lightGray
            anchors {
                left: parent.left
                top: parent.top
            }
            InfoLabel { 
                text: qsTr("SECTION_ACCOUNTS") + tl.tr
                anchors {
                    left: accountListView.left
                    top: parent.top
                    topMargin: 20
                } 
            }
            ListView {
                id: accountListView
                width: parent.width * 3/4; height: parent.height - 100
                anchors.centerIn: parent
                spacing: 10
                model: EngineModel

                Component.onCompleted: control.pickAccount(currentItem.accountData)

                delegate: HoverRectangle {
                    id: wrapper

                    property variant accountData: model
                    color: "transparent"
                    width: parent.width; height: 30

                    onClicked: {
                        accountListView.currentIndex = index
                        control.pickAccount(accountData)
                    }

                    NuxeoToolTip {
                        visible: accountName.truncated && hovered
                        text: server
                    }
                    
                    Text {
                        id: accountName
                        width: parent.width
                        elide: Text.ElideRight
                        text: server
                        font.pointSize: 16
                        anchors.centerIn: parent
                        horizontalAlignment: Text.AlignLeft
                        verticalAlignment: Text.AlignVCenter
                    }

                    Rectangle {
                        width: accountName.contentWidth; height: 2
                        color: nuxeoBlue
                        visible: wrapper.ListView.isCurrentItem
                        anchors {
                            top: accountName.bottom
                            left: accountName.left
                        }
                    }
                }
            }

            HoverRectangle {
                // Add a new account
                width: accountListView.width * 3/4; height: 20
                color: "transparent"

                Text {
                    text: "+ " + qsTr("NEW_ENGINE") + tl.tr
                    color: mediumGray
                    font {
                        weight: Font.Normal
                        pointSize: 16
                    }
                    anchors.verticalCenter: parent.verticalCenter
                }

                anchors {
                    top: accountListView.top
                    topMargin: Math.min(accountListView.contentHeight, accountListView.height) + 10
                    left: accountListView.left
                }
                onClicked: newAccountPopup.open()
            }
        }

        Rectangle {
            // Right panel that shows the account info:
            // server url, username, path to local folder, UI
            width: parent.width - 150; height: parent.height
            anchors.left: accountList.right

            Column {
                id: accountInfo
                width: parent.width - 100; height: parent.height - 100
                anchors {
                    horizontalCenter: parent.horizontalCenter
                    top: parent.top
                    topMargin: 20
                }
                spacing: 15

                InfoLabel { text: qsTr("URL") + tl.tr }
                Text { text: currentAccount.url }

                HorizontalSeparator {}
                
                InfoLabel { text: qsTr("USERNAME") + tl.tr }
                Text { text: currentAccount.username }

                HorizontalSeparator {}

                InfoLabel { text: qsTr("ENGINE_FOLDER") + tl.tr }
                Text { text: currentAccount.folder }
                
                HorizontalSeparator {}

                InfoLabel { text: qsTr("SERVER_UI") + tl.tr }

                NuxeoComboBox {
                    id: uiSelect
                    property string suffix: " (" + qsTr("SERVER_DEFAULT") + ")"

                    width: 200
                    textRole: "type"
                    
                    displayText: currentText + (model.get(currentIndex).value == currentAccount.ui ? suffix : "")

                    model: ListModel {
                        ListElement { type: "JSF UI"; value: "jsf" }
                        ListElement { type: "Web UI"; value: "web" }
                    }
                    
                    delegate: ItemDelegate {
                        width: uiSelect.width
                        contentItem: Text {
                            text: type + (currentAccount.ui == value ? uiSelect.suffix : "")
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }
                        highlighted: uiSelect.currentIndex === index
                    }
                    Component.onCompleted: console.log(currentAccount.ui)
                    onActivated: {
                        console.log(uiSelect.currentIndex)
                        var ui = uiSelect.model.get(uiSelect.currentIndex).value
                        api.set_server_ui(currentAccount.uid, ui)
                    }
                }
            }

            Rectangle {
                id: reconnectContainer
                width: reconnectLabel.width + reconnectButton.width + 40
                height: 40
                visible: control.invalidCredentials
                anchors {
                    left: accountInfo.left
                    bottom: accountInfo.bottom
                }

                Text {
                    id: reconnectLabel
                    text: qsTr("UNAUTHORIZED") + tl.tr
                    color: red
                    font.pointSize: 16
                    anchors {
                        left: parent.left
                        verticalCenter: parent.verticalCenter
                        leftMargin: 10
                    }
                }
                NuxeoButton {
                    // reconnect when credentials are invalid
                    id: reconnectButton
                    text: qsTr("CONNECT") + tl.tr
                    lightColor: red; darkColor: red
                    size: 14

                    anchors {
                        left: reconnectLabel.right
                        verticalCenter: parent.verticalCenter
                        leftMargin: 20
                    }
                    onClicked: api.web_update_token(currentAccount.uid)
                }
            }

            NuxeoButton {
                // show and select sync folders
                id: selectFolders

                text: qsTr("SELECT_SYNC_FOLDERS") + tl.tr
                size: 14
                inverted: true

                anchors {
                    left: accountInfo.left
                    top: reconnectContainer.bottom
                }
                onClicked: api.filters_dialog(currentAccount.uid)
            }

            NuxeoButton {
                // Remove the account
                id: removeAccountButton

                text: qsTr("DISCONNECT") + tl.tr
                lightColor: mediumGray
                darkColor: red
                size: 14

                anchors {
                    left: selectFolders.right
                    top: reconnectContainer.bottom
                    leftMargin: 40
                }
                onClicked: accountDeletion.open()
            }

            Rectangle {
                // When there's no account, show a message
                id: noAccount
                anchors.fill: parent
                visible: EngineModel.count == 0

                Text {
                    width: parent.width * 3/5
                    text: "No account yet, add one by clicking on the +"
                    color: mediumGray
                    wrapMode: Text.WordWrap
                    horizontalAlignment:  Text.AlignHCenter
                    font.pointSize: 30

                    anchors.centerIn: parent
                }
            }
        }
    }
    
    NewAccountPopup { id: newAccountPopup }

    ConfirmPopup {
        id: accountDeletion
        message: qsTr("CONFIRM_DISCONNECT") + tl.tr
        onOk: api.unbind_server(currentAccount.uid)
    }
}