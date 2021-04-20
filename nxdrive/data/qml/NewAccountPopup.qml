import QtQuick 2.15
// QtQuick.Dialogs has another unknown versioning
import QtQuick.Dialogs 1.3
import QtQuick.Layouts 1.15
import "icon-font/Icon.js" as MdiFont

NuxeoPopup {
    id: control
    width: 450
    height: 250
    padding: 20

    title: qsTr("NEW_ENGINE") + tl.tr

    onOpened: {
        folderInput.text = api.default_local_folder()
        urlInput.focus = true
    }

    contentItem: ColumnLayout {
        GridLayout {
            Layout.topMargin: 30  // NXDRIVE-2349: should be 20 here
            columns: 2
            rowSpacing: 20
            columnSpacing: 10

            Keys.onReturnPressed: connectButton.clicked()
            Keys.onEnterPressed: connectButton.clicked()

            // Server URL
            ScaledText { text: qsTr("URL") + tl.tr; color: mediumGray }
            NuxeoInput {
                id: urlInput
                Layout.fillWidth: true
                lineColor: acceptableInput ? focusedUnderline : errorContent
                inputMethodHints: Qt.ImhUrlCharactersOnly
                KeyNavigation.tab: folderInput
                placeholderText: "https://server.com/nuxeo"
                text: api.default_server_url_value()
                font.family: "Courier"
                validator: RegExpValidator { regExp: /^https?:\/\/[^\s<"\/]+\/[^\s<"]+$/ }
            }

            // Local folder
            ScaledText {
                text: qsTr("ENGINE_FOLDER") + tl.tr
                wrapMode: Text.WordWrap
                Layout.maximumWidth: control.width / 3
                Layout.preferredWidth: contentWidth
                color: mediumGray
            }

            // Free disk space based on the selected local folder
            RowLayout {
                Layout.fillWidth: true
                NuxeoInput {
                    id: folderInput
                    Layout.fillWidth: true
                    lineColor: focusedUnderline
                    onTextChanged: freeSpace.text = api.get_free_disk_space(folderInput.text)
                }

                IconLabel {
                    Layout.alignment: Qt.AlignRight
                    icon: MdiFont.Icon.folderOutline
                    onClicked: fileDialog.visible = true
                }
            }
            ScaledText {
                text: qsTr("FREE_DISK_SPACE") + tl.tr;
                color: mediumGray
            }
            ScaledText {
                id: freeSpace
                visible: folderInput.text
            }

            // Authentication method
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
                enabled: urlInput.acceptableInput && folderInput.text
                text: qsTr("CONNECT") + tl.tr

                onClicked: {
                    api.web_authentication(urlInput.text, folderInput.text, useLegacyAuth.checked)
                    control.close()
                }
            }
        }
    }

    FileDialog {
        id: fileDialog
        folder: shortcuts.home
        selectFolder: true
        onAccepted: folderInput.text = api.to_local_file(fileDialog.fileUrl)
    }
}
