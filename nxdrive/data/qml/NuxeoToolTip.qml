import QtQuick 2.15
import QtQuick.Controls 2.15

ToolTip {
    id: control
    delay: 600
    contentItem: ScaledText {
        text: control.text
        color: lightTheme
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignHCenter
    }

    background: Rectangle {
        border.color: grayBorder
        color: grayBorder
        radius: 3
    }
}
