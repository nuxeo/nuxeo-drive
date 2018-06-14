import QtQuick 2.10
import QtQuick.Controls 2.3

Button {
    id: control
    property string lightColor
    property string darkColor
    property string color
    property bool inverted: false

    color: control.down ? control.darkColor : control.lightColor

    font {
        family: "Neue Haas Grotesk Display Std"
        weight: Font.Bold
        pointSize: 16
    }

    contentItem: Text {
        text: control.text
        font: control.font
        opacity: enabled ? 1.0 : 0.3
        anchors.centerIn: parent
        color: control.inverted ? "white" : control.color
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        opacity: enabled ? 1 : 0.3
        color: control.inverted ? control.color : "white"
        border {
            width: 2
            color: control.color
        }
        radius: 20
    }
}