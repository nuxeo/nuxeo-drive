import QtQuick 2.13
import QtQuick.Controls 2.13

ToolTip {
    id: control
    delay: 600
    contentItem: ScaledText {
        text: control.text
        color: "#FFFFFF"
    }

    background: Rectangle {
        border.color: "#848484"
        color: "#848484"
    }
}
