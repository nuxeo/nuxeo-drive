import QtQuick
// QtQuick.Dialogs is available in Qt 6.2+
import QtQuick.Dialogs
import QtQuick.Layouts
import "../../../drive/data/qml/icon-font/Icon.js" as MdiFont
import "../../../drive/data/qml"

NuxeoPopup {
    id: control
    width: 480
    padding: 20

    title: qsTr("NEW_ENGINE") + tl.tr

    Component.onCompleted: {
        height = Qt.binding(function() {
            return popupContent.implicitHeight + topPadding + bottomPadding
        })
    }

    onOpened: {
        folderInput.text = api.default_server_local_folder()
        urlInput.focus = true
    }

    contentItem: ColumnLayout {
        id: popupContent
        spacing: 20

        ColumnLayout {
            id: formFields
            Layout.fillWidth: true
            Layout.topMargin: 30
            spacing: 20
            Keys.onReturnPressed: connectButton.clicked()
            Keys.onEnterPressed: connectButton.clicked()

            ColumnLayout {
                id: server_url
                Layout.fillWidth: true
                spacing: 10

                ScaledText { text: qsTr("URL") + tl.tr; color: secondaryText }
                NuxeoInput {
                    id: urlInput
                    Layout.fillWidth: true
                    Layout.leftMargin: 25
                    lineColor: acceptableInput ? focusedUnderline : errorContent
                    inputMethodHints: Qt.ImhUrlCharactersOnly
                    KeyNavigation.tab: folderInput
                    placeholderText: "https://server.com"
                    text: api.default_server_url_value()
                    font.family: "Courier"
                    onAccepted: connectButton.clicked()
                    validator: RegularExpressionValidator { regularExpression: /^https?:\/\/[^\s<"\/]+(\/[^\s<"]*)?$/ }
                }
            }

            ColumnLayout {
                id: local_folder
                Layout.fillWidth: true
                spacing: 10

                RowLayout {
                    spacing: 10

                    ScaledText {
                        text: qsTr("ENGINE_FOLDER") + tl.tr
                        wrapMode: Text.WordWrap
                        Layout.maximumWidth: control.width / 3
                        Layout.preferredWidth: contentWidth
                        color: secondaryText
                    }
                    IconLabel {
                        Layout.alignment: Qt.AlignRight
                        icon: MdiFont.Icon.folderOutline
                        onClicked: fileDialog.open()
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 25
                    spacing: 20

                    NuxeoInput {
                        id: folderInput
                        Layout.fillWidth: true
                        lineColor: focusedUnderline
                        onAccepted: connectButton.clicked()
                        onTextChanged: {
                            var disk_space = api.get_free_disk_space(folderInput.text)
                            freeSpace.text = qsTr("FREE_DISK_SPACE").arg(disk_space) + tl.tr
                        }
                    }
                    ScaledText {
                        id: freeSpace
                        visible: folderInput.text
                        color: secondaryText
                    }
                }
            }

            RowLayout {
                id: authMethodRow
                spacing: 10

                ScaledText {
                    text: qsTr("USE_LEGACY_AUTH") + tl.tr
                    color: mediumGray
                }
                NuxeoCheckBox {
                    id: useLegacyAuth
                    checked: true
                    leftPadding: 0
                }
            }

            Column {
                id: credentials
                Layout.fillWidth: true
                width: parent.width
                spacing: 10

                ScaledText { text: qsTr("USERNAME") + tl.tr; color: secondaryText }
                NuxeoInput {
                    id: usernameInput
                    x: 25
                    width: parent.width - 25
                    height: Math.max(implicitHeight, 24)
                    placeholderText: "admin"
                    KeyNavigation.tab: passwordInput
                    onAccepted: connectButton.clicked()
                }

                ScaledText { text: qsTr("PASSWORD") + tl.tr; color: secondaryText }
                NuxeoInput {
                    id: passwordInput
                    x: 25
                    width: parent.width - 25
                    height: Math.max(implicitHeight, 24)
                    echoMode: TextInput.Password
                    KeyNavigation.tab: connectButton
                    onAccepted: connectButton.clicked()
                }
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight

            NuxeoButton {
                text: qsTr("CANCEL") + tl.tr
                primary: false
                onClicked: control.close()
            }

            NuxeoButton {
                id: connectButton
                enabled: {
                    if (!urlInput.acceptableInput || !folderInput.text)
                        return false
                    return usernameInput.text.length > 0 && passwordInput.text.length > 0
                }
                text: qsTr("CONNECT") + tl.tr

                onClicked: {
                    if (useLegacyAuth.checked) {
                        api.password_auth(
                            folderInput.text,
                            urlInput.text,
                            usernameInput.text,
                            passwordInput.text
                        )
                    } else {
                        api.oauth2_password_auth(
                            folderInput.text,
                            urlInput.text,
                            usernameInput.text,
                            passwordInput.text
                        )
                    }
                    control.close()
                }
            }
        }
    }

    FolderDialog {
        id: fileDialog
        currentFolder: api.default_server_local_folder()
        onAccepted: folderInput.text = api.to_local_file(fileDialog.selectedFolder)
    }
}
