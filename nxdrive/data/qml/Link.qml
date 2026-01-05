import QtQuick 6.0

ScaledText {
    id: control

    signal clicked()

    property bool enabled: true
    property string tooltip

    color: interactiveLink

    horizontalAlignment: Text.AlignLeft
    verticalAlignment: Text.AlignVCenter

    MouseArea {
        id: linkArea
        enabled: parent.enabled
        hoverEnabled: control.tooltip
        width: parent.width
        height: parent.height
        anchors.centerIn: parent
        onClicked: control.clicked()
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
    }

    NuxeoToolTip {
        text: control.tooltip
        visible: control.tooltip && linkArea.containsMouse
    }
}
