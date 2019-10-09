import QtQuick 2.13
import QtQuick.Dialogs 1.3
import QtQuick.Layouts 1.13
import "icon-font/Icon.js" as MdiFont

NuxeoPopup {
    id: control
    width: 400 * ratio
    height: 250
    padding: 20

    title: qsTr("NEW_ENGINE") + tl.tr

    onOpened: {
        folderInput.text = api.default_local_folder()
        urlInput.focus = true
    }

    contentItem: ColumnLayout {
        GridLayout {
            Layout.topMargin: 20
            columns: 2
            rowSpacing: 20
            columnSpacing: 10

            Keys.onReturnPressed: connectButton.clicked()
            Keys.onEnterPressed: connectButton.clicked()

            ScaledText { text: qsTr("URL") + tl.tr; color: mediumGray }
            NuxeoInput {
                id: urlInput
                Layout.fillWidth: true
                lineColor: nuxeoBlue
                inputMethodHints: Qt.ImhUrlCharactersOnly
                KeyNavigation.tab: folderInput
                placeholderText: "your.nuxeo.platform.com"
                text: api.default_server_url_value()
                font.family: "monospace"
            }

            ScaledText {
                text: qsTr("ENGINE_FOLDER") + tl.tr
                wrapMode: Text.WordWrap
                Layout.maximumWidth: control.width / 3
                Layout.preferredWidth: contentWidth
                color: mediumGray
            }

            RowLayout {
                Layout.fillWidth: true
                NuxeoInput {
                    id: folderInput
                    Layout.fillWidth: true
                    lineColor: nuxeoBlue
                }

                IconLabel {
                    Layout.alignment: Qt.AlignRight
                    icon: MdiFont.Icon.folderOutline
                    onClicked: fileDialog.visible = true
                }
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight

            NuxeoButton {
                text: qsTr("CANCEL") + tl.tr
                lightColor: mediumGray
                darkColor: darkGray
                onClicked: control.close()
            }

            NuxeoButton {
                id: connectButton
                enabled: urlInput.text && folderInput.text
                inverted: true
                text: qsTr("CONNECT") + tl.tr

                onClicked: {
                    api.web_authentication(urlInput.text, folderInput.text)
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
