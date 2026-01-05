import QtQuick 2.15
import QtQuick.Controls 2.15

TabButton {
    id: control
    property int barIndex
    property int index
    property bool activated: barIndex == index

    height: 50


    contentItem:  ScaledText {
        text: control.text
        color: activated ? focusedTab : unfocusedTab
        font{
            weight: activated ? 600 : 400
            pointSize: point_size * 1.2
        }
        opacity: enabled ? 1.0 : 0.3
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Item {
        opacity: enabled ? 1 : 0.3
        height: control.height

        HorizontalSeparator {
            height: activated ? 2 : 1; radius: 1
            anchors.bottom: parent.bottom
            color: activated ? focusedUnderline : unfocusedUnderline
        }
    }

    MouseArea
    {
        id: mouseArea
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onPressed:  mouse.accepted = false
    }
}
