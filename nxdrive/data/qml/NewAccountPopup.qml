import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Dialogs 1.3
import QtQuick.Window 2.2
import "icon-font/Icon.js" as MdiFont

Popup {
    id: control

    width: 400
    height: 300
    x: (parent.width - width) / 2
    y: (parent.height - height) / 2
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    
    background: ShadowRectangle { border.width: 0 }
    
    onOpened: {
        usernameInput.clear()
        // urlInput.clear()
        // folderInput.clear()
        usernameInput.focus = true
    }

    NuxeoInput {
        id: usernameInput
        width: parent.width * 3/4; height: 20
        placeholderText: qsTr("NAME") + tl.tr
        lineColor: nuxeoBlue
        KeyNavigation.tab: urlInput

        anchors {
            horizontalCenter: parent.horizontalCenter
            top: parent.top
            topMargin: 40
        }
    }
    
    NuxeoInput {
        id: urlInput
        width: parent.width * 3/4; height: 20
        placeholderText: qsTr("URL") + tl.tr
        lineColor: nuxeoBlue
        inputMethodHints: Qt.ImhUrlCharactersOnly
        KeyNavigation.tab: folderInput
        text: "http://localhost:8080"

        anchors {
            horizontalCenter: parent.horizontalCenter
            top: usernameInput.bottom
            topMargin: 30
        }
    }

    NuxeoInput {
        id: folderInput
        width: parent.width * 3/4 - 40; height: 20
        placeholderText: qsTr("ENGINE_FOLDER") + tl.tr
        lineColor: nuxeoBlue
        text: api.get_default_nuxeo_drive_folder()

        anchors {
            left: urlInput.left
            top: urlInput.bottom
            topMargin: 30
        }
    }

    HoverRectangle {
        width: 20; height: 20
        IconLabel { icon: MdiFont.Icon.folderOutline }
        onClicked: {
            fileDialog.visible = true
        }
        anchors {
            bottom: folderInput.bottom
            right: urlInput.right
            rightMargin: 5
        }
    }

    NuxeoButton {
        id: addAccountButton
        inverted: true
        enabled: urlInput.text && folderInput.text
        text: qsTr("CONNECT") + tl.tr

        anchors {
            bottom: parent.bottom
            bottomMargin: 40
            horizontalCenter: parent.horizontalCenter
        }

        onClicked: {
            api.web_authentication(usernameInput.text, urlInput.text, folderInput.text)
            control.close()
        }
    }

    FileDialog {
        id: fileDialog
        folder: shortcuts.home
        selectFolder: true
        onAccepted: {
            folderInput.text = fileDialog.fileUrl.toString().replace("file://", "")
        }
    }
}