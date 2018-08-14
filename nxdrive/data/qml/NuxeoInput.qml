import QtQuick 2.10

TextInput {
    id: control
    property string placeholderText
    property string lineColor: nuxeoBlue

    font.pointSize: 12 / ratio
    wrapMode: TextInput.Wrap
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
        color: lightGray
        visible: !control.text
        font: control.font

        anchors {
            bottom: parent.bottom
            bottomMargin: 3
        }
    }
}
