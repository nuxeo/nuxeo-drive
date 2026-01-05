import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: control
    property string text
    property int size: 14
    height: size * 2; width: 100

    signal clicked()

    color: clickArea.containsMouse ? lightGray : uiBackground

    ScaledText {
        id: itemText
        text: control.text

        padding: 10
        height: parent.height
        horizontalAlignment: Text.AlignLeft
        verticalAlignment: Text.AlignVCenter
    }

    MouseArea {
        id: clickArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: control.clicked()
        cursorShape: Qt.PointingHandCursor
    }
}
