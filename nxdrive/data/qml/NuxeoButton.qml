import QtQuick 2.13
import QtQuick.Controls 2.13

Button {
    id: control
    property string lightColor : nuxeoBlue
    property string darkColor : darkBlue
    property int radius: 4
    property int borderWidth: 1
    property int size: 12
    property bool inverted: false

    property string color
    color: control.hovered ? control.darkColor : control.lightColor


    contentItem: ScaledText {
        id: buttonText
        text: control.text
        pointSize: control.size

        opacity: enabled ? 1.0 : 0.3
        anchors {
            centerIn: buttonBackground
        }
        color: control.inverted ? "white" : control.color
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        id: buttonBackground
        width: buttonText.width + control.size; height: buttonText.height + control.size
        opacity: enabled ? 1 : 0.3
        color: control.inverted ? control.color : "transparent"
        radius: control.radius

        border {
            width: borderWidth
            color: control.color
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onPressed: mouse.accepted = false
    }
}
