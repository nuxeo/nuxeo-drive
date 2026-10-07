/*
 * © 2012-2026 Hyland.
 * All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
 */

import QtQuick

TextInput {
    id: control
    property string placeholderText
    property string lineColor: focusedUnderline

    font.pointSize: point_size
    wrapMode: TextInput.Wrap
    selectionColor: primaryBg
    horizontalAlignment: TextInput.AlignLeft
    verticalAlignment: TextInput.AlignVCenter
    selectByMouse: true

    Rectangle {
        color: control.focus ? control.lineColor : lightGray
        width: control.width; height: 1
        anchors.bottom: parent.bottom
    }

    ScaledText {
        text: control.placeholderText
        color: lightGray
        visible: !control.text
        font: control.font

        anchors {
            bottom: parent.bottom
            bottomMargin: 3
        }
    }
}
