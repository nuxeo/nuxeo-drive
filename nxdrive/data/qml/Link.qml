import QtQuick 2.15

ScaledText {
    id: control

    signal clicked()

    property bool enabled: true

    color: interactiveLink

    horizontalAlignment: Text.AlignLeft
    verticalAlignment: Text.AlignVCenter

    MouseArea {
        id: linkArea
        enabled: parent.enabled
        width: parent.width * 3/2
        height: parent.height * 3/2
        anchors.centerIn: parent
        onClicked: control.clicked()
        cursorShape: Qt.PointingHandCursor
    }
}
