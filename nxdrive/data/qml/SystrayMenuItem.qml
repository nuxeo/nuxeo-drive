import QtQuick 2.10
import QtQuick.Controls 2.3

Rectangle {
    id: control
    property string text
    property int size: 14
    height: size * 2; width: 100

    signal clicked()

    color: clickArea.containsMouse ? lightGray : lighterGray

    ScaledText {
        id: itemText
        text: control.text
        pointSize: control.size
        
        padding: 10
        height: parent.height
        elide: Text.ElideRight
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
