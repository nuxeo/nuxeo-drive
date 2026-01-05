import QtQuick 2.15
import QtQuick.Controls 2.15

Button {
    id: control
    property int radius: 4
    property int borderWidth: 1
    property int size: 12

    // Primary or secondary actions
    property bool primary: true

    contentItem: ScaledText {
        id: buttonText
        text: control.text

        leftPadding: 5
        rightPadding: 5
        opacity: enabled ? 1.0 : 0.3
        anchors {
            centerIn: buttonBackground
        }
        color: control.primary ? (control.hovered ? primaryButtonTextHover : primaryButtonText) : (control.hovered ? secondaryButtonTextHover : secondaryButtonText)
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Rectangle {
        id: buttonBackground
        width: buttonText.width + control.size
        height: buttonText.height + control.size
        opacity: enabled ? 1 : 0.3
        color: control.primary ? (control.hovered ? primaryBgHover : primaryBg) : (control.hovered ? secondaryBgHover : secondaryBg)
        radius: control.radius

        border {
            width: borderWidth
            color: control.primary ? buttonBackground.color : buttonText.color
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onPressed: mouse.accepted = false
    }
}
