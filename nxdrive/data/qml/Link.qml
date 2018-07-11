import QtQuick 2.10

 ScaledText {
    id: control

    signal clicked()

    color: nuxeoBlue

    elide: Text.ElideRight
    horizontalAlignment: Text.AlignLeft
    verticalAlignment: Text.AlignVCenter

    MouseArea {
        id: linkArea
        width: parent.width * 3/2
        height: parent.height * 3/2
        anchors.centerIn: parent
        onClicked: control.clicked()
        cursorShape: Qt.PointingHandCursor
    }
}
