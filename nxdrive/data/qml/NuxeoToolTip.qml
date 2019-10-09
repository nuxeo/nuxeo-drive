import QtQuick 2.13
import QtQuick.Controls 2.13

ToolTip {
    id: control
    delay: 600
    contentItem: ScaledText {
        text: control.text
        color: "#333"
    }

    background: Rectangle {
        border.color: "#efefef"
    }
}
