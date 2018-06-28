import QtQuick 2.10
import QtQuick.Controls 2.3

TabButton {
    id: control
    property int barIndex
    property int index
    property string color
    property string underlineColor
    
    height: 50

    font { weight: Font.Bold; pointSize: 14 }
    
    contentItem: Text {
        text: control.text
        font: control.font
        opacity: enabled ? 1.0 : 0.3
        color: barIndex == index ? control.underlineColor : control.color
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        opacity: enabled ? 1 : 0.3
        height: control.height

        Rectangle {
            width: parent.width * 3 / 4; height: 2; radius: 1
            anchors {
                bottom: parent.bottom
                horizontalCenter: parent.horizontalCenter
            }
            visible: barIndex == index
            color: control.underlineColor
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