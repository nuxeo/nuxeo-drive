import QtQuick 2.10
import QtQuick.Layouts 1.3

NuxeoPopup {
    id: control
    property string message
    property string okColor: nuxeoBlue

    signal ok()
    signal cancel()

    width: 250
    height: 150

    contentItem: Item {
        width: control.width; height: control.height

        ColumnLayout {
            width: parent.width - 30
            height: parent.height - 30
            anchors.centerIn: parent
            spacing: 20
            ScaledText {
                text: message
                wrapMode: Text.WordWrap
                Layout.maximumWidth: parent.width
                Layout.alignment: Qt.AlignHCenter
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter | Qt.AlignBottom
                spacing: 20
                NuxeoButton {
                    id: cancelButton
                    text: qsTr("CANCEL") + tl.tr
                    lightColor: mediumGray
                    darkColor: darkGray
                    inverted: true
                    Layout.alignment: Qt.AlignLeft
                    onClicked: { control.cancel(); control.close() }
                }

                NuxeoButton {
                    id: okButton
                    text: qsTr("CONTINUE") + tl.tr
                    inverted: true
                    color: control.okColor
                    Layout.alignment: Qt.AlignRight
                    onClicked: { control.ok(); control.close() }
                }
            }
        }
    }
}
