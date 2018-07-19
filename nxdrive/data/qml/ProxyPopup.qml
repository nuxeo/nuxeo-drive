import QtQuick 2.10
import QtQuick.Controls 2.3
import QtQuick.Layouts 1.3

NuxeoPopup {
    id: control

    property bool isManual: proxyType.currentIndex == 2
    property bool isAuth: authenticatedCheckBox.checked
    property bool isAuto: proxyType.currentIndex == 3

    title: qsTr("PROXY_CHANGE_SETTINGS") + tl.tr
    width: 480
    topPadding: 60
    leftPadding: 50
    rightPadding: 50

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

    contentItem: GridLayout {
        columns: 2
        rowSpacing: 20
        columnSpacing: 20

        ScaledText { text: qsTr("TYPE") + tl.tr; color: mediumGray }
        NuxeoComboBox {
            id: proxyType
            Layout.fillWidth: true

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
                contentItem: ScaledText {
                    text: qsTr(type) + tl.tr
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
                highlighted: proxyType.highlightedIndex === index
            }
        }

        ScaledText { text: qsTr("URL") + tl.tr; color: mediumGray; visible: isManual }
        NuxeoInput {
            id: urlInput
            visible: isManual
            Layout.fillWidth: true
            font.family: 'monospace'
            inputMethodHints: Qt.ImhUrlCharactersOnly
            KeyNavigation.tab: authenticatedCheckBox
        }

        NuxeoCheckBox {
            id: authenticatedCheckBox
            Layout.columnSpan: 2
            visible: proxyType.currentIndex == 2
            KeyNavigation.tab: usernameInput
            text: qsTr("REQUIRES_AUTHENTICATION") + tl.tr
        }

        ScaledText { text: qsTr("USERNAME") + tl.tr; color: mediumGray; visible: isManual && isAuth }
        NuxeoInput {
            id: usernameInput
            visible: isManual && isAuth
            Layout.fillWidth: true
            KeyNavigation.tab: passwordInput
        }

        ScaledText { text: qsTr("PASSWORD") + tl.tr; color: mediumGray; visible: isManual && isAuth }
        NuxeoInput {
            id: passwordInput
            visible: isManual && isAuth
            Layout.fillWidth: true
            echoMode: TextInput.Password
        }

        ScaledText { text: qsTr("SCRIPT_ADDR") + tl.tr; color: mediumGray; visible: isAuto }
        NuxeoInput {
            id: pacUrlInput
            visible: isAuto
            Layout.fillWidth: true
            font.family: 'monospace'
            inputMethodHints: Qt.ImhUrlCharactersOnly
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            Layout.columnSpan: 2

            NuxeoButton {
                id: cancelButton
                text: qsTr("CANCEL") + tl.tr
                lightColor: mediumGray
                darkColor: darkGray
                onClicked: control.close()
            }

            NuxeoButton {
                id: okButton
                text: qsTr("APPLY") + tl.tr
                inverted: true
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
    }
}
