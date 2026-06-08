import QtQuick
// QtQuick.Dialogs is available in Qt 6.2+
import QtQuick.Dialogs
import QtQuick.Layouts
import "icon-font/Icon.js" as MdiFont

NuxeoPopup {
    id: control
    width: 480
    height: 180 + server_url.height + local_folder.height + (alfrescoCredentials.visible ? alfrescoCredentials.height + 20 : 0)
    padding: 20

    title: qsTr("NEW_ENGINE") + tl.tr

    // Detect if the URL points to an Alfresco server
    property bool isAlfresco: !urlInput.text.replace(/\/+$/, "").endsWith("/nuxeo")

    onIsAlfrescoChanged: {
        folderInput.text = control.isAlfresco ? api.default_alfresco_local_folder() : api.default_local_folder()
    }

    onOpened: {
        folderInput.text = control.isAlfresco ? api.default_alfresco_local_folder() : api.default_local_folder()
        urlInput.focus = true
    }

    contentItem: ColumnLayout {
        spacing: 20

        ColumnLayout {
            Layout.topMargin: 30  // NXDRIVE-2349: should be 20 here
            spacing: 20
            Keys.onReturnPressed: connectButton.clicked()
            Keys.onEnterPressed: connectButton.clicked()

            // Server URL
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
                    placeholderText: "https://server.com/nuxeo or https://server.com"
                    text: api.default_server_url_value()
                    font.family: "Courier"
                    validator: RegularExpressionValidator { regularExpression: /^https?:\/\/[^\s<"\/]+(\/[^\s<"]*)?$/ }
                }
            }

            // Local folder
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

            // Authentication method
            RowLayout {
                spacing: 10

                ScaledText {
                    text: qsTr("USE_LEGACY_AUTH") + tl.tr;
                    color: mediumGray
                }
                NuxeoCheckBox {
                    id: useLegacyAuth
                    checked: true
                    leftPadding: 0
                }
            }

            // Username/password fields for Alfresco (both basic and OAuth2)
            ColumnLayout {
                id: alfrescoCredentials
                visible: control.isAlfresco
                Layout.fillWidth: true
                spacing: 10

                ScaledText { text: qsTr("USERNAME") + tl.tr; color: secondaryText }
                NuxeoInput {
                    id: usernameInput
                    Layout.fillWidth: true
                    Layout.leftMargin: 25
                    placeholderText: "admin"
                    KeyNavigation.tab: passwordInput
                }

                ScaledText { text: qsTr("PASSWORD") + tl.tr; color: secondaryText }
                NuxeoInput {
                    id: passwordInput
                    Layout.fillWidth: true
                    Layout.leftMargin: 25
                    echoMode: TextInput.Password
                    KeyNavigation.tab: connectButton
                }
            }
        }

        // Cancel/Connect buttons
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
                    // For Alfresco, always require username and password
                    if (control.isAlfresco)
                        return usernameInput.text.length > 0 && passwordInput.text.length > 0
                    return true
                }
                text: qsTr("CONNECT") + tl.tr

                onClicked: {
                    if (control.isAlfresco && useLegacyAuth.checked) {
                        // Alfresco basic auth: bind directly with credentials
                        api.alfresco_basic_auth(
                            folderInput.text,
                            urlInput.text,
                            usernameInput.text,
                            passwordInput.text
                        )
                    } else if (control.isAlfresco && !useLegacyAuth.checked) {
                        // Alfresco OAuth2: password grant with credentials
                        api.alfresco_oauth2_auth(
                            folderInput.text,
                            urlInput.text,
                            usernameInput.text,
                            passwordInput.text
                        )
                    } else {
                        api.web_authentication(urlInput.text, folderInput.text, useLegacyAuth.checked)
                    }
                    control.close()
                }
            }
        }
    }

    FolderDialog {
        id: fileDialog
        currentFolder: api.default_local_folder()
        onAccepted: folderInput.text = api.to_local_file(fileDialog.selectedFolder)
    }
}
