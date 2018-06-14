import QtQuick 2.0

Rectangle {
    id: control

    signal clicked()
    property string currentColor
    property string hoveredColor
    property string unhoveredColor

    currentColor: mouseArea.containsMouse ? hoveredColor : unhoveredColor

    opacity: mouseArea.containsMouse ? 1.0 : 0.8

    MouseArea {
        id: mouseArea
        z: 20
        cursorShape: Qt.PointingHandCursor
        anchors.fill: parent
        anchors.margins: -3
        hoverEnabled: true  // this line will enable mouseArea.containsMouse
        onClicked: { control.clicked() }
    }
}