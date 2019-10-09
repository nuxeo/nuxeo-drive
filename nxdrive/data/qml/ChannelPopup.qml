import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.Layouts 1.13

NuxeoPopup {
    id: control

    title: qsTr("CHANNEL_CHANGE_SETTINGS") + tl.tr
    width: 400
    height: 150
    topPadding: 60
    leftPadding: 50
    rightPadding: 50

    onOpened: {
        var channel = api.get_update_channel()
        switch(channel) {
            case "centralized":
                channelType.currentIndex = 0
                break
            case "release":
                channelType.currentIndex = 1
                break
            case "beta":
                channelType.currentIndex = 2
                break
            case "alpha":
                channelType.currentIndex = 3
                break
        }
    }

    contentItem: GridLayout {
        columns: 2
        rowSpacing: 20
        columnSpacing: 20

        ScaledText { text: qsTr("CHANNEL") + tl.tr; color: mediumGray }
        NuxeoComboBox {
            id: channelType

            textRole: "type"
            displayText: qsTr(currentText) + tl.tr
            model: ListModel {
                ListElement { type: "Centralized"; value: "centralized" }
                ListElement { type: "Release"; value: "release" }
                ListElement { type: "Beta"; value: "beta" }
                ListElement { type: "Alpha"; value: "alpha" }
            }

            delegate: ItemDelegate {
                width: channelType.width
                contentItem: ScaledText {
                    text: qsTr(type) + tl.tr
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
                highlighted: channelType.highlightedIndex === index
            }
        }

        ConfirmPopup {
            id: useAlpha
            message: qsTr("CHANNEL_CONFIRM_DANGEROUS") + tl.tr
            okColor: red
            onOk: {
                var channel = channelType.model.get(channelType.currentIndex).value
                api.set_update_channel(channel)
                control.close()
            }
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
                    var channel = channelType.model.get(channelType.currentIndex).value
                    if (channel == 'alpha') {
                        useAlpha.open()
                    } else {
                        api.set_update_channel(channel)
                        control.close()
                    }
                }
            }
        }
    }
}
