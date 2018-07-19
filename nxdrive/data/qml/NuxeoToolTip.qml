import QtQuick 2.10
import QtQuick.Controls 2.1

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
