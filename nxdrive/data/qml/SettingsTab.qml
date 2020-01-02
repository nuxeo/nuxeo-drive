import QtQuick 2.13
import QtQuick.Controls 2.13

TabButton {
    id: control
    property int barIndex
    property int index
    property string color
    property string underlineColor: nuxeoBlue
    property bool activated: barIndex == index

    height: 50


    contentItem:  ScaledText {
        text: control.text
        font{
            weight: Font.Bold
            pointSize: point_size * 1.2
        }
        opacity: enabled ? 1.0 : 0.3
        color: activated ? control.underlineColor : control.color
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Item {
        opacity: enabled ? 1 : 0.3
        height: control.height

        HorizontalSeparator {
            height: activated ? 2 : 1; radius: 1
            anchors.bottom: parent.bottom
            color: activated ? control.underlineColor : lightGray
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
