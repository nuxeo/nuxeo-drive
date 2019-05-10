import QtQuick 2.10
import QtQuick.Controls 2.3

Switch {
    id: control

    property bool enabled: true
    property string checkedColor: enabled ? nuxeoBlue : lightGray
    property string uncheckedColor: enabled ? mediumGray : lightGray
    property string textColor: enabled ? darkGray : lightGray
    property int size: 8
    property int leftOffset: size * 4 + spacing
    leftPadding: leftOffset

    indicator: Rectangle {
        implicitWidth: size * 4
        implicitHeight: size * 2
        x: control.leftPadding - leftOffset
        y: parent.height / 2 - height / 2
        radius: size
        color: control.checked ? checkedColor : "white"
        border {
            color: control.checked ? checkedColor : uncheckedColor
            width: 2
        }

        Rectangle {
            property int roundSize: Math.round(size * 1.2)
            property int roundMargin: Math.round(size * 0.4)

            x: control.checked ? parent.width - width - roundMargin : roundMargin
            y: parent.height / 2 - height / 2
            width: roundSize
            height: roundSize
            radius: size
            color: control.checked ? (control.down ? lighterGray : "white") : uncheckedColor
            border.width: 0
        }
    }

    contentItem: ScaledText {
        color: control.textColor
        text: control.text
        opacity: enabled ? 1.0 : 0.3
        verticalAlignment: Text.AlignVCenter
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ForbiddenCursor
        onPressed: mouse.accepted = !control.enabled
    }
}
