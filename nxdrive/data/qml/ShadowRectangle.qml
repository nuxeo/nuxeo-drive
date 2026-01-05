import QtQuick 2.15

Rectangle {
    id: control
    radius: 8
    property string shadowColor: "#16000000"
    property real offset: Math.min(width*0.02, height*0.02)
    property int spread: 4

    border.width: 0

    Repeater {
        model: control.offset
        Rectangle {
            color: shadowColor
            width: control.width + control.spread
            height: control.height + control.spread
            z: -1
            opacity: 1 / (index * 1.2)
            radius: control.radius + 2
            anchors.left: control.left
            anchors.leftMargin: - index - 1 - control.spread / 2
            anchors.top: control.top
            anchors.topMargin: index + 1 - control.spread / 2
        }
    }
}
