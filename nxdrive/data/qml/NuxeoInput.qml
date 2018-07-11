import QtQuick 2.10

TextInput {
    id: control
    property string placeholderText
    property string lineColor: nuxeoBlue

    font.pointSize: 12 / ratio
    selectionColor: teal
    horizontalAlignment: TextInput.AlignLeft
    verticalAlignment: TextInput.AlignVCenter

    Rectangle {
        color: control.focus ? control.lineColor : lightGray
        width: control.width; height: 1
        anchors.bottom: parent.bottom
    }

    ScaledText {
        text: control.placeholderText
        font: control.font
        color: lightGray
        visible: !control.text
        anchors {
            bottom: parent.bottom
            bottomMargin: 3
        }
    }
}
