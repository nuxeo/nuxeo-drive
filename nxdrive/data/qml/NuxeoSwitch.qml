import QtQuick 2.10
import QtQuick.Controls 2.3

Switch {
    id: control

    property string lightColor: nuxeoBlue
    property string darkColor: darkBlue
    property string textColor: darkGray
    property int size: 8

    indicator: Rectangle {
        implicitWidth: size * 4
        implicitHeight: size * 2
        x: control.leftPadding
        y: parent.height / 2 - height / 2
        radius: size
        color: control.checked ? lightColor : "white"
        border {
            color: control.checked ? lightColor : mediumGray
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
            color: control.checked ? (control.down ? lighterGray : "white") : mediumGray
            border.width: 0
        }
    }

    contentItem: ScaledText {
        color: control.textColor
        text: control.text
        opacity: enabled ? 1.0 : 0.3
        verticalAlignment: Text.AlignVCenter
        leftPadding: control.indicator.width + control.spacing
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onPressed: mouse.accepted = false
    }
}
