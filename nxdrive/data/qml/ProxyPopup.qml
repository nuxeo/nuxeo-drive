import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

NuxeoPopup {
    id: control

    property bool isManual: proxyType.currentIndex == 2
    property bool isAuto: proxyType.currentIndex == 3

    title: qsTr("PROXY_CHANGE_SETTINGS") + tl.tr
    width: 480
    height: 200
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

        Keys.onReturnPressed: okButton.clicked()
        Keys.onEnterPressed: okButton.clicked()

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
            font.family: "Courier"
            placeholderText: 'https://username:password@proxy.tld:port'
            inputMethodHints: Qt.ImhUrlCharactersOnly
        }

        ScaledText {
            text: qsTr("SCRIPT_ADDR") + tl.tr
            color: mediumGray
            visible: isAuto
        }
        NuxeoInput {
            id: pacUrlInput
            visible: isAuto
            Layout.fillWidth: true
            font.family: "Courier"
            placeholderText: 'https://server.tld/proxy.pac\nfile://C:/proxy.pac'
            inputMethodHints: Qt.ImhUrlCharactersOnly
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            Layout.columnSpan: 2

            NuxeoButton {
                id: cancelButton
                text: qsTr("CANCEL") + tl.tr
                primary: false
                onClicked: control.close()
            }

            NuxeoButton {
                id: okButton
                text: qsTr("APPLY") + tl.tr
                enabled:
                    proxyType.currentIndex < 2
                    || (isManual && urlInput.text)
                    || (isAuto && pacUrlInput.text)
                onClicked: {
                    // No check is done on setting change as we want to revalidate the existing proxy
                    if (api.set_proxy_settings(
                        proxyType.model.get(proxyType.currentIndex).value,
                        urlInput.text,
                        pacUrlInput.text
                    )) {
                        control.close()
                    }
                }
            }
        }
    }
}
