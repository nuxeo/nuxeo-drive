import QtQuick 2.15
import QtQuick.Controls 2.15

ToolTip {
    id: control
    delay: 600
    contentItem: ScaledText {
        text: control.text
        color: lightTheme
        leftPadding: 3
        rightPadding: 3
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignHCenter
        wrapMode: control.text.length > 60 ? Text.WrapAnywhere : Text.NoWrap
    }

    background: Rectangle {
        border.color: grayBorder
        color: grayBorder
        radius: 3
    }
}
