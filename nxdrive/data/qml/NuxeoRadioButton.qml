import QtQuick 2.10
import QtQuick.Controls 2.3

RadioButton {
    id: control
    property string color: nuxeoBlue
    property int size: 4
    property int leftOffset: size * 4 + spacing
    leftPadding: leftOffset

    indicator: Rectangle {
        implicitWidth: control.size * 4
        implicitHeight: control.size * 4
        x: control.leftPadding - leftOffset
        y: parent.height / 2 - height / 2
        radius: control.size * 2
        border {
            color: control.checked ? control.color : mediumGray
            width: 2
        }

        Rectangle {
            width: control.size * 2
            height: control.size * 2
            x: control.size
            y: control.size
            radius: control.size
            color: control.color
            visible: control.checked
        }
    }

    contentItem: ScaledText {
        text: control.text
        opacity: enabled ? 1.0 : 0.3
        verticalAlignment: Text.AlignVCenter
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onPressed: mouse.accepted = false
    }
}
