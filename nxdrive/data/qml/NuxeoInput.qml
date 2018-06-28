import QtQuick 2.10

TextInput {
    id: control
    property string placeholderText
    property string lineColor: nuxeoBlue

    selectionColor: teal
    horizontalAlignment: TextInput.AlignLeft
    verticalAlignment: TextInput.AlignVCenter

    Text {
        text: control.placeholderText
        font: control.font
        color: "#aaa"
        visible: !control.text
        anchors {
            bottom: parent.bottom
            bottomMargin: 3
        }
    }
    Rectangle {
        color: control.focus ? control.lineColor : "#aaa"
        width: parent.width; height: 1
        anchors.bottom: parent.bottom
    }
}