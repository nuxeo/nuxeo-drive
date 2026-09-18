/*
 * © 2012-2026 Hyland.
 * All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
 */

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

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
