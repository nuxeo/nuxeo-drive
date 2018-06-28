import QtQuick 2.10
import QtQuick.Controls 2.3

Switch {
    id: control

    property string lightColor: nuxeoBlue
    property string darkColor: darkBlue
    property int size: 8

    indicator: Rectangle {
        implicitWidth: size * 4
        implicitHeight: size * 2
        x: control.leftPadding
        y: parent.height / 2 - height / 2
        radius: size
        color: control.checked ? lightColor : "#ffffff"
        border.color: control.checked ? lightColor : "#cccccc"

        Rectangle {
            x: control.checked ? parent.width - width : 0
            width: size * 2
            height: size * 2
            radius: size
            color: control.down ? "#cccccc" : "#ffffff"
            border.color: control.checked ? (control.down ? darkColor : lightColor) : "#999999"
        }
    }

    contentItem: Text {
        text: control.text
        font: control.font
        opacity: enabled ? 1.0 : 0.3
        verticalAlignment: Text.AlignVCenter
        leftPadding: control.indicator.width + control.spacing
    }
}