import QtQuick 2.10
import QtQuick.Controls 2.3

CheckBox {
    id: control
    property string color: "#333"
    property string borderColor: "#333"
    property string checkColor: "#333"

    indicator: Rectangle {
        implicitWidth: 14
        implicitHeight: 14
        x: control.leftPadding
        y: parent.height / 2 - height / 2
        radius: 2
        border.color: borderColor

        Rectangle {
            width: 8
            height: 8
            x: 3
            y: 3
            radius: 1
            color: checkColor
            visible: control.checked
        }
    }

    contentItem: Text {
        text: control.text
        font: control.font
        opacity: enabled ? 1.0 : 0.3
        color: control.color
        verticalAlignment: Text.AlignVCenter
        leftPadding: control.indicator.width + control.spacing
    }
}