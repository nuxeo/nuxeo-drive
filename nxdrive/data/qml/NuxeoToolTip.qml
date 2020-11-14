import QtQuick 2.15
import QtQuick.Controls 2.15

ToolTip {
    id: control
    delay: 600
    contentItem: ScaledText {
        text: control.text
        color: "#FFFFFF"
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignHCenter
    }

    background: Rectangle {
        border.color: "#848484"
        color: "#848484"
        radius: 3
    }
}
