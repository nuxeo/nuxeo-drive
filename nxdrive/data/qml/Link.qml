import QtQuick 2.10

HoverRectangle {
    id: control
    color: "transparent"
    width: linkText.contentWidth; height: linkText.contentHeight
    
    property string text
    property string lineColor: nuxeoBlue
    property bool lineVisible: true
    property int size: 14

    Text {
        id: linkText
        elide: Text.ElideRight
        text: control.text
        font.pointSize: control.size
        anchors.centerIn: parent
        horizontalAlignment: Text.AlignLeft
        verticalAlignment: Text.AlignVCenter
    }

    Rectangle {
        width: linkText.contentWidth; height: 2
        color: control.lineColor
        visible: control.lineVisible
        anchors {
            top: linkText.bottom
            left: linkText.left
        }
    }
}