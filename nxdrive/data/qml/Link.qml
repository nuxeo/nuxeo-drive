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
        width: parent.width
        height: parent.height
        anchors.centerIn: parent
        onClicked: control.clicked()
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
    }
}
