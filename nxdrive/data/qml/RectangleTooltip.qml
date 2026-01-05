import QtQuick 6.0
import QtQuick.Controls 6.0
import QtQuick.Layouts 6.0

Rectangle {
    id: control
    property string tooltip;
    property string hoverColor;

    Rectangle {
        color: control.hoverColor && mouseArea.containsMouse ? control.hoverColor: control.color
        anchors.fill: parent
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
    }

    NuxeoToolTip {
        text: tooltip
        visible: control.tooltip && mouseArea.containsMouse
    }
}
