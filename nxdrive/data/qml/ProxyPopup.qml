import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Dialogs 1.3
import QtQuick.Window 2.2
import "icon-font/Icon.js" as MdiFont

Popup {
    id: control

    width: 400
    height: 200 + (manualSettings.visible ? 150 : 0) + (automaticSettings.visible ? 30 : 0)
    x: (parent.width - width) / 2
    y: (parent.height - height) / 2
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    
    background: ShadowRectangle { border.width: 0 }
    
    onOpened: {
        var proxy = JSON.parse(api.get_proxy_settings())
        switch(proxy.config) {
            case "None":
                proxyType.currentIndex = 0
                break
            case "System":
                proxyType.currentIndex = 1
                break
            case "Manual":
                proxyType.currentIndex = 2
                urlInput.text = proxy.url
                authenticatedCheckBox.checked = proxy.authenticated
                if (proxy.authenticated) {
                    usernameInput.text = proxy.username
                    passwordInput.text = proxy.password
                }
                break
            case "Automatic":
                proxyType.currentIndex = 3
                pacUrlInput.text = proxy.pac_url
                break
        }
    }

    NuxeoComboBox {
        id: proxyType
        width: 300

        anchors {
            horizontalCenter: parent.horizontalCenter
            top: parent.top
            topMargin: 30
        }

        textRole: "type"
        displayText: qsTr(currentText) + tl.tr
        model: ListModel {
            ListElement { type: "NONE"; value: "None" }
            ListElement { type: "SYSTEM"; value: "System" }
            ListElement { type: "MANUAL"; value: "Manual" }
            ListElement { type: "AUTOMATIC"; value: "Automatic" }
        }
            
        delegate: ItemDelegate {
            width: proxyType.width
            contentItem: Text {
                text: qsTr(type) + tl.tr
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
            highlighted: proxyType.highlightedIndex === index
        }
    }

    Item {
        id: manualSettings
        visible: proxyType.currentIndex == 2
        width: parent.width * 3/4; height: 110
        anchors {
            horizontalCenter: parent.horizontalCenter
            top: proxyType.bottom
            topMargin: 20
        }

        NuxeoInput {
            id: urlInput
            width: parent.width; height: 20
            placeholderText: qsTr("URL") + tl.tr
            inputMethodHints: Qt.ImhUrlCharactersOnly
            KeyNavigation.tab: authenticatedCheckBox

            anchors.top: parent.top
        }

        NuxeoCheckBox {
            id: authenticatedCheckBox
            KeyNavigation.tab: usernameInput

            text: qsTr("REQUIRES_AUTHENTICATION") + tl.tr

            anchors {
                top: urlInput.bottom
                topMargin: 20
            }
        }

        Item {
            width: parent.width; height: 70
            anchors {
                top: authenticatedCheckBox.bottom
                topMargin: 20
            }
            visible: authenticatedCheckBox.checked

            NuxeoInput {
                id: usernameInput
                width: parent.width; height: 20
                placeholderText: qsTr("USERNAME") + tl.tr
                KeyNavigation.tab: passwordInput
                anchors.top: parent.top
            }
            
            NuxeoInput {
                id: passwordInput
                width: parent.width; height: 20
                placeholderText: qsTr("PASSWORD") + tl.tr
                echoMode: TextInput.Password
                anchors {
                    top: usernameInput.bottom
                    topMargin: 20
                }
            }
        }
    }

    Item {
        id: automaticSettings
        visible: proxyType.currentIndex == 3
        width: parent.width * 3/4; height: contentHeight
        anchors {
            horizontalCenter: parent.horizontalCenter
            top: proxyType.bottom
            topMargin: 20
        }

        NuxeoInput {
            id: pacUrlInput
            width: parent.width; height: 20
            placeholderText: qsTr("SCRIPT_ADDR") + tl.tr
            inputMethodHints: Qt.ImhUrlCharactersOnly
            anchors.top: parent.top
        }
    }
    
    NuxeoButton {
        id: cancelButton
        text: qsTr("ROOT_USED_CANCEL") + tl.tr
        lightColor: mediumGray
        darkColor: "#333"
        inverted: true
        size: 14
        anchors {
            left: parent.left
            bottom: parent.bottom
            leftMargin: 40
            bottomMargin: 30
        }
        onClicked: control.close()
    }

    NuxeoButton {
        id: okButton
        text: qsTr("APPLY") + tl.tr
        inverted: true
        size: 14
        anchors {
            right: parent.right
            bottom: parent.bottom
            rightMargin: 40
            bottomMargin: 30
        }
        onClicked: {
            if (api.set_proxy_settings(
                proxyType.model.get(proxyType.currentIndex).value,
                urlInput.text,
                authenticatedCheckBox.checked,
                usernameInput.text,
                passwordInput.text,
                pacUrlInput.text
            )) {
                control.close()
            }
        }
    }
}