import QtQuick 2.6
import QtQuick.Controls 2.1

ToolTip {
    id: control
    delay: 600
    contentItem: Text {
        text: control.text
        font: control.font
        color: "#333"
    }

    background: Rectangle {
        border.color: "#efefef"
    }
}